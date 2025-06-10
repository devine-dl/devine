from __future__ import annotations

import base64
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Callable, Optional, Union
from uuid import UUID

import m3u8
from construct import Container
from pymp4.parser import Box
from pyplayready.cdm import Cdm as PlayReadyCdm
from pyplayready.system.pssh import PSSH
from requests import Session
from rich.text import Text

from devine.core import binaries
from devine.core.config import config
from devine.core.console import console
from devine.core.constants import AnyTrack
from devine.core.utilities import get_boxes
from devine.core.utils.subprocess import ffprobe


class PlayReady:
    """PlayReady DRM System."""

    def __init__(
        self,
        pssh: PSSH,
        kid: Union[UUID, str, bytes, None] = None,
        pssh_b64: Optional[str] = None,
        **kwargs: Any,
    ):
        if not pssh:
            raise ValueError("Provided PSSH is empty.")
        if not isinstance(pssh, PSSH):
            raise TypeError(f"Expected pssh to be a {PSSH}, not {pssh!r}")

        kids: list[UUID] = []
        for header in pssh.wrm_headers:
            try:
                signed_ids, _, _, _ = header.read_attributes()
            except Exception:
                continue
            for signed_id in signed_ids:
                try:
                    kids.append(UUID(bytes_le=base64.b64decode(signed_id.value)))
                except Exception:
                    continue

        if kid:
            if isinstance(kid, str):
                kid = UUID(hex=kid)
            elif isinstance(kid, bytes):
                kid = UUID(bytes=kid)
            if not isinstance(kid, UUID):
                raise ValueError(f"Expected kid to be a {UUID}, str, or bytes, not {kid!r}")
            if kid not in kids:
                kids.append(kid)

        self._pssh = pssh
        self._kids = kids

        if not self.kids:
            raise PlayReady.Exceptions.KIDNotFound("No Key ID was found within PSSH and none were provided.")

        self.content_keys: dict[UUID, str] = {}
        self.data: dict = kwargs or {}
        if pssh_b64:
            self.data.setdefault("pssh_b64", pssh_b64)

    @classmethod
    def from_track(cls, track: AnyTrack, session: Optional[Session] = None) -> PlayReady:
        if not session:
            session = Session()
            session.headers.update(config.headers)

        kid: Optional[UUID] = None
        pssh_boxes: list[Container] = []
        tenc_boxes: list[Container] = []

        if track.descriptor == track.Descriptor.HLS:
            m3u_url = track.url
            master = m3u8.loads(session.get(m3u_url).text, uri=m3u_url)
            pssh_boxes.extend(
                Box.parse(base64.b64decode(x.uri.split(",")[-1]))
                for x in (master.session_keys or master.keys)
                if x and x.keyformat and "playready" in x.keyformat.lower()
            )

        init_data = track.get_init_segment(session=session)
        if init_data:
            probe = ffprobe(init_data)
            if probe:
                for stream in probe.get("streams") or []:
                    enc_key_id = stream.get("tags", {}).get("enc_key_id")
                    if enc_key_id:
                        kid = UUID(bytes=base64.b64decode(enc_key_id))
            pssh_boxes.extend(list(get_boxes(init_data, b"pssh")))
            tenc_boxes.extend(list(get_boxes(init_data, b"tenc")))

        pssh = next((b for b in pssh_boxes if b.system_ID == PSSH.SYSTEM_ID.bytes), None)
        if not pssh:
            raise PlayReady.Exceptions.PSSHNotFound("PSSH was not found in track data.")

        tenc = next(iter(tenc_boxes), None)
        if not kid and tenc and tenc.key_ID.int != 0:
            kid = tenc.key_ID

        pssh_bytes = Box.build(pssh)
        return cls(pssh=PSSH(pssh_bytes), kid=kid, pssh_b64=base64.b64encode(pssh_bytes).decode())

    @classmethod
    def from_init_data(cls, init_data: bytes) -> PlayReady:
        if not init_data:
            raise ValueError("Init data should be provided.")
        if not isinstance(init_data, bytes):
            raise TypeError(f"Expected init data to be bytes, not {init_data!r}")

        kid: Optional[UUID] = None
        pssh_boxes: list[Container] = list(get_boxes(init_data, b"pssh"))
        tenc_boxes: list[Container] = list(get_boxes(init_data, b"tenc"))

        probe = ffprobe(init_data)
        if probe:
            for stream in probe.get("streams") or []:
                enc_key_id = stream.get("tags", {}).get("enc_key_id")
                if enc_key_id:
                    kid = UUID(bytes=base64.b64decode(enc_key_id))

        pssh = next((b for b in pssh_boxes if b.system_ID == PSSH.SYSTEM_ID.bytes), None)
        if not pssh:
            raise PlayReady.Exceptions.PSSHNotFound("PSSH was not found in track data.")

        tenc = next(iter(tenc_boxes), None)
        if not kid and tenc and tenc.key_ID.int != 0:
            kid = tenc.key_ID

        pssh_bytes = Box.build(pssh)
        return cls(pssh=PSSH(pssh_bytes), kid=kid, pssh_b64=base64.b64encode(pssh_bytes).decode())

    @property
    def pssh(self) -> PSSH:
        return self._pssh

    @property
    def pssh_b64(self) -> Optional[str]:
        return self.data.get("pssh_b64")

    @property
    def kid(self) -> Optional[UUID]:
        return next(iter(self.kids), None)

    @property
    def kids(self) -> list[UUID]:
        return self._kids

    def get_content_keys(self, cdm: PlayReadyCdm, certificate: Callable, licence: Callable) -> None:
        for kid in self.kids:
            if kid in self.content_keys:
                continue
            session_id = cdm.open()
            try:
                challenge = cdm.get_license_challenge(
                    session_id, self.pssh.wrm_headers[0]
                )
                license_res = licence(challenge=challenge)

                if isinstance(license_res, bytes):
                    license_str = license_res.decode(errors="ignore")
                else:
                    license_str = str(license_res)

                if "<License>" not in license_str:
                    try:
                        license_str = base64.b64decode(license_str + "===").decode()
                    except Exception:
                        pass

                cdm.parse_license(session_id, license_str)
                keys = {
                    key.key_id: key.key.hex() for key in cdm.get_keys(session_id)
                }
                self.content_keys.update(keys)
            finally:
                cdm.close(session_id)

        if not self.content_keys:
            raise PlayReady.Exceptions.EmptyLicense("No Content Keys were within the License")

    def decrypt(self, path: Path) -> None:
        if not self.content_keys:
            raise ValueError("Cannot decrypt a Track without any Content Keys...")
        if not binaries.ShakaPackager:
            raise EnvironmentError("Shaka Packager executable not found but is required.")
        if not path or not path.exists():
            raise ValueError("Tried to decrypt a file that does not exist.")

        output_path = path.with_stem(f"{path.stem}_decrypted")
        config.directories.temp.mkdir(parents=True, exist_ok=True)

        try:
            arguments = [
                f"input={path},stream=0,output={output_path},output_format=MP4",
                "--enable_raw_key_decryption",
                "--keys",
                ",".join([
                    *[
                        f"label={i}:key_id={kid.hex}:key={key.lower()}"
                        for i, (kid, key) in enumerate(self.content_keys.items())
                    ],
                    *[
                        f"label={i}:key_id={'00'*16}:key={key.lower()}"
                        for i, (kid, key) in enumerate(self.content_keys.items(), len(self.content_keys))
                    ],
                ]),
                "--temp_dir",
                config.directories.temp,
            ]

            p = subprocess.Popen(
                [binaries.ShakaPackager, *arguments],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )

            stream_skipped = False
            had_error = False
            shaka_log_buffer = ""
            for line in iter(p.stderr.readline, ""):
                line = line.strip()
                if not line:
                    continue
                if "Skip stream" in line:
                    stream_skipped = True
                if ":INFO:" in line:
                    continue
                if "I0" or "W0" in line:
                    continue
                if ":ERROR:" in line:
                    had_error = True
                if "Insufficient bits in bitstream for given AVC profile" in line:
                    continue
                shaka_log_buffer += f"{line.strip()}\n"

            if shaka_log_buffer:
                shaka_log_buffer = "\n            ".join(
                    textwrap.wrap(shaka_log_buffer.rstrip(), width=console.width - 22, initial_indent="")
                )
                console.log(Text.from_ansi("\n[PlayReady]: " + shaka_log_buffer))

            p.wait()

            if p.returncode != 0 or had_error:
                raise subprocess.CalledProcessError(p.returncode, arguments)

            path.unlink()
            if not stream_skipped:
                shutil.move(output_path, path)
        except subprocess.CalledProcessError as e:
            if e.returncode == 0xC000013A:
                raise KeyboardInterrupt()
            raise

    class Exceptions:
        class PSSHNotFound(Exception):
            pass

        class KIDNotFound(Exception):
            pass

        class CEKNotFound(Exception):
            pass

        class EmptyLicense(Exception):
            pass


__all__ = ("PlayReady",)
