import os
import subprocess
import textwrap
import time
from functools import partial
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Callable, Generator, MutableMapping, Optional, Union
from urllib.parse import urlparse

import requests
from Crypto.Random import get_random_bytes
from requests import Session
from requests.cookies import cookiejar_from_dict, get_cookie_header
from rich import filesize
from rich.text import Text

from devine.core.config import config
from devine.core.console import console
from devine.core.constants import DOWNLOAD_CANCELLED
from devine.core.utilities import get_binary_path, get_extension, get_free_port


def rpc(caller: Callable, secret: str, method: str, params: Optional[list[Any]] = None) -> Any:
    """Make a call to Aria2's JSON-RPC API."""
    try:
        rpc_res = caller(
            json={
                "jsonrpc": "2.0",
                "id": get_random_bytes(16).hex(),
                "method": method,
                "params": [f"token:{secret}", *(params or [])]
            }
        ).json()
        if rpc_res.get("code"):
            # wrap to console width - padding - '[Aria2c]: '
            error_pretty = "\n          ".join(textwrap.wrap(
                f"RPC Error: {rpc_res['message']} ({rpc_res['code']})".strip(),
                width=console.width - 20,
                initial_indent=""
            ))
            console.log(Text.from_ansi("\n[Aria2c]: " + error_pretty))
        return rpc_res["result"]
    except requests.exceptions.ConnectionError:
        # absorb, process likely ended as it was calling RPC
        return


def download(
    urls: Union[str, list[str], dict[str, Any], list[dict[str, Any]]],
    output_dir: Path,
    filename: str,
    headers: Optional[MutableMapping[str, Union[str, bytes]]] = None,
    cookies: Optional[Union[MutableMapping[str, str], CookieJar]] = None,
    proxy: Optional[str] = None,
    max_workers: Optional[int] = None
) -> Generator[dict[str, Any], None, None]:
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

    if not max_workers:
        max_workers = min(32, (os.cpu_count() or 1) + 4)
    elif not isinstance(max_workers, int):
        raise TypeError(f"Expected max_workers to be {int}, not {type(max_workers)}")

    if not isinstance(urls, list):
        urls = [urls]

    executable = get_binary_path("aria2c", "aria2")
    if not executable:
        raise EnvironmentError("Aria2c executable not found...")

    if proxy and not proxy.lower().startswith("http://"):
        raise ValueError("Only HTTP proxies are supported by aria2(c)")

    if cookies and not isinstance(cookies, CookieJar):
        cookies = cookiejar_from_dict(cookies)

    url_files = []
    for i, url in enumerate(urls):
        if isinstance(url, str):
            url_data = {
                "url": url
            }
        else:
            url_data: dict[str, Any] = url
        url_filename = filename.format(
            i=i,
            ext=get_extension(url_data["url"])
        )
        url_text = url_data["url"]
        url_text += f"\n\tdir={output_dir}"
        url_text += f"\n\tout={url_filename}"
        if cookies:
            mock_request = requests.Request(url=url_data["url"])
            cookie_header = get_cookie_header(cookies, mock_request)
            if cookie_header:
                url_text += f"\n\theader=Cookie: {cookie_header}"
        for key, value in url_data.items():
            if key == "url":
                continue
            if key == "headers":
                for header_name, header_value in value.items():
                    url_text += f"\n\theader={header_name}: {header_value}"
            else:
                url_text += f"\n\t{key}={value}"
        url_files.append(url_text)
    url_file = "\n".join(url_files)

    rpc_port = get_free_port()
    rpc_secret = get_random_bytes(16).hex()
    rpc_uri = f"http://127.0.0.1:{rpc_port}/jsonrpc"
    rpc_session = Session()

    max_concurrent_downloads = int(config.aria2c.get("max_concurrent_downloads", max_workers))
    max_connection_per_server = int(config.aria2c.get("max_connection_per_server", 1))
    split = int(config.aria2c.get("split", 5))
    file_allocation = config.aria2c.get("file_allocation", "prealloc")
    if len(urls) > 1:
        split = 1
        file_allocation = "none"

    arguments = [
        # [Basic Options]
        "--input-file", "-",
        "--all-proxy", proxy or "",
        "--continue=true",
        # [Connection Options]
        f"--max-concurrent-downloads={max_concurrent_downloads}",
        f"--max-connection-per-server={max_connection_per_server}",
        f"--split={split}",  # each split uses their own connection
        "--max-file-not-found=5",  # counted towards --max-tries
        "--max-tries=5",
        "--retry-wait=2",
        # [Advanced Options]
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--console-log-level=warn",
        "--download-result=default",
        f"--file-allocation={file_allocation}",
        "--summary-interval=0",
        # [RPC Options]
        "--enable-rpc=true",
        f"--rpc-listen-port={rpc_port}",
        f"--rpc-secret={rpc_secret}"
    ]

    for header, value in (headers or {}).items():
        if header.lower() == "cookie":
            raise ValueError("You cannot set Cookies as a header manually, please use the `cookies` param.")
        if header.lower() == "accept-encoding":
            # we cannot set an allowed encoding, or it will return compressed
            # and the code is not set up to uncompress the data
            continue
        if header.lower() == "referer":
            arguments.extend(["--referer", value])
            continue
        if header.lower() == "user-agent":
            arguments.extend(["--user-agent", value])
            continue
        arguments.extend(["--header", f"{header}: {value}"])

    yield dict(total=len(urls))

    try:
        p = subprocess.Popen(
            [
                executable,
                *arguments
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL
        )

        p.stdin.write(url_file.encode())
        p.stdin.close()

        while p.poll() is None:
            global_stats: dict[str, Any] = rpc(
                caller=partial(rpc_session.post, url=rpc_uri),
                secret=rpc_secret,
                method="aria2.getGlobalStat"
            ) or {}

            number_stopped = int(global_stats.get("numStoppedTotal", 0))
            download_speed = int(global_stats.get("downloadSpeed", -1))

            if number_stopped:
                yield dict(completed=number_stopped)
            if download_speed != -1:
                yield dict(downloaded=f"{filesize.decimal(download_speed)}/s")

            stopped_downloads: list[dict[str, Any]] = rpc(
                caller=partial(rpc_session.post, url=rpc_uri),
                secret=rpc_secret,
                method="aria2.tellStopped",
                params=[0, 999999]
            ) or []

            for dl in stopped_downloads:
                if dl["status"] == "error":
                    used_uri = next(
                        uri["uri"]
                        for file in dl["files"]
                        if file["selected"] == "true"
                        for uri in file["uris"]
                        if uri["status"] == "used"
                    )
                    error = f"Download Error (#{dl['gid']}): {dl['errorMessage']} ({dl['errorCode']}), {used_uri}"
                    error_pretty = "\n          ".join(textwrap.wrap(
                        error,
                        width=console.width - 20,
                        initial_indent=""
                    ))
                    console.log(Text.from_ansi("\n[Aria2c]: " + error_pretty))
                    raise ValueError(error)

            if number_stopped == len(urls):
                rpc(
                    caller=partial(rpc_session.post, url=rpc_uri),
                    secret=rpc_secret,
                    method="aria2.shutdown"
                )
                break

            time.sleep(1)

        p.wait()

        if p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, arguments)
    except ConnectionResetError:
        # interrupted while passing URI to download
        raise KeyboardInterrupt()
    except subprocess.CalledProcessError as e:
        if e.returncode in (7, 0xC000013A):
            # 7 is when Aria2(c) handled the CTRL+C
            # 0xC000013A is when it never got the chance to
            raise KeyboardInterrupt()
        raise
    except KeyboardInterrupt:
        DOWNLOAD_CANCELLED.set()  # skip pending track downloads
        yield dict(downloaded="[yellow]CANCELLED")
        raise
    except Exception:
        DOWNLOAD_CANCELLED.set()  # skip pending track downloads
        yield dict(downloaded="[red]FAILED")
        raise
    finally:
        rpc(
            caller=partial(rpc_session.post, url=rpc_uri),
            secret=rpc_secret,
            method="aria2.shutdown"
        )


