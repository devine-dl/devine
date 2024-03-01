from __future__ import annotations

import base64
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable, Optional, Union
from uuid import UUID

import m3u8
from construct import Container
from pymp4.parser import Box
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session
from rich.text import Text

from devine.core.config import config
from devine.core.console import console
from devine.core.constants import AnyTrack
from devine.core.utilities import get_binary_path, get_boxes
from devine.core.utils.subprocess import ffprobe


class Widevine:
    """Widevine DRM System."""
    def __init__(self, pssh: PSSH, kid: Union[UUID, str, bytes, None] = None, **kwargs: Any):
        if not pssh:
            raise ValueError("Provided PSSH is empty.")
        if not isinstance(pssh, PSSH):
            raise TypeError(f"Expected pssh to be a {PSSH}, not {pssh!r}")

        if pssh.system_id == PSSH.SystemId.PlayReady:
            pssh.to_widevine()

        if kid:
            if isinstance(kid, str):
                kid = UUID(hex=kid)
            elif isinstance(kid, bytes):
                kid = UUID(bytes=kid)
            if not isinstance(kid, UUID):
                raise ValueError(f"Expected kid to be a {UUID}, str, or bytes, not {kid!r}")
            pssh.set_key_ids([kid])

        self._pssh = pssh

        if not self.kids:
            raise Widevine.Exceptions.KIDNotFound("No Key ID was found within PSSH and none were provided.")

        self.content_keys: dict[UUID, str] = {}
        self.data: dict = kwargs or {}

    @classmethod
    def from_track(cls, track: AnyTrack, session: Optional[Session] = None) -> Widevine:
        """
        Get PSSH and KID from within the Initiation Segment of the Track Data.
        It also tries to get PSSH and KID from other track data like M3U8 data
        as well as through ffprobe.

        Create a Widevine DRM System object from a track's information.
        This should only be used if a PSSH could not be provided directly.
        It is *rare* to need to use this.

        You may provide your own requests session to be able to use custom
        headers and more.

        Raises:
            PSSHNotFound - If the PSSH was not found within the data.
            KIDNotFound - If the KID was not found within the data or PSSH.
        """
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
                if x and x.keyformat and x.keyformat.lower() == WidevineCdm.urn
            )

        init_data = track.get_init_segment(session=session)
        if init_data:
            # try get via ffprobe, needed for non mp4 data e.g. WEBM from Google Play
            probe = ffprobe(init_data)
            if probe:
                for stream in probe.get("streams") or []:
                    enc_key_id = stream.get("tags", {}).get("enc_key_id")
                    if enc_key_id:
                        kid = UUID(bytes=base64.b64decode(enc_key_id))
            pssh_boxes.extend(list(get_boxes(init_data, b"pssh")))
            tenc_boxes.extend(list(get_boxes(init_data, b"tenc")))

        pssh_boxes.sort(key=lambda b: {
            PSSH.SystemId.Widevine: 0,
            PSSH.SystemId.PlayReady: 1
        }[b.system_ID])

        pssh = next(iter(pssh_boxes), None)
        if not pssh:
            raise Widevine.Exceptions.PSSHNotFound("PSSH was not found in track data.")

        tenc = next(iter(tenc_boxes), None)
        if not kid and tenc and tenc.key_ID.int != 0:
            kid = tenc.key_ID

        return cls(pssh=PSSH(pssh), kid=kid)

    @classmethod
    def from_init_data(cls, init_data: bytes) -> Widevine:
        """
        Get PSSH and KID from within Initialization Segment Data.

        This should only be used if a PSSH could not be provided directly.
        It is *rare* to need to use this.

        Raises:
            PSSHNotFound - If the PSSH was not found within the data.
            KIDNotFound - If the KID was not found within the data or PSSH.
        """
        if not init_data:
            raise ValueError("Init data should be provided.")
        if not isinstance(init_data, bytes):
            raise TypeError(f"Expected init data to be bytes, not {init_data!r}")

        kid: Optional[UUID] = None
        pssh_boxes: list[Container] = list(get_boxes(init_data, b"pssh"))
        tenc_boxes: list[Container] = list(get_boxes(init_data, b"tenc"))

        # try get via ffprobe, needed for non mp4 data e.g. WEBM from Google Play
        probe = ffprobe(init_data)
        if probe:
            for stream in probe.get("streams") or []:
                enc_key_id = stream.get("tags", {}).get("enc_key_id")
                if enc_key_id:
                    kid = UUID(bytes=base64.b64decode(enc_key_id))

        pssh_boxes.sort(key=lambda b: {
            PSSH.SystemId.Widevine: 0,
            PSSH.SystemId.PlayReady: 1
        }[b.system_ID])

        pssh = next(iter(pssh_boxes), None)
        if not pssh:
            raise Widevine.Exceptions.PSSHNotFound("PSSH was not found in track data.")

        tenc = next(iter(tenc_boxes), None)
        if not kid and tenc and tenc.key_ID.int != 0:
            kid = tenc.key_ID

        return cls(pssh=PSSH(pssh), kid=kid)

    @property
    def pssh(self) -> PSSH:
        """Get Protection System Specific Header Box."""
        return self._pssh

    @property
    def kid(self) -> Optional[UUID]:
        """Get first Key ID, if any."""
        return next(iter(self.kids), None)

    @property
    def kids(self) -> list[UUID]:
        """Get all Key IDs."""
        return self._pssh.key_ids

    def get_content_keys(self, cdm: WidevineCdm, certificate: Callable, licence: Callable) -> None:
        """
        Create a CDM Session and obtain Content Keys for this DRM Instance.
        The certificate and license params are expected to be a function and will
        be provided with the challenge and session ID.
        """
        for kid in self.kids:
            if kid in self.content_keys:
                continue

            session_id = cdm.open()

            try:
                cdm.set_service_certificate(
                    session_id,
                    certificate(
                        challenge=cdm.service_certificate_challenge
                    )
                )

                cdm.parse_license(
                    session_id,
                    licence(
                        challenge=cdm.get_license_challenge(session_id, self.pssh)
                    )
                )

                self.content_keys = {
                    key.kid: key.key.hex()
                    for key in cdm.get_keys(session_id, "CONTENT")
                }
                if not self.content_keys:
                    raise Widevine.Exceptions.EmptyLicense("No Content Keys were within the License")

                if kid not in self.content_keys:
                    raise Widevine.Exceptions.CEKNotFound(f"No Content Key for KID {kid.hex} within the License")
            finally:
                cdm.close(session_id)

    def decrypt(self, path: Path) -> None:
        """
        Decrypt a Track with Widevine DRM.
        Raises:
            EnvironmentError if the Shaka Packager executable could not be found.
            ValueError if the track has not yet been downloaded.
            SubprocessError if Shaka Packager returned a non-zero exit code.
        """
        if not self.content_keys:
            raise ValueError("Cannot decrypt a Track without any Content Keys...")

        platform = {"win32": "win", "darwin": "osx"}.get(sys.platform, sys.platform)
        executable = get_binary_path("shaka-packager", "packager", f"packager-{platform}", f"packager-{platform}-x64")
        if not executable:
            raise EnvironmentError("Shaka Packager executable not found but is required.")
        if not path or not path.exists():
            raise ValueError("Tried to decrypt a file that does not exist.")

        output_path = path.with_stem(f"{path.stem}_decrypted")
        config.directories.temp.mkdir(parents=True, exist_ok=True)

        try:
            arguments = [
                f"input={path},stream=0,output={output_path},output_format=MP4",
                "--enable_raw_key_decryption", "--keys",
                ",".join([
                    *[
                        "label={}:key_id={}:key={}".format(i, kid.hex, key.lower())
                        for i, (kid, key) in enumerate(self.content_keys.items())
                    ],
                    *[
                        # some services use a blank KID on the file, but real KID for license server
                        "label={}:key_id={}:key={}".format(i, "00" * 16, key.lower())
                        for i, (kid, key) in enumerate(self.content_keys.items(), len(self.content_keys))
                    ]
                ]),
                "--temp_dir", config.directories.temp
            ]

            p = subprocess.Popen(
                [executable, *arguments],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            stream_skipped = False
            had_error = False

            shaka_log_buffer = ""
            for line in iter(p.stderr.readline, ""):
                line = line.strip()
                if not line:
                    continue
                if "Skip stream" in line:
                    # file/segment was so small that it didn't have any actual data, ignore
                    stream_skipped = True
                if ":INFO:" in line:
                    continue
                if ":ERROR:" in line:
                    had_error = True
                if "Insufficient bits in bitstream for given AVC profile" in line:
                    # this is a warning and is something we don't have to worry about
                    continue
                shaka_log_buffer += f"{line.strip()}\n"

            if shaka_log_buffer:
                # wrap to console width - padding - '[Widevine]: '
                shaka_log_buffer = "\n            ".join(textwrap.wrap(
                    shaka_log_buffer.rstrip(),
                    width=console.width - 22,
                    initial_indent=""
                ))
                console.log(Text.from_ansi("\n[Widevine]: " + shaka_log_buffer))

            p.wait()

            if p.returncode != 0 or had_error:
                raise subprocess.CalledProcessError(p.returncode, arguments)

            path.unlink()
            if not stream_skipped:
                shutil.move(output_path, path)
        except subprocess.CalledProcessError as e:
            if e.returncode == 0xC000013A:  # STATUS_CONTROL_C_EXIT
                raise KeyboardInterrupt()
            raise

    class Exceptions:
        class PSSHNotFound(Exception):
            """PSSH (Protection System Specific Header) was not found."""

        class KIDNotFound(Exception):
            """KID (Encryption Key ID) was not found."""

        class CEKNotFound(Exception):
            """CEK (Content Encryption Key) for KID was not found in License."""

        class EmptyLicense(Exception):
            """License returned no Content Encryption Keys."""


__all__ = ("Widevine",)
