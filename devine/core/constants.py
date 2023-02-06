import logging
from typing import TypeVar, Union


LOG_FORMAT = "{asctime} [{levelname[0]}] {name} : {message}"  # must be '{}' style
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FORMATTER = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT, "{")
DRM_SORT_MAP = ["ClearKey", "Widevine"]
LANGUAGE_MUX_MAP = {
    # List of language tags that cannot be used by mkvmerge and need replacements.
    # Try get the replacement to be as specific locale-wise as possible.
    # A bcp47 as the replacement is recommended.
    "cmn": "zh",
    "cmn-Hant": "zh-Hant",
    "cmn-Hans": "zh-Hans",
    "none": "und",
    "yue": "zh-yue",
    "yue-Hant": "zh-yue-Hant",
    "yue-Hans": "zh-yue-Hans"
}
TERRITORY_MAP = {
    "Hong Kong SAR China": "Hong Kong"
}
LANGUAGE_MAX_DISTANCE = 5  # this is max to be considered "same", e.g., en, en-US, en-AU
VIDEO_CODEC_MAP = {
    "AVC": "H.264",
    "HEVC": "H.265"
}
DYNAMIC_RANGE_MAP = {
    "HDR10": "HDR",
    "HDR10+": "HDR",
    "Dolby Vision": "DV"
}
AUDIO_CODEC_MAP = {
    "E-AC-3": "DDP",
    "AC-3": "DD"
}

context_settings = dict(
    help_option_names=["-?", "-h", "--help"],  # default only has --help
    max_content_width=116,  # max PEP8 line-width, -4 to adjust for initial indent
)

# For use in signatures of functions which take one specific type of track at a time
# (it can't be a list that contains e.g. both Video and Audio objects)
TrackT = TypeVar("TrackT", bound="Track")  # noqa: F821

# For general use in lists that can contain mixed types of tracks.
# list[Track] won't work because list is invariant.
# TODO: Add Chapter?
AnyTrack = Union["Video", "Audio", "Subtitle"]  # noqa: F821
