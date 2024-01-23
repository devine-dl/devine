import math
import time
from functools import partial
from pathlib import Path
from typing import Any, MutableMapping, Optional, Union

from requests import Session
from requests.cookies import RequestsCookieJar
from rich import filesize

from devine.core.constants import DOWNLOAD_CANCELLED

MAX_ATTEMPTS = 5
RETRY_WAIT = 2


def requests(
    uri: Union[str, list[str]],
    out: Path,
    headers: Optional[dict] = None,
    cookies: Optional[Union[MutableMapping[str, str], RequestsCookieJar]] = None,
    proxy: Optional[str] = None,
    progress: Optional[partial] = None,
    *_: Any,
    **__: Any
) -> int:
    """
    Download files using Python Requests.
    https://requests.readthedocs.io

    If multiple URLs are provided they will be downloaded in the provided order
    to the output directory. They will not be merged together.
    """
    if isinstance(uri, list) and len(uri) == 1:
        uri = uri[0]

    if isinstance(uri, list):
        if out.is_file():
            raise ValueError("Expecting out to be a Directory path not a File as multiple URLs were provided")
        uri = [
            (url, out / f"{i:08}.mp4")
            for i, url in enumerate(uri)
        ]
    else:
        uri = [(uri, out.parent / out.name)]

    session = Session()
    if headers:
        headers = {
            k: v
            for k, v in headers.items()
            if k.lower() != "accept-encoding"
        }
        session.headers.update(headers)
    if cookies:
        session.cookies.update(cookies)
    if proxy:
        session.proxies.update({"all": proxy})

    if progress:
        progress(total=len(uri))

    download_sizes = []
    last_speed_refresh = time.time()

    for url, out_path in uri:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        control_file = out_path.with_name(f"{out_path.name}.!dev")
        if control_file.exists():
            # consider the file corrupt if the control file exists
            # TODO: Design a control file format so we know how much of the file is missing
            out_path.unlink(missing_ok=True)
            control_file.unlink()
        elif out_path.exists():
            continue
        control_file.write_bytes(b"")

        attempts = 1
        try:
            while True:
                try:
                    stream = session.get(url, stream=True)
                    stream.raise_for_status()

                    if len(uri) == 1 and progress:
                        content_length = int(stream.headers.get("Content-Length", "0"))
                        if content_length > 0:
                            progress(total=math.ceil(content_length / 1024))

                    with open(out_path, "wb") as f:
                        written = 0
                        for chunk in stream.iter_content(chunk_size=1024):
                            download_size = len(chunk)
                            f.write(chunk)
                            written += download_size
                            if progress:
                                progress(advance=1)

                                now = time.time()
                                time_since = now - last_speed_refresh

                                download_sizes.append(download_size)
                                if time_since > 5 or download_size < 1024:
                                    data_size = sum(download_sizes)
                                    download_speed = data_size / (time_since or 1)
                                    progress(downloaded=f"{filesize.decimal(download_speed)}/s")
                                    last_speed_refresh = now
                                    download_sizes.clear()
                    break
                except Exception as e:
                    out_path.unlink(missing_ok=True)
                    if DOWNLOAD_CANCELLED.is_set() or attempts == MAX_ATTEMPTS:
                        raise e
                    time.sleep(RETRY_WAIT)
                    attempts += 1
        finally:
            control_file.unlink()

    return 0


__all__ = ("requests",)
