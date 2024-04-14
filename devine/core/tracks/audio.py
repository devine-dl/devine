from __future__ import annotations

import math
from enum import Enum
from typing import Any, Optional, Union

from devine.core.tracks.track import Track


class Audio(Track):
    class Codec(str, Enum):
        AAC = "AAC"    # https://wikipedia.org/wiki/Advanced_Audio_Coding
        AC3 = "DD"     # https://wikipedia.org/wiki/Dolby_Digital
        EC3 = "DD+"    # https://wikipedia.org/wiki/Dolby_Digital_Plus
        OPUS = "OPUS"  # https://wikipedia.org/wiki/Opus_(audio_format)
        OGG = "VORB"   # https://wikipedia.org/wiki/Vorbis
        DTS = "DTS"    # https://en.wikipedia.org/wiki/DTS_(company)#DTS_Digital_Surround
        ALAC = "ALAC"  # https://en.wikipedia.org/wiki/Apple_Lossless_Audio_Codec
        FLAC = "FLAC"  # https://en.wikipedia.org/wiki/FLAC

        @property
        def extension(self) -> str:
            return self.name.lower()

        @staticmethod
        def from_mime(mime: str) -> Audio.Codec:
            mime = mime.lower().strip().split(".")[0]
            if mime == "mp4a":
                return Audio.Codec.AAC
            if mime == "ac-3":
                return Audio.Codec.AC3
            if mime == "ec-3":
                return Audio.Codec.EC3
            if mime == "opus":
                return Audio.Codec.OPUS
            if mime == "dtsc":
                return Audio.Codec.DTS
            if mime == "alac":
                return Audio.Codec.ALAC
            if mime == "flac":
                return Audio.Codec.FLAC
            raise ValueError(f"The MIME '{mime}' is not a supported Audio Codec")

        @staticmethod
        def from_codecs(codecs: str) -> Audio.Codec:
            for codec in codecs.lower().split(","):
                mime = codec.strip().split(".")[0]
                try:
                    return Audio.Codec.from_mime(mime)
                except ValueError:
                    pass
            raise ValueError(f"No MIME types matched any supported Audio Codecs in '{codecs}'")

        @staticmethod
        def from_netflix_profile(profile: str) -> Audio.Codec:
            profile = profile.lower().strip()
            if profile.startswith("heaac"):
                return Audio.Codec.AAC
            if profile.startswith("dd-"):
                return Audio.Codec.AC3
            if profile.startswith("ddplus"):
                return Audio.Codec.EC3
            if profile.startswith("playready-oggvorbis"):
                return Audio.Codec.OGG
            raise ValueError(f"The Content Profile '{profile}' is not a supported Audio Codec")

    def __init__(
        self,
        *args: Any,
        codec: Optional[Audio.Codec] = None,
        bitrate: Optional[Union[str, int, float]] = None,
        channels: Optional[Union[str, int, float]] = None,
        joc: Optional[int] = None,
        descriptive: Union[bool, int] = False,
        **kwargs: Any
    ):
        """
        Create a new Audio track object.

        Parameters:
            codec: An Audio.Codec enum representing the audio codec.
                If not specified, MediaInfo will be used to retrieve the codec
                once the track has been downloaded.
            bitrate: A number or float representing the average bandwidth in bytes/s.
                Float values are rounded up to the nearest integer.
            channels: A number, float, or string representing the number of audio channels.
                Strings may represent numbers or floats. Expanded layouts like 7.1.1 is
                not supported. All numbers and strings will be cast to float.
            joc: The number of Joint-Object-Coding Channels/Objects in the audio stream.
            descriptive: Mark this audio as being descriptive audio for the blind.

        Note: If codec, bitrate, channels, or joc is not specified some checks may be
        skipped or assume a value. Specifying as much information as possible is highly
        recommended.
        """
        super().__init__(*args, **kwargs)

        if not isinstance(codec, (Audio.Codec, type(None))):
            raise TypeError(f"Expected codec to be a {Audio.Codec}, not {codec!r}")
        if not isinstance(bitrate, (str, int, float, type(None))):
            raise TypeError(f"Expected bitrate to be a {str}, {int}, or {float}, not {bitrate!r}")
        if not isinstance(channels, (str, int, float, type(None))):
            raise TypeError(f"Expected channels to be a {str}, {int}, or {float}, not {channels!r}")
        if not isinstance(joc, (int, type(None))):
            raise TypeError(f"Expected joc to be a {int}, not {joc!r}")
        if (
            not isinstance(descriptive, (bool, int)) or
            (isinstance(descriptive, int) and descriptive not in (0, 1))
        ):
            raise TypeError(f"Expected descriptive to be a {bool} or bool-like {int}, not {descriptive!r}")

        self.codec = codec

        try:
            self.bitrate = int(math.ceil(float(bitrate))) if bitrate else None
        except (ValueError, TypeError) as e:
            raise ValueError(f"Expected bitrate to be a number or float, {e}")

        try:
            self.channels = self.parse_channels(channels) if channels else None
        except (ValueError, NotImplementedError) as e:
            raise ValueError(f"Expected channels to be a number, float, or a string, {e}")

        self.joc = joc
        self.descriptive = bool(descriptive)

    def __str__(self) -> str:
        return " | ".join(filter(bool, [
            "AUD",
            f"[{self.codec.value}]" if self.codec else None,
            str(self.language),
            ", ".join(filter(bool, [
                str(self.channels) if self.channels else None,
                f"JOC {self.joc}" if self.joc else None,
            ])),
            f"{self.bitrate // 1000} kb/s" if self.bitrate else None,
            self.get_track_name(),
            self.edition
        ]))

    @staticmethod
    def parse_channels(channels: Union[str, int, float]) -> float:
        """
        Converts a Channel string to a float representing audio channel count and layout.
        E.g. "3" -> "3.0", "2.1" -> "2.1", ".1" -> "0.1".

        This does not validate channel strings as genuine channel counts or valid layouts.
        It does not convert the value to assume a sub speaker channel layout, e.g. 5.1->6.0.
        It also does not support expanded surround sound channel layout strings like 7.1.2.
        """
        if isinstance(channels, str):
            # TODO: Support all possible DASH channel configurations (https://datatracker.ietf.org/doc/html/rfc8216)
            if channels.upper() == "A000":
                return 2.0
            elif channels.upper() == "F801":
                return 5.1
            elif channels.replace("ch", "").replace(".", "", 1).isdigit():
                # e.g., '2ch', '2', '2.0', '5.1ch', '5.1'
                return float(channels.replace("ch", ""))
            raise NotImplementedError(f"Unsupported Channels string value, '{channels}'")

        return float(channels)

    def get_track_name(self) -> Optional[str]:
        """Return the base Track Name."""
        track_name = super().get_track_name() or ""
        flag = self.descriptive and "Descriptive"
        if flag:
            if track_name:
                flag = f" ({flag})"
            track_name += flag
        return track_name or None


__all__ = ("Audio",)
