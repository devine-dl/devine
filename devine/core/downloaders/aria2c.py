import asyncio
import subprocess
import textwrap
from functools import partial
from http.cookiejar import CookieJar
from pathlib import Path
from typing import MutableMapping, Optional, Union

import requests
from requests.cookies import RequestsCookieJar, cookiejar_from_dict, get_cookie_header
from rich.text import Text

from devine.core.config import config
from devine.core.console import console
from devine.core.utilities import get_binary_path, start_pproxy


async def aria2c(
    uri: Union[str, list[str]],
    out: Path,
    headers: Optional[dict] = None,
    cookies: Optional[Union[MutableMapping[str, str], RequestsCookieJar]] = None,
    proxy: Optional[str] = None,
    silent: bool = False,
    segmented: bool = False,
    progress: Optional[partial] = None,
    *args: str
) -> int:
    """
    Download files using Aria2(c).
    https://aria2.github.io

    If multiple URLs are provided they will be downloaded in the provided order
    to the output directory. They will not be merged together.
    """
    if not isinstance(uri, list):
        uri = [uri]

    if cookies and not isinstance(cookies, CookieJar):
        cookies = cookiejar_from_dict(cookies)

    executable = get_binary_path("aria2c", "aria2")
    if not executable:
        raise EnvironmentError("Aria2c executable not found...")

    if proxy and proxy.lower().split(":")[0] != "http":
        # HTTPS proxies are not supported by aria2(c).
        # Proxy the proxy via pproxy to access it as an HTTP proxy.
        async with start_pproxy(proxy) as pproxy_:
            return await aria2c(uri, out, headers, cookies, pproxy_, silent, segmented, progress, *args)

    multiple_urls = len(uri) > 1
    url_files = []
    for i, url in enumerate(uri):
        url_text = url
        if multiple_urls:
            url_text += f"\n\tdir={out.parent}"
            url_text += f"\n\tout={out.name}"
        else:
            url_text += f"\n\tdir={out}"
            url_text += f"\n\tout={i:08}.mp4"
        if cookies:
            mock_request = requests.Request(url=url)
            cookie_header = get_cookie_header(cookies, mock_request)
            if cookie_header:
                url_text += f"\n\theader=Cookie: {cookie_header}"
        url_files.append(url_text)
    url_file = "\n".join(url_files)

    max_concurrent_downloads = int(config.aria2c.get("max_concurrent_downloads", 5))
    max_connection_per_server = int(config.aria2c.get("max_connection_per_server", 1))
    split = int(config.aria2c.get("split", 5))
    file_allocation = config.aria2c.get("file_allocation", "prealloc")
    if segmented:
        split = 1
        file_allocation = "none"

    arguments = [
        # [Basic Options]
        "--input-file", "-",
        "--out", out.name,
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
        f"--download-result={'default' if progress else 'hide'}",
        f"--file-allocation={file_allocation}",
        "--summary-interval=0",
        # [Extra Options]
        *args
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

    try:
        p = await asyncio.create_subprocess_exec(
            executable,
            *arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE
        )

        p.stdin.write(url_file.encode())
        await p.stdin.drain()
        p.stdin.close()

        if p.stdout:
            is_dl_summary = False
            log_buffer = ""
            while True:
                try:
                    chunk = await p.stdout.readuntil(b"\r")
                except asyncio.IncompleteReadError as e:
                    chunk = e.partial
                if not chunk:
                    break
                for line in chunk.decode().strip().splitlines():
                    if not line:
                        continue
                    if line.startswith("Download Results"):
                        # we know it's 100% downloaded, but let's use the avg dl speed value
                        is_dl_summary = True
                    elif line.startswith("[") and line.endswith("]"):
                        if progress and "%" in line:
                            # id, dledMiB/totalMiB(x%), CN:xx, DL:xxMiB, ETA:Xs
                            # eta may not always be available
                            data_parts = line[1:-1].split()
                            perc_parts = data_parts[1].split("(")
                            if len(perc_parts) == 2:
                                # might otherwise be e.g., 0B/0B, with no % symbol provided
                                progress(
                                    total=100,
                                    completed=int(perc_parts[1][:-2]),
                                    downloaded=f"{data_parts[3].split(':')[1]}/s"
                                )
                    elif is_dl_summary and "OK" in line and "|" in line:
                        gid, status, avg_speed, path_or_uri = line.split("|")
                        progress(total=100, completed=100, downloaded=avg_speed.strip())
                    elif not is_dl_summary:
                        if "aria2 will resume download if the transfer is restarted" in line:
                            continue
                        if "If there are any errors, then see the log file" in line:
                            continue
                        log_buffer += f"{line.strip()}\n"

            if log_buffer and not silent:
                # wrap to console width - padding - '[Aria2c]: '
                log_buffer = "\n          ".join(textwrap.wrap(
                    log_buffer.rstrip(),
                    width=console.width - 20,
                    initial_indent=""
                ))
                console.log(Text.from_ansi("\n[Aria2c]: " + log_buffer))

        await p.wait()

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

    return p.returncode


__all__ = ("aria2c",)
