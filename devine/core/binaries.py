import shutil
import sys
from pathlib import Path
from typing import Optional

__shaka_platform = {
    "win32": "win",
    "darwin": "osx"
}.get(sys.platform, sys.platform)


def find(*names: str) -> Optional[Path]:
    """Find the path of the first found binary name."""
    for name in names:
        path = shutil.which(name)
        if path:
            return Path(path)
    return None


FFMPEG = find("ffmpeg")
FFProbe = find("ffprobe")
FFPlay = find("ffplay")
SubtitleEdit = find("SubtitleEdit")
ShakaPackager = find(
    "shaka-packager",
    "packager",
    f"packager-{__shaka_platform}",
    f"packager-{__shaka_platform}-arm64",
    f"packager-{__shaka_platform}-x64"
)
Aria2 = find("aria2c", "aria2")
CCExtractor = find(
    "ccextractor",
    "ccextractorwin",
    "ccextractorwinfull"
)
HolaProxy = find("hola-proxy")
MPV = find("mpv")
Caddy = find("caddy")


__all__ = (
    "FFMPEG", "FFProbe", "FFPlay", "SubtitleEdit", "ShakaPackager",
    "Aria2", "CCExtractor", "HolaProxy", "MPV", "Caddy", "find"
)
