import base64
import re
import shutil
import subprocess
from copy import copy
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union
from uuid import UUID
from zlib import crc32

import m3u8
import requests
from langcodes import Language

from devine.core.constants import TERRITORY_MAP
from devine.core.drm import DRM_T
from devine.core.utilities import get_binary_path, get_boxes
from devine.core.utils.subprocess import ffprobe


class Track:
    class Descriptor(Enum):
        URL = 1  # Direct URL, nothing fancy
        HLS = 2  # https://en.wikipedia.org/wiki/HTTP_Live_Streaming
        DASH = 3  # https://en.wikipedia.org/wiki/Dynamic_Adaptive_Streaming_over_HTTP

    def __init__(
        self,
        url: Union[str, list[str]],
        language: Union[Language, str],
        is_original_lang: bool = False,
        descriptor: Descriptor = Descriptor.URL,
        needs_repack: bool = False,
        drm: Optional[Iterable[DRM_T]] = None,
        edition: Optional[str] = None,
        extra: Optional[Any] = None,
        id_: Optional[str] = None,
    ) -> None:
        if not isinstance(url, (str, list)):
            raise TypeError(f"Expected url to be a {str}, or list of {str}, not {type(url)}")
        if not isinstance(language, (Language, str)):
            raise TypeError(f"Expected language to be a {Language} or {str}, not {type(language)}")
        if not isinstance(is_original_lang, bool):
            raise TypeError(f"Expected is_original_lang to be a {bool}, not {type(is_original_lang)}")
        if not isinstance(descriptor, Track.Descriptor):
            raise TypeError(f"Expected descriptor to be a {Track.Descriptor}, not {type(descriptor)}")
        if not isinstance(needs_repack, bool):
            raise TypeError(f"Expected needs_repack to be a {bool}, not {type(needs_repack)}")
        if not isinstance(id_, (str, type(None))):
            raise TypeError(f"Expected id_ to be a {str}, not {type(id_)}")
        if not isinstance(edition, (str, type(None))):
            raise TypeError(f"Expected edition to be a {str}, not {type(edition)}")

        invalid_urls = ", ".join(set(type(x) for x in url if not isinstance(x, str)))
        if invalid_urls:
            raise TypeError(f"Expected all items in url to be a {str}, but found {invalid_urls}")

        if drm is not None:
            try:
                iter(drm)
            except TypeError:
                raise TypeError(f"Expected drm to be an iterable, not {type(drm)}")

        self.url = url
        self.language = Language.get(language)
        self.is_original_lang = bool(is_original_lang)
        self.descriptor = descriptor
        self.needs_repack = bool(needs_repack)
        self.drm = drm
        self.edition: str = edition
        self.extra: Any = extra or {}  # allow anything for extra, but default to a dict

        if not id_:
            this = copy(self)
            this.url = self.url.rsplit("?", maxsplit=1)[0]
            checksum = crc32(repr(self).encode("utf8"))
            id_ = hex(checksum)[2:]

        self.id = id_

        # TODO: Currently using OnFoo event naming, change to just segment_filter
        self.OnSegmentFilter: Optional[Callable] = None

        # Called after one of the Track's segments have downloaded
        self.OnSegmentDownloaded: Optional[Callable[[Path], None]] = None
        # Called after the Track has downloaded
        self.OnDownloaded: Optional[Callable] = None
        # Called after the Track or one of its segments have been decrypted
        self.OnDecrypted: Optional[Callable[[DRM_T, Optional[m3u8.Segment]], None]] = None
        # Called after the Track has been repackaged
        self.OnRepacked: Optional[Callable] = None
        # Called before the Track is multiplexed
        self.OnMultiplex: Optional[Callable] = None

        self.path: Optional[Path] = None

    def __repr__(self) -> str:
        return "{name}({items})".format(
            name=self.__class__.__name__,
            items=", ".join([f"{k}={repr(v)}" for k, v in self.__dict__.items()])
        )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Track) and self.id == other.id

    def get_track_name(self) -> Optional[str]:
        """Return the base Track Name. This may be enhanced in sub-classes."""
        if (self.language.language or "").lower() == (self.language.territory or "").lower():
            self.language.territory = None  # e.g. en-en, de-DE
        if self.language.territory == "US":
            self.language.territory = None
        reduced = self.language.simplify_script()
        extra_parts = []
        if reduced.script is not None:
            extra_parts.append(reduced.script_name(max_distance=25))
        if reduced.territory is not None:
            territory = reduced.territory_name(max_distance=25)
            extra_parts.append(TERRITORY_MAP.get(territory, territory))
        return ", ".join(extra_parts) or None

    def get_key_id(self, init_data: Optional[bytes] = None, *args, **kwargs) -> Optional[UUID]:
        """
        Probe the DRM encryption Key ID (KID) for this specific track.

        It currently supports finding the Key ID by probing the track's stream
        with ffprobe for `enc_key_id` data, as well as for mp4 `tenc` (Track
        Encryption) boxes.

        It explicitly ignores PSSH information like the `PSSH` box, as the box
        is likely to contain multiple Key IDs that may or may not be for this
        specific track.

        To retrieve the initialization segment, this method calls :meth:`get_init_segment`
        with the positional and keyword arguments. The return value of `get_init_segment`
        is then used to determine the Key ID.

        Returns:
            The Key ID as a UUID object, or None if the Key ID could not be determined.
        """
        if not init_data:
            init_data = self.get_init_segment(*args, **kwargs)
        if not isinstance(init_data, bytes):
            raise TypeError(f"Expected init_data to be bytes, not {init_data!r}")

        probe = ffprobe(init_data)
        if probe:
            for stream in probe.get("streams") or []:
                enc_key_id = stream.get("tags", {}).get("enc_key_id")
                if enc_key_id:
                    return UUID(bytes=base64.b64decode(enc_key_id))

        for tenc in get_boxes(init_data, b"tenc"):
            if tenc.key_ID.int != 0:
                return tenc.key_ID

        for uuid_box in get_boxes(init_data, b"uuid"):
            if uuid_box.extended_type == UUID("8974dbce-7be7-4c51-84f9-7148f9882554"):  # tenc
                tenc = uuid_box.data
                if tenc.key_ID.int != 0:
                    return tenc.key_ID

    def get_init_segment(
        self,
        maximum_size: int = 20000,
        url: Optional[str] = None,
        byte_range: Optional[str] = None,
        session: Optional[requests.Session] = None
    ) -> bytes:
        """
        Get the Track's Initial Segment Data Stream.

        HLS and DASH tracks must explicitly provide a URL to the init segment or file.
        Providing the byte-range for the init segment is recommended where possible.

        If `byte_range` is not set, it will make a HEAD request and check the size of
        the file. If the size could not be determined, it will download up to the first
        20KB only, which should contain the entirety of the init segment. You may
        override this by changing the `maximum_size`.

        The default maximum_size of 20000 (20KB) is a tried-and-tested value that
        seems to work well across the board.

        Parameters:
            maximum_size: Size to assume as the content length if byte-range is not
                used, the content size could not be determined, or the content size
                is larger than it. A value of 20000 (20KB) or higher is recommended.
            url: Explicit init map or file URL to probe from.
            byte_range: Range of bytes to download from the explicit or implicit URL.
            session: Session context, e.g., authorization and headers.
        """
        if not isinstance(maximum_size, int):
            raise TypeError(f"Expected maximum_size to be an {int}, not {type(maximum_size)}")
        if not isinstance(url, (str, type(None))):
            raise TypeError(f"Expected url to be a {str}, not {type(url)}")
        if not isinstance(byte_range, (str, type(None))):
            raise TypeError(f"Expected byte_range to be a {str}, not {type(byte_range)}")
        if not isinstance(session, (requests.Session, type(None))):
            raise TypeError(f"Expected session to be a {requests.Session}, not {type(session)}")

        if not url:
            if self.descriptor != self.Descriptor.URL:
                raise ValueError(f"An explicit URL must be provided for {self.descriptor.name} tracks")
            if not self.url:
                raise ValueError("An explicit URL must be provided as the track has no URL")
            url = self.url

        if not session:
            session = requests.Session()

        content_length = maximum_size

        if byte_range:
            if not isinstance(byte_range, str):
                raise TypeError(f"Expected byte_range to be a str, not {byte_range!r}")
            if not re.match(r"^\d+-\d+$", byte_range):
                raise ValueError(f"The value of byte_range is unrecognized: '{byte_range}'")
            start, end = byte_range.split("-")
            if start > end:
                raise ValueError(f"The start range cannot be greater than the end range: {start}>{end}")
        else:
            size_test = session.head(url)
            if "Content-Length" in size_test.headers:
                content_length_header = int(size_test.headers["Content-Length"])
                if content_length_header > 0:
                    content_length = min(content_length_header, maximum_size)
            range_test = session.head(url, headers={"Range": "bytes=0-1"})
            if range_test.status_code == 206:
                byte_range = f"0-{content_length-1}"

        if byte_range:
            res = session.get(
                url=url,
                headers={
                    "Range": f"bytes={byte_range}"
                }
            )
            res.raise_for_status()
            init_data = res.content
        else:
            init_data = None
            with session.get(url, stream=True) as s:
                for chunk in s.iter_content(content_length):
                    init_data = chunk
                    break
            if not init_data:
                raise ValueError(f"Failed to read {content_length} bytes from the track URI.")

        return init_data

    def delete(self) -> None:
        if self.path:
            self.path.unlink()
            self.path = None

    def repackage(self) -> None:
        if not self.path or not self.path.exists():
            raise ValueError("Cannot repackage a Track that has not been downloaded.")

        executable = get_binary_path("ffmpeg")
        if not executable:
            raise EnvironmentError("FFmpeg executable \"ffmpeg\" was not found but is required for this call.")

        original_path = self.path
        output_path = original_path.with_stem(f"{original_path.stem}_repack")

        def _ffmpeg(extra_args: list[str] = None):
            subprocess.run(
                [
                    executable, "-hide_banner",
                    "-loglevel", "error",
                    "-i", original_path,
                    *(extra_args or []),
                    # Following are very important!
                    "-map_metadata", "-1",  # don't transfer metadata to output file
                    "-fflags", "bitexact",  # only have minimal tag data, reproducible mux
                    "-codec", "copy",
                    str(output_path)
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

        try:
            _ffmpeg()
        except subprocess.CalledProcessError as e:
            if b"Malformed AAC bitstream detected" in e.stderr:
                # e.g., TruTV's dodgy encodes
                _ffmpeg(["-y", "-bsf:a", "aac_adtstoasc"])
            else:
                raise

        self.path = output_path

    def move(self, target: Union[Path, str]) -> bool:
        """
        Move the Track's file from current location, to target location.
        This will overwrite anything at the target path.

        Raises:
            TypeError: If the target argument is not the expected type.

        Returns True if the move succeeded, or False if there was no file to move, or
        the file failed to move.
        """
        if not isinstance(target, (str, Path)):
            raise TypeError(f"Expected {target} to be a {Path} or {str}, not {type(target)}")

        if not self.path:
            return False

        if not isinstance(target, Path):
            target = Path(target)

        moved_to = Path(shutil.move(self.path, target))
        success = moved_to.resolve() == target.resolve()

        if success:
            self.path = target

        return success


__all__ = ("Track",)
