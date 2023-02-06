import json
import subprocess
from pathlib import Path
from typing import Union


def ffprobe(uri: Union[bytes, Path]) -> dict:
    """Use ffprobe on the provided data to get stream information."""
    args = [
        "ffprobe",
        "-v", "quiet",
        "-of", "json",
        "-show_streams"
    ]
    if isinstance(uri, Path):
        args.extend([
            "-f", "lavfi",
            "-i", "movie={}[out+subcc]".format(str(uri).replace("\\", '/').replace(":", "\\\\:"))
        ])
    elif isinstance(uri, bytes):
        args.append("pipe:")
    try:
        ff = subprocess.run(
            args,
            input=uri if isinstance(uri, bytes) else None,
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError:
        return {}
    return json.loads(ff.stdout.decode("utf8"))
