import re
from abc import ABC
from collections import Counter
from typing import Any, Iterable, Optional, Union

from langcodes import Language
from pymediainfo import MediaInfo
from rich.tree import Tree
from sortedcontainers import SortedKeyList

from devine.core.config import config
from devine.core.constants import AUDIO_CODEC_MAP, DYNAMIC_RANGE_MAP, VIDEO_CODEC_MAP
from devine.core.titles.title import Title
from devine.core.utilities import sanitize_filename


class Episode(Title):
    def __init__(
        self,
        id_: Any,
        service: type,
        title: str,
        season: Union[int, str],
        number: Union[int, str],
        name: Optional[str] = None,
        year: Optional[Union[int, str]] = None,
        language: Optional[Union[str, Language]] = None,
        data: Optional[Any] = None,
    ) -> None:
        super().__init__(id_, service, language, data)

        if not title:
            raise ValueError("Episode title must be provided")
        if not isinstance(title, str):
            raise TypeError(f"Expected title to be a str, not {title!r}")

        if season != 0 and not season:
            raise ValueError("Episode season must be provided")
        if isinstance(season, str) and season.isdigit():
            season = int(season)
        elif not isinstance(season, int):
            raise TypeError(f"Expected season to be an int, not {season!r}")

        if number != 0 and not number:
            raise ValueError("Episode number must be provided")
        if isinstance(number, str) and number.isdigit():
            number = int(number)
        elif not isinstance(number, int):
            raise TypeError(f"Expected number to be an int, not {number!r}")

        if name is not None and not isinstance(name, str):
            raise TypeError(f"Expected name to be a str, not {name!r}")

        if year is not None:
            if isinstance(year, str) and year.isdigit():
                year = int(year)
            elif not isinstance(year, int):
                raise TypeError(f"Expected year to be an int, not {year!r}")

        title = title.strip()

        if name is not None:
            name = name.strip()
            # ignore episode names that are the episode number or title name
            if re.match(r"Episode ?#?\d+", name, re.IGNORECASE):
                name = None
            elif name.lower() == title.lower():
                name = None

        if year is not None and year <= 0:
            raise ValueError(f"Episode year cannot be {year}")

        self.title = title
        self.season = season
        self.number = number
        self.name = name
        self.year = year

    def __str__(self) -> str:
        return "{title} S{season:02}E{number:02} {name}".format(
            title=self.title,
            season=self.season,
            number=self.number,
            name=self.name or ""
        ).strip()

    def get_filename(self, media_info: MediaInfo, folder: bool = False, show_service: bool = True) -> str:
        primary_video_track = next(iter(media_info.video_tracks), None)
        primary_audio_track = next(iter(media_info.audio_tracks), None)
        unique_audio_languages = len({
            x.language.split("-")[0]
            for x in media_info.audio_tracks
            if x.language
        })

        # Title SXXEXX Name (or Title SXX if folder)
        if folder:
            name = f"{self.title} S{self.season:02}"
        else:
            name = "{title} S{season:02}E{number:02} {name}".format(
                title=self.title.replace("$", "S"),  # e.g., Arli$$
                season=self.season,
                number=self.number,
                name=self.name or ""
            ).strip()

        # MULTi
        if unique_audio_languages > 1:
            name += " MULTi"

        # Resolution
        if primary_video_track:
            resolution = primary_video_track.height
            aspect_ratio = [
                int(float(plane))
                for plane in primary_video_track.other_display_aspect_ratio[0].split(":")
            ]
            if len(aspect_ratio) == 1:
                # e.g., aspect ratio of 2 (2.00:1) would end up as `(2.0,)`, add 1
                aspect_ratio.append(1)
            if aspect_ratio[0] / aspect_ratio[1] not in (16 / 9, 4 / 3):
                # We want the resolution represented in a 4:3 or 16:9 canvas.
                # If it's not 4:3 or 16:9, calculate as if it's inside a 16:9 canvas,
                # otherwise the track's height value is fine.
                # We are assuming this title is some weird aspect ratio so most
                # likely a movie or HD source, so it's most likely widescreen so
                # 16:9 canvas makes the most sense.
                resolution = int(primary_video_track.width * (9 / 16))
            name += f" {resolution}p"

        # Service
        if show_service:
            name += f" {self.service.__name__}"

        # 'WEB-DL'
        name += " WEB-DL"

        # Audio Codec + Channels (+ feature)
        if primary_audio_track:
            codec = primary_audio_track.format
            channel_layout = primary_audio_track.channel_layout or primary_audio_track.channellayout_original
            channels = float(sum(
                {"LFE": 0.1}.get(position.upper(), 1)
                for position in channel_layout.split(" ")
            ))
            features = primary_audio_track.format_additionalfeatures or ""
            name += f" {AUDIO_CODEC_MAP.get(codec, codec)}{channels:.1f}"
            if "JOC" in features:
                name += " Atmos"

        # Video (dynamic range + hfr +) Codec
        if primary_video_track:
            codec = primary_video_track.format
            hdr_format = primary_video_track.hdr_format_commercial
            trc = primary_video_track.transfer_characteristics or primary_video_track.transfer_characteristics_original
            frame_rate = float(primary_video_track.frame_rate)
            if hdr_format:
                name += f" {DYNAMIC_RANGE_MAP.get(hdr_format)} "
            elif trc and "HLG" in trc:
                name += " HLG"
            if frame_rate > 30:
                name += " HFR"
            name += f" {VIDEO_CODEC_MAP.get(codec, codec)}"

        if config.tag:
            name += f"-{config.tag}"

        return sanitize_filename(name)


class Series(SortedKeyList, ABC):
    def __init__(self, iterable: Optional[Iterable] = None):
        super().__init__(
            iterable,
            key=lambda x: (x.season, x.number, x.year or 0)
        )

    def __str__(self) -> str:
        if not self:
            return super().__str__()
        return self[0].title + (f" ({self[0].year})" if self[0].year else "")

    def tree(self, verbose: bool = False) -> Tree:
        seasons = Counter(x.season for x in self)
        num_seasons = len(seasons)
        num_episodes = sum(seasons.values())
        tree = Tree(
            f"{num_seasons} Season{['s', ''][num_seasons == 1]}, {num_episodes} Episode{['s', ''][num_episodes == 1]}",
            guide_style="bright_black"
        )
        if verbose:
            for season, episodes in seasons.items():
                season_tree = tree.add(
                    f"[bold]Season {str(season).zfill(len(str(num_seasons)))}[/]: [bright_black]{episodes} episodes",
                    guide_style="bright_black"
                )
                for episode in self:
                    if episode.season == season:
                        if episode.name:
                            season_tree.add(
                                f"[bold]{str(episode.number).zfill(len(str(episodes)))}.[/] "
                                f"[bright_black]{episode.name}"
                            )
                        else:
                            season_tree.add(f"[bright_black]Episode {str(episode.number).zfill(len(str(episodes)))}")

        return tree


__all__ = ("Episode", "Series")
