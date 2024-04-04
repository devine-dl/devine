import math
import os
import time
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Generator, MutableMapping, Optional, Union

from requests import Session
from requests.adapters import HTTPAdapter
from rich import filesize

from devine.core.constants import DOWNLOAD_CANCELLED
from devine.core.utilities import get_extension

MAX_ATTEMPTS = 5
RETRY_WAIT = 2
CHUNK_SIZE = 1024
PROGRESS_WINDOW = 5

DOWNLOAD_SIZES = []
LAST_SPEED_REFRESH = time.time()

def download(
    url: str,
    save_path: Path,
    session: Optional[Session] = None,
    segmented: bool = False,
    **kwargs: Any
) -> Generator[dict[str, Any], None, None]:
    """
    Download a file using Python Requests.
    https://requests.readthedocs.io

    Yields the following download status updates while chunks are downloading:

    - {total: 123} (there are 123 chunks to download)
    - {total: None} (there are an unknown number of chunks to download)
    - {advance: 1} (one chunk was downloaded)
    - {downloaded: "10.1 MB/s"} (currently downloading at a rate of 10.1 MB/s)
    - {file_downloaded: Path(...), written: 1024} (download finished, has the save path and size)

    The data is in the same format accepted by rich's progress.update() function. The
    `downloaded` key is custom and is not natively accepted by all rich progress bars.

    Parameters:
        url: Web URL of a file to download.
        save_path: The path to save the file to. If the save path's directory does not
            exist then it will be made automatically.
        session: The Requests Session to make HTTP requests with. Useful to set Header,
            Cookie, and Proxy data. Connections are saved and re-used with the session
            so long as the server keeps the connection alive.
        segmented: If downloads are segments or parts of one bigger file.
        kwargs: Any extra keyword arguments to pass to the session.get() call. Use this
            for one-time request changes like a header, cookie, or proxy. For example,
            to request Byte-ranges use e.g., `headers={"Range": "bytes=0-128"}`.
    """
    global LAST_SPEED_REFRESH

    session = session or Session()

    save_dir = save_path.parent
    control_file = save_path.with_name(f"{save_path.name}.!dev")

    save_dir.mkdir(parents=True, exist_ok=True)

    if control_file.exists():
        # consider the file corrupt if the control file exists
        save_path.unlink(missing_ok=True)
        control_file.unlink()
    elif save_path.exists():
        # if it exists, and no control file, then it should be safe
        yield dict(
            file_downloaded=save_path,
            written=save_path.stat().st_size
        )
        # TODO: This should return, potential recovery bug

    # TODO: Design a control file format so we know how much of the file is missing
    control_file.write_bytes(b"")

    attempts = 1
    try:
        while True:
            written = 0

            # these are for single-url speed calcs only
            download_sizes = []
            last_speed_refresh = time.time()

            try:
                stream = session.get(url, stream=True, **kwargs)
                stream.raise_for_status()

                if not segmented:
                    try:
                        content_length = int(stream.headers.get("Content-Length", "0"))
                    except ValueError:
                        content_length = 0

                    if content_length > 0:
                        yield dict(total=math.ceil(content_length / CHUNK_SIZE))
                    else:
                        # we have no data to calculate total chunks
                        yield dict(total=None)  # indeterminate mode

                with open(save_path, "wb") as f:
                    for chunk in stream.iter_content(chunk_size=CHUNK_SIZE):
                        download_size = len(chunk)
                        f.write(chunk)
                        written += download_size

                        if not segmented:
                            yield dict(advance=1)
                            now = time.time()
                            time_since = now - last_speed_refresh
                            download_sizes.append(download_size)
                            if time_since > PROGRESS_WINDOW or download_size < CHUNK_SIZE:
                                data_size = sum(download_sizes)
                                download_speed = math.ceil(data_size / (time_since or 1))
                                yield dict(downloaded=f"{filesize.decimal(download_speed)}/s")
                                last_speed_refresh = now
                                download_sizes.clear()

                yield dict(file_downloaded=save_path, written=written)

                if segmented:
                    yield dict(advance=1)
                    now = time.time()
                    time_since = now - LAST_SPEED_REFRESH
                    if written:  # no size == skipped dl
                        DOWNLOAD_SIZES.append(written)
                    if DOWNLOAD_SIZES and time_since > PROGRESS_WINDOW:
                        data_size = sum(DOWNLOAD_SIZES)
                        download_speed = math.ceil(data_size / (time_since or 1))
                        yield dict(downloaded=f"{filesize.decimal(download_speed)}/s")
                        LAST_SPEED_REFRESH = now
                        DOWNLOAD_SIZES.clear()
                break
            except Exception as e:
                save_path.unlink(missing_ok=True)
                if DOWNLOAD_CANCELLED.is_set() or attempts == MAX_ATTEMPTS:
                    raise e
                time.sleep(RETRY_WAIT)
                attempts += 1
    finally:
        control_file.unlink()


