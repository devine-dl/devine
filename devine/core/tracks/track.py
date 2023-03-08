import re
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union

import requests
from langcodes import Language

from devine.core.constants import TERRITORY_MAP
from devine.core.drm import DRM_T
from devine.core.utilities import get_binary_path


class Track:
    class DRM(Enum):
        pass

    class Descriptor(Enum):
        URL = 1  # Direct URL, nothing fancy
        M3U = 2  # https://en.wikipedia.org/wiki/M3U (and M3U8)
        MPD = 3  # https://en.wikipedia.org/wiki/Dynamic_Adaptive_Streaming_over_HTTP

    def __init__(
        self,
        id_: str,
        url: Union[str, list[str]],
        language: Union[Language, str],
        is_original_lang: bool = False,
        descriptor: Descriptor = Descriptor.URL,
        needs_proxy: bool = False,
        needs_repack: bool = False,
        drm: Optional[Iterable[DRM_T]] = None,
        edition: Optional[str] = None,
        extra: Optional[Any] = None
    ) -> None:
        self.id = id_
        self.url = url
        # required basic metadata
        self.language = Language.get(language)
        self.is_original_lang = bool(is_original_lang)
        # optional io metadata
        self.descriptor = descriptor
        self.needs_proxy = bool(needs_proxy)
        self.needs_repack = bool(needs_repack)
        # drm
        self.drm = drm
        # extra data
        self.edition: str = edition
        self.extra: Any = extra or {}  # allow anything for extra, but default to a dict

        # events
        self.OnSegmentFilter: Optional[Callable] = None
        self.OnDownloaded: Optional[Callable] = None
        self.OnDecrypted: Optional[Callable] = None
        self.OnRepacked: Optional[Callable] = None
        self.OnMultiplex: Optional[Callable] = None

        # should only be set internally
        self.path: Optional[Path] = None

    def __repr__(self) -> str:
        return "{name}({items})".format(
            name=self.__class__.__name__,
            items=", ".join([f"{k}={repr(v)}" for k, v in self.__dict__.items()])
        )

    def __eq__(self, other: object) -> bool:
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

    def get_init_segment(
        self,
        fallback_size: int = 20000,
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
        override this by changing the `fallback_size`.

        The default fallback_size of 20000 (20KB) is a tried-and-tested value that
        seems to work well across the board.

        Parameters:
            fallback_size: Size to assume as the content length if byte-range is not
                used and the content size could not be determined. 20000 (20KB) or
                higher is recommended.
            url: Explicit init map or file URL to probe from.
            byte_range: Range of bytes to download from the explicit or implicit URL.
            session: Session context, e.g., authorization and headers.
        """
        if not session:
            session = requests.Session()

        if self.descriptor != self.Descriptor.URL and not url:
            # We cannot know which init map from the HLS or DASH playlist is actually used.
            # For DASH this could be from any adaptation set, any period, e.t.c.
            # For HLS we could make some assumptions, but it's best that it is explicitly provided.
            raise ValueError(
                f"An explicit URL to an init map or file must be provided for {self.descriptor.name} tracks."
            )

        url = url or self.url
        if not url:
            raise ValueError("The track must have an URL to point towards it's data.")

        content_length = fallback_size

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
                content_length = int(size_test.headers['Content-Length'])
            range_test = session.head(url, headers={"Range": "bytes=0-1"})
            if range_test.status_code == 206:
                if content_length < 100000:  # 100KB limit
                    # if it supports it, and is less than 100KB, use byte-range
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
            # Take advantage of streaming support to take just the first n bytes
            # This is a hacky alternative to HTTP's Range on unsupported servers
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

        repacked_path = self.path.with_suffix(f".repack{self.path.suffix}")

        def _ffmpeg(extra_args: list[str] = None):
            subprocess.run(
                [
                    executable, "-hide_banner",
                    "-loglevel", "error",
                    "-i", self.path,
                    *(extra_args or []),
                    # Following are very important!
                    "-map_metadata", "-1",  # don't transfer metadata to output file
                    "-fflags", "bitexact",  # only have minimal tag data, reproducible mux
                    "-codec", "copy",
                    str(repacked_path)
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

        self.swap(repacked_path)

    def move(self, target: Union[str, Path]) -> bool:
        """
        Move the Track's file from current location, to target location.
        This will overwrite anything at the target path.
        """
        if not self.path:
            return False
        target = Path(target)

        ok = Path(shutil.move(self.path, target)).resolve() == target.resolve()
        if ok:
            self.path = target
        return ok

    def swap(self, target: Union[str, Path]) -> bool:
        """
        Swaps the Track's file with the Target file. The current Track's file is deleted.
        Returns False if the Track is not yet downloaded, or the target path does not exist.
        """
        target = Path(target)
        if not target.exists() or not self.path:
            return False
        self.path.unlink()
        ok = Path(shutil.move(target, self.path)).resolve() == self.path.resolve()
        if not ok:
            return False
        return self.move(target)


__ALL__ = (Track,)
