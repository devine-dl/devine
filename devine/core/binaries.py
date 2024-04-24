import sys

from devine.core.utilities import get_binary_path

__shaka_platform = {
    "win32": "win",
    "darwin": "osx"
}.get(sys.platform, sys.platform)

FFMPEG = get_binary_path("ffmpeg")
FFProbe = get_binary_path("ffprobe")
FFPlay = get_binary_path("ffplay")
SubtitleEdit = get_binary_path("SubtitleEdit")
ShakaPackager = get_binary_path(
    "shaka-packager",
    "packager",
    f"packager-{__shaka_platform}",
    f"packager-{__shaka_platform}-x64"
)
Aria2 = get_binary_path("aria2c", "aria2")
CCExtractor = get_binary_path(
    "ccextractor",
    "ccextractorwin",
    "ccextractorwinfull"
)
HolaProxy = get_binary_path("hola-proxy")
MPV = get_binary_path("mpv")
Caddy = get_binary_path("caddy")


__all__ = (
    "FFMPEG", "FFProbe", "FFPlay", "SubtitleEdit", "ShakaPackager",
    "Aria2", "CCExtractor", "HolaProxy", "MPV", "Caddy"
)