def requests(
    urls: Union[str, list[str], dict[str, Any], list[dict[str, Any]]],
    output_dir: Path,
    filename: str,
    headers: Optional[MutableMapping[str, Union[str, bytes]]] = None,
    cookies: Optional[Union[MutableMapping[str, str], CookieJar]] = None,
    proxy: Optional[str] = None,
    max_workers: Optional[int] = None
) -> Generator[dict[str, Any], None, None]:
    """
    Download a file using Python Requests.
    https://requests.readthedocs.io

    Yields the following download status updates while chunks are downloading:

    - {total: 123} (there are 123 chunks to download)
    - {total: None} (there are an unknown number of chunks to download)
    - {advance: 1} (one chunk was downloaded)
    - {downloaded: "10.1 MB/s"} (currently downloading at a rate of 10.1 MB/s)
    - {file_downloaded: Path(...), written: 1024} (download finished, has the save path and size)

    The data is in the same format accepted by rich's progress.update() function.
    However, The `downloaded`, `file_downloaded` and `written` keys are custom and not
    natively accepted by rich progress bars.

    Parameters:
        urls: Web URL(s) to file(s) to download. You can use a dictionary with the key
            "url" for the URI, and other keys for extra arguments to use per-URL.
        output_dir: The folder to save the file into. If the save path's directory does
            not exist then it will be made automatically.
        filename: The filename or filename template to use for each file. The variables
            you can use are `i` for the URL index and `ext` for the URL extension.
        headers: A mapping of HTTP Header Key/Values to use for all downloads.
        cookies: A mapping of Cookie Key/Values or a Cookie Jar to use for all downloads.
        proxy: An optional proxy URI to route connections through for all downloads.
        max_workers: The maximum amount of threads to use for downloads. Defaults to
            min(32,(cpu_count+4)).
    """
    if not urls:
        raise ValueError("urls must be provided and not empty")
    elif not isinstance(urls, (str, dict, list)):
        raise TypeError(f"Expected urls to be {str} or {dict} or a list of one of them, not {type(urls)}")

    if not output_dir:
        raise ValueError("output_dir must be provided")
    elif not isinstance(output_dir, Path):
        raise TypeError(f"Expected output_dir to be {Path}, not {type(output_dir)}")

    if not filename:
        raise ValueError("filename must be provided")
    elif not isinstance(filename, str):
        raise TypeError(f"Expected filename to be {str}, not {type(filename)}")

    if not isinstance(headers, (MutableMapping, type(None))):
        raise TypeError(f"Expected headers to be {MutableMapping}, not {type(headers)}")

    if not isinstance(cookies, (MutableMapping, CookieJar, type(None))):
        raise TypeError(f"Expected cookies to be {MutableMapping} or {CookieJar}, not {type(cookies)}")

    if not isinstance(proxy, (str, type(None))):
        raise TypeError(f"Expected proxy to be {str}, not {type(proxy)}")

    if not isinstance(max_workers, (int, type(None))):
        raise TypeError(f"Expected max_workers to be {int}, not {type(max_workers)}")

    if not isinstance(urls, list):
        urls = [urls]

    if not max_workers:
        max_workers = min(32, (os.cpu_count() or 1) + 4)

    urls = [
        dict(
            save_path=save_path,
            **url
        ) if isinstance(url, dict) else dict(
            url=url,
            save_path=save_path
        )
        for i, url in enumerate(urls)
        for save_path in [output_dir / filename.format(
            i=i,
            ext=get_extension(url["url"] if isinstance(url, dict) else url)
        )]
    ]

    session = Session()
    session.mount("https://", HTTPAdapter(
        pool_connections=max_workers,
        pool_maxsize=max_workers,
        pool_block=True
    ))
    session.mount("http://", session.adapters["https://"])

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

    yield dict(total=len(urls))

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for future in as_completed(
                pool.submit(
                    download,
                    session=session,
                    segmented=True,
                    **url
                )
                for url in urls
            ):
                try:
                    yield from future.result()
                except KeyboardInterrupt:
                    DOWNLOAD_CANCELLED.set()  # skip pending track downloads
                    yield dict(downloaded="[yellow]CANCELLING")
                    pool.shutdown(wait=True, cancel_futures=True)
                    yield dict(downloaded="[yellow]CANCELLED")
                    # tell dl that it was cancelled
                    # the pool is already shut down, so exiting loop is fine
                    raise
                except Exception:
                    DOWNLOAD_CANCELLED.set()  # skip pending track downloads
                    yield dict(downloaded="[red]FAILING")
                    pool.shutdown(wait=True, cancel_futures=True)
                    yield dict(downloaded="[red]FAILED")
                    # tell dl that it failed
                    # the pool is already shut down, so exiting loop is fine
                    raise
    finally:
        DOWNLOAD_SIZES.clear()


__all__ = ("requests",)
