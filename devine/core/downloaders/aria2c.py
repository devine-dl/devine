import asyncio
import subprocess
from pathlib import Path
from typing import Union, Optional

from devine.core.config import config
from devine.core.utilities import get_binary_path, start_pproxy


async def aria2c(
    uri: Union[str, list[str]],
    out: Path,
    headers: Optional[dict] = None,
    proxy: Optional[str] = None
) -> int:
    """
    Download files using Aria2(c).
    https://aria2.github.io

    If multiple URLs are provided they will be downloaded in the provided order
    to the output directory. They will not be merged together.
    """
    segmented = False
    if isinstance(uri, list) and len(uri) == 1:
        uri = uri[0]
    if isinstance(uri, list):
        segmented = True
        uri = "\n".join([
            f"{url}\n"
            f"\tdir={out}\n"
            f"\tout={i:08}.mp4"
            for i, url in enumerate(uri)
        ])
        if out.is_file():
            raise ValueError("Provided multiple segments to download, expecting directory path")
    elif "\t" not in uri:
        uri = f"{uri}\n" \
              f"\tdir={out.parent}\n" \
              f"\tout={out.name}"

    executable = get_binary_path("aria2c", "aria2")
    if not executable:
        raise EnvironmentError("Aria2c executable not found...")

    arguments = [
        "-c",  # Continue downloading a partially downloaded file
        "--remote-time",  # Retrieve timestamp of the remote file from the and apply if available
        "-x", "16",  # The maximum number of connections to one server for each download
        "-j", "16",  # The maximum number of parallel downloads for every static (HTTP/FTP) URL
        "-s", ("1" if segmented else "16"),  # Download a file using N connections
        "--min-split-size", ("1024M" if segmented else "20M"),  # effectively disable split if segmented
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--retry-wait", "2",  # Set the seconds to wait between retries.
        "--max-tries", "5",
        "--max-file-not-found", "5",
        "--summary-interval", "0",
        "--file-allocation", config.aria2c.get("file_allocation", "falloc"),
        "--console-log-level", "warn",
        "--download-result", "hide",
        "-i", "-"
    ]

    for header, value in (headers or {}).items():
        if header.lower() == "accept-encoding":
            # we cannot set an allowed encoding, or it will return compressed
            # and the code is not set up to uncompress the data
            continue
        arguments.extend(["--header", f"{header}: {value}"])

    if proxy and proxy.lower().split(":")[0] != "http":
        # HTTPS proxies not supported by Aria2c.
        # Proxy the proxy via pproxy to access it as a HTTP proxy.
        async with start_pproxy(proxy) as pproxy_:
            return await aria2c(uri, out, headers, pproxy_)

    if proxy:
        arguments += ["--all-proxy", proxy]

    p = await asyncio.create_subprocess_exec(executable, *arguments, stdin=subprocess.PIPE)
    await p.communicate(uri.encode())
    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, arguments)

    return p.returncode


__ALL__ = (aria2c,)
