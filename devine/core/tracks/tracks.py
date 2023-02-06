from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable, Iterator, Optional, Sequence, Union

from Cryptodome.Random import get_random_bytes
from langcodes import Language, closest_supported_match

from devine.core.config import config
from devine.core.constants import LANGUAGE_MAX_DISTANCE, LANGUAGE_MUX_MAP, AnyTrack, TrackT
from devine.core.tracks.audio import Audio
from devine.core.tracks.track import Track
from devine.core.tracks.chapter import Chapter
from devine.core.tracks.subtitle import Subtitle
from devine.core.tracks.video import Video
from devine.core.utilities import sanitize_filename, is_close_match
from devine.core.utils.collections import as_list, flatten


class Tracks:
    """
    Video, Audio, Subtitle, and Chapter Track Store.
    It provides convenience functions for listing, sorting, and selecting tracks.
    """

    TRACK_ORDER_MAP = {
        Video: 0,
        Audio: 1,
        Subtitle: 2,
        Chapter: 3
    }

    def __init__(self, *args: Union[Tracks, list[Track], Track]):
        self.videos: list[Video] = []
        self.audio: list[Audio] = []
        self.subtitles: list[Subtitle] = []
        self.chapters: list[Chapter] = []

        if args:
            self.add(args)

    def __iter__(self) -> Iterator[AnyTrack]:
        return iter(as_list(self.videos, self.audio, self.subtitles))

    def __len__(self) -> int:
        return len(self.videos) + len(self.audio) + len(self.subtitles)

    def __repr__(self) -> str:
        return "{name}({items})".format(
            name=self.__class__.__name__,
            items=", ".join([f"{k}={repr(v)}" for k, v in self.__dict__.items()])
        )

    def __str__(self) -> str:
        rep = {
            Video: [],
            Audio: [],
            Subtitle: [],
            Chapter: []
        }
        tracks = [*list(self), *self.chapters]

        for track in sorted(tracks, key=lambda t: self.TRACK_ORDER_MAP[type(t)]):
            if not rep[type(track)]:
                count = sum(type(x) is type(track) for x in tracks)
                rep[type(track)].append("{count} {type} Track{plural}{colon}".format(
                    count=count,
                    type=track.__class__.__name__,
                    plural="s" if count != 1 else "",
                    colon=":" if count > 0 else ""
                ))
            rep[type(track)].append(str(track))

        for type_ in list(rep):
            if not rep[type_]:
                del rep[type_]
                continue
            rep[type_] = "\n".join(
                [rep[type_][0]] +
                [f"├─ {x}" for x in rep[type_][1:-1]] +
                [f"└─ {rep[type_][-1]}"]
            )
        rep = "\n".join(list(rep.values()))

        return rep

    def exists(self, by_id: Optional[str] = None, by_url: Optional[Union[str, list[str]]] = None) -> bool:
        """Check if a track already exists by various methods."""
        if by_id:  # recommended
            return any(x.id == by_id for x in self)
        if by_url:
            return any(x.url == by_url for x in self)
        return False

    def add(
        self,
        tracks: Union[Tracks, Sequence[Union[AnyTrack, Chapter]], Track, Chapter],
        warn_only: bool = False
    ) -> None:
        """Add a provided track to its appropriate array and ensuring it's not a duplicate."""
        if isinstance(tracks, Tracks):
            tracks = [*list(tracks), *tracks.chapters]

        duplicates = 0
        for track in flatten(tracks):
            if self.exists(by_id=track.id):
                if not warn_only:
                    raise ValueError(
                        "One or more of the provided Tracks is a duplicate. "
                        "Track IDs must be unique but accurate using static values. The "
                        "value should stay the same no matter when you request the same "
                        "content. Use a value that has relation to the track content "
                        "itself and is static or permanent and not random/RNG data that "
                        "wont change each refresh or conflict in edge cases."
                    )
                duplicates += 1
                continue

            if isinstance(track, Video):
                self.videos.append(track)
            elif isinstance(track, Audio):
                self.audio.append(track)
            elif isinstance(track, Subtitle):
                self.subtitles.append(track)
            elif isinstance(track, Chapter):
                self.chapters.append(track)
            else:
                raise ValueError("Track type was not set or is invalid.")

        log = logging.getLogger("Tracks")

        if duplicates:
            log.warning(f" - Found and skipped {duplicates} duplicate tracks...")

    def print(self, level: int = logging.INFO) -> None:
        """Print the __str__ to log at a specified level."""
        log = logging.getLogger("Tracks")
        for line in str(self).splitlines(keepends=False):
            log.log(level, line)

    def sort_videos(self, by_language: Optional[Sequence[Union[str, Language]]] = None) -> None:
        """Sort video tracks by bitrate, and optionally language."""
        if not self.videos:
            return
        # bitrate
        self.videos.sort(
            key=lambda x: float(x.bitrate or 0.0),
            reverse=True
        )
        # language
        for language in reversed(by_language or []):
            if str(language) == "all":
                language = next((x.language for x in self.videos if x.is_original_lang), "")
            if not language:
                continue
            self.videos.sort(key=lambda x: str(x.language))
            self.videos.sort(key=lambda x: not is_close_match(language, [x.language]))

    def sort_audio(self, by_language: Optional[Sequence[Union[str, Language]]] = None) -> None:
        """Sort audio tracks by bitrate, descriptive, and optionally language."""
        if not self.audio:
            return
        # bitrate
        self.audio.sort(
            key=lambda x: float(x.bitrate or 0.0),
            reverse=True
        )
        # descriptive
        self.audio.sort(key=lambda x: str(x.language) if x.descriptive else "")
        # language
        for language in reversed(by_language or []):
            if str(language) == "all":
                language = next((x.language for x in self.audio if x.is_original_lang), "")
            if not language:
                continue
            self.audio.sort(key=lambda x: str(x.language))
            self.audio.sort(key=lambda x: not is_close_match(language, [x.language]))

    def sort_subtitles(self, by_language: Optional[Sequence[Union[str, Language]]] = None) -> None:
        """
        Sort subtitle tracks by various track attributes to a common P2P standard.
        You may optionally provide a sequence of languages to prioritize to the top.

        Section Order:
          - by_language groups prioritized to top, and ascending alphabetically
          - then rest ascending alphabetically after the prioritized groups
          (Each section ascending alphabetically, but separated)

        Language Group Order:
          - Forced
          - Normal
          - Hard of Hearing (SDH/CC)
          (Least to most captions expected in the subtitle)
        """
        if not self.subtitles:
            return
        # language groups
        self.subtitles.sort(key=lambda x: str(x.language))
        self.subtitles.sort(key=lambda x: x.sdh or x.cc)
        self.subtitles.sort(key=lambda x: x.forced, reverse=True)
        # sections
        for language in reversed(by_language or []):
            if str(language) == "all":
                language = next((x.language for x in self.subtitles if x.is_original_lang), "")
            if not language:
                continue
            self.subtitles.sort(key=lambda x: is_close_match(language, [x.language]), reverse=True)

    def sort_chapters(self) -> None:
        """Sort chapter tracks by chapter number."""
        if not self.chapters:
            return
        # number
        self.chapters.sort(key=lambda x: x.number)

    def select_video(self, x: Callable[[Video], bool]) -> None:
        self.videos = list(filter(x, self.videos))

    def select_audio(self, x: Callable[[Audio], bool]) -> None:
        self.audio = list(filter(x, self.audio))

    def select_subtitles(self, x: Callable[[Subtitle], bool]) -> None:
        self.subtitles = list(filter(x, self.subtitles))

    def with_resolution(self, resolution: int) -> None:
        if resolution:
            # Note: Do not merge these list comprehensions. They must be done separately so the results
            # from the 16:9 canvas check is only used if there's no exact height resolution match.
            videos_quality = [x for x in self.videos if x.height == resolution]
            if not videos_quality:
                videos_quality = [x for x in self.videos if int(x.width * (9 / 16)) == resolution]
            self.videos = videos_quality

    def export_chapters(self, to_file: Optional[Union[Path, str]] = None) -> str:
        """Export all chapters in order to a string or file."""
        self.sort_chapters()
        data = "\n".join(map(repr, self.chapters))
        if to_file:
            to_file = Path(to_file)
            to_file.parent.mkdir(parents=True, exist_ok=True)
            to_file.write_text(data, encoding="utf8")
        return data

    @staticmethod
    def select_per_language(tracks: list[TrackT], languages: list[str]) -> list[TrackT]:
        """
        Enumerates and return the first Track per language.
        You should sort the list so the wanted track is closer to the start of the list.
        """
        tracks_ = []
        for language in languages:
            match = closest_supported_match(language, [str(x.language) for x in tracks], LANGUAGE_MAX_DISTANCE)
            if match:
                tracks_.append(next(x for x in tracks if str(x.language) == match))
        return tracks_

    def mux(self, title: str, delete: bool = True) -> tuple[Path, int]:
        """
        Takes the Video, Audio and Subtitle Tracks, and muxes them into an MKV file.
        It will attempt to detect Forced/Default tracks, and will try to parse the language codes of the Tracks
        """
        cl = [
            "mkvmerge",
            "--no-date",  # remove dates from the output for security
        ]

        if config.muxing.get("set_title", True):
            cl.extend(["--title", title])

        for i, vt in enumerate(self.videos):
            if not vt.path or not vt.path.exists():
                raise ValueError("Video Track must be downloaded before muxing...")
            cl.extend([
                "--language", "0:{}".format(LANGUAGE_MUX_MAP.get(
                    str(vt.language), str(vt.language)
                )),
                "--default-track", f"0:{i == 0}",
                "--original-flag", f"0:{vt.is_original_lang}",
                "--compression", "0:none",  # disable extra compression
                "(", str(vt.path), ")"
            ])

        for i, at in enumerate(self.audio):
            if not at.path or not at.path.exists():
                raise ValueError("Audio Track must be downloaded before muxing...")
            cl.extend([
                "--track-name", f"0:{at.get_track_name() or ''}",
                "--language", "0:{}".format(LANGUAGE_MUX_MAP.get(
                    str(at.language), str(at.language)
                )),
                "--default-track", f"0:{i == 0}",
                "--visual-impaired-flag", f"0:{at.descriptive}",
                "--original-flag", f"0:{at.is_original_lang}",
                "--compression", "0:none",  # disable extra compression
                "(", str(at.path), ")"
            ])

        for st in self.subtitles:
            if not st.path or not st.path.exists():
                raise ValueError("Text Track must be downloaded before muxing...")
            default = bool(self.audio and is_close_match(st.language, [self.audio[0].language]) and st.forced)
            cl.extend([
                "--track-name", f"0:{st.get_track_name() or ''}",
                "--language", "0:{}".format(LANGUAGE_MUX_MAP.get(
                    str(st.language), str(st.language)
                )),
                "--sub-charset", "0:UTF-8",
                "--forced-track", f"0:{st.forced}",
                "--default-track", f"0:{default}",
                "--hearing-impaired-flag", f"0:{st.sdh}",
                "--original-flag", f"0:{st.is_original_lang}",
                "--compression", "0:none",  # disable extra compression (probably zlib)
                "(", str(st.path), ")"
            ])

        if self.chapters:
            chapters_path = config.directories.temp / config.filenames.chapters.format(
                title=sanitize_filename(title),
                random=get_random_bytes(16).hex()
            )
            self.export_chapters(chapters_path)
            cl.extend(["--chapters", str(chapters_path)])
        else:
            chapters_path = None

        output_path = (
            self.videos[0].path.with_suffix(".muxed.mkv") if self.videos else
            self.audio[0].path.with_suffix(".muxed.mka") if self.audio else
            self.subtitles[0].path.with_suffix(".muxed.mks") if self.subtitles else
            chapters_path.with_suffix(".muxed.mkv") if self.chapters else
            None
        )
        if not output_path:
            raise ValueError("No tracks provided, at least one track must be provided.")

        # let potential failures go to caller, caller should handle
        try:
            p = subprocess.run([
                *cl,
                "--output", str(output_path)
            ])
            return output_path, p.returncode
        finally:
            if chapters_path:
                # regardless of delete param, we delete as it's a file we made during muxing
                chapters_path.unlink()
            if delete:
                for track in self:
                    track.delete()


__ALL__ = (Tracks,)
