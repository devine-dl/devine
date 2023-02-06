from abc import ABC
from typing import Any, Optional, Union, Iterable

from langcodes import Language
from pymediainfo import MediaInfo
from sortedcontainers import SortedKeyList

from devine.core.config import config
from devine.core.constants import AUDIO_CODEC_MAP
from devine.core.titles.title import Title
from devine.core.utilities import sanitize_filename


class Song(Title):
    def __init__(
        self,
        id_: Any,
        service: type,
        name: str,
        artist: str,
        album: str,
        track: int,
        disc: int,
        year: int,
        language: Optional[Union[str, Language]] = None,
        data: Optional[Any] = None,
    ) -> None:
        super().__init__(id_, service, language, data)

        if not name:
            raise ValueError("Song name must be provided")
        if not isinstance(name, str):
            raise TypeError(f"Expected name to be a str, not {name!r}")

        if not artist:
            raise ValueError("Song artist must be provided")
        if not isinstance(artist, str):
            raise TypeError(f"Expected artist to be a str, not {artist!r}")

        if not album:
            raise ValueError("Song album must be provided")
        if not isinstance(album, str):
            raise TypeError(f"Expected album to be a str, not {name!r}")

        if not track:
            raise ValueError("Song track must be provided")
        if not isinstance(track, int):
            raise TypeError(f"Expected track to be an int, not {track!r}")

        if not disc:
            raise ValueError("Song disc must be provided")
        if not isinstance(disc, int):
            raise TypeError(f"Expected disc to be an int, not {disc!r}")

        if not year:
            raise ValueError("Song year must be provided")
        if not isinstance(year, int):
            raise TypeError(f"Expected year to be an int, not {year!r}")

        name = name.strip()
        artist = artist.strip()
        album = album.strip()

        if track <= 0:
            raise ValueError(f"Song track cannot be {track}")
        if disc <= 0:
            raise ValueError(f"Song disc cannot be {disc}")
        if year <= 0:
            raise ValueError(f"Song year cannot be {year}")

        self.name = name
        self.artist = artist
        self.album = album
        self.track = track
        self.disc = disc
        self.year = year

    def __str__(self) -> str:
        return "{artist} - {album} ({year}) / {track:02}. {name}".format(
            artist=self.artist,
            album=self.album,
            year=self.year,
            track=self.track,
            name=self.name
        ).strip()

    def get_filename(self, media_info: MediaInfo, folder: bool = False, show_service: bool = True) -> str:
        audio_track = next(iter(media_info.audio_tracks), None)
        codec = audio_track.format
        channel_layout = audio_track.channel_layout or audio_track.channellayout_original
        channels = float(sum(
            {"LFE": 0.1}.get(position.upper(), 1)
            for position in channel_layout.split(" ")
        ))
        features = audio_track.format_additionalfeatures or ""

        if folder:
            # Artist - Album (Year)
            name = str(self).split(" / ")[0]
        else:
            # NN. Song Name
            name = str(self).split(" / ")[1]

        # Service
        if show_service:
            name += f" {self.service.__name__}"

        # 'WEB-DL'
        name += " WEB-DL"

        # Audio Codec + Channels (+ feature)
        name += f" {AUDIO_CODEC_MAP.get(codec, codec)}{channels:.1f}"
        if "JOC" in features:
            name += " Atmos"

        if config.tag:
            name += f"-{config.tag}"

        return sanitize_filename(name, " ")


class Album(SortedKeyList, ABC):
    def __init__(self, iterable: Optional[Iterable] = None):
        super().__init__(
            iterable,
            key=lambda x: (x.album, x.disc, x.track, x.year or 0)
        )

    def __str__(self) -> str:
        if not self:
            return super().__str__()

        lines = [
            f"Album: {self[0].album} ({self[0].year or '?'})",
            f"Artist: {self[0].artist}",
            f"Tracks: ({len(self)})",
            *[
                f"├─ {song.track:02}. {song.name}"
                for song in self
            ]
        ]
        last_line = lines.pop(-1)
        lines.append(last_line.replace("├", "└"))

        return "\n".join(lines)


__ALL__ = (Song, Album)
