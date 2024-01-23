import time
from functools import partial
from pathlib import Path
from typing import Any, MutableMapping, Optional, Union

from curl_cffi.requests import Session
from requests.cookies import RequestsCookieJar
from rich import filesize

from devine.core.config import config
from devine.core.constants import DOWNLOAD_CANCELLED

MAX_ATTEMPTS = 5
RETRY_WAIT = 2
BROWSER = config.curl_impersonate.get("browser", "chrome110")


def curl_impersonate(
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
    Download files using Curl Impersonate.
    https://github.com/lwthiker/curl-impersonate

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

    session = Session(impersonate=BROWSER)
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
        session.proxies.update({
            "http": proxy,
            "https": proxy
        })

    if progress:
        progress(total=len(uri))

    download_sizes = []
    last_speed_refresh = time.time()

    for url, out_path in uri:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        attempts = 1

        while True:
            try:
                stream = session.get(url, stream=True)
                stream.raise_for_status()
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
                if DOWNLOAD_CANCELLED.is_set() or attempts == MAX_ATTEMPTS:
                    raise e
                time.sleep(RETRY_WAIT)
                attempts += 1

    return 0


__all__ = ("curl_impersonate",)