def aria2c(
    urls: Union[str, list[str], dict[str, Any], list[dict[str, Any]]],
    output_dir: Path,
    filename: str,
    headers: Optional[MutableMapping[str, Union[str, bytes]]] = None,
    cookies: Optional[Union[MutableMapping[str, str], CookieJar]] = None,
    proxy: Optional[str] = None,
    max_workers: Optional[int] = None
) -> Generator[dict[str, Any], None, None]:
    """
    Download files using Aria2(c).
    https://aria2.github.io

    Yields the following download status updates while chunks are downloading:

    - {total: 100} (100% download total)
    - {completed: 1} (1% download progress out of 100%)
    - {downloaded: "10.1 MB/s"} (currently downloading at a rate of 10.1 MB/s)

    The data is in the same format accepted by rich's progress.update() function.

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
            min(32,(cpu_count+4)). Use for the --max-concurrent-downloads option.
    """
    if proxy and not proxy.lower().startswith("http://"):
        # Only HTTP proxies are supported by aria2(c)
        proxy = urlparse(proxy)

        port = get_free_port()
        username, password = get_random_bytes(8).hex(), get_random_bytes(8).hex()
        local_proxy = f"http://{username}:{password}@localhost:{port}"

        scheme = {
            "https": "http+ssl",
            "socks5h": "socks"
        }.get(proxy.scheme, proxy.scheme)

        remote_server = f"{scheme}://{proxy.hostname}"
        if proxy.port:
            remote_server += f":{proxy.port}"
        if proxy.username or proxy.password:
            remote_server += "#"
        if proxy.username:
            remote_server += proxy.username
        if proxy.password:
            remote_server += f":{proxy.password}"

        p = subprocess.Popen(
            [
                "pproxy",
                "-l", f"http://:{port}#{username}:{password}",
                "-r", remote_server
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            yield from download(urls, output_dir, filename, headers, cookies, local_proxy, max_workers)
        finally:
            p.kill()
            p.wait()
        return
    yield from download(urls, output_dir, filename, headers, cookies, proxy, max_workers)


__all__ = ("aria2c",)
