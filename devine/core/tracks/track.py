import re
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union

import m3u8
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

    def get_init_segment(self, session: Optional[requests.Session] = None) -> bytes:
        """
        Get the Track's Initial Segment Data Stream.
        If the Track URL is not detected to be an init segment, it will download
        up to the first 20,000 (20KB) bytes only.
        """
        if not session:
            session = requests.Session()

        url = None
        is_init_stream = False

        if self.descriptor == self.Descriptor.M3U:
            master = m3u8.loads(session.get(self.url).text, uri=self.url)
            for segment in master.segments:
                if not segment.init_section:
                    continue
                # skip any segment that would be skipped from the download
                # as we cant consider these a true initial segment
                if callable(self.OnSegmentFilter) and self.OnSegmentFilter(segment):
                    continue
                url = ("" if re.match("^https?://", segment.init_section.uri) else segment.init_section.base_uri)
                url += segment.init_section.uri
                is_init_stream = True
                break

        if not url:
            url = self.url

        if isinstance(url, list):
            url = url[0]
            is_init_stream = True

        if is_init_stream:
            return session.get(url).content

        # likely a full single-file download, get first 20k bytes
        with session.get(url, stream=True) as s:
            # assuming enough to contain the pssh/kid
            for chunk in s.iter_content(20000):
                # we only want the first chunk
                return chunk

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
