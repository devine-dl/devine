import asyncio
import subprocess
import textwrap
from functools import partial
from pathlib import Path
from typing import Optional, Union

from rich.text import Text

from devine.core.config import config
from devine.core.console import console
from devine.core.utilities import get_binary_path, start_pproxy


async def aria2c(
    uri: Union[str, list[str]],
    out: Path,
    headers: Optional[dict] = None,
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
        "--file-allocation", [
            config.aria2c.get("file_allocation", "prealloc"),
            "none"
        ][segmented],
        "--console-log-level", "warn",
        "--download-result", ["hide", "default"][bool(progress)],
        *args,
        "-i", "-"
    ]

    for header, value in (headers or {}).items():
        if header.lower() == "accept-encoding":
            # we cannot set an allowed encoding, or it will return compressed
            # and the code is not set up to uncompress the data
            continue
        arguments.extend(["--header", f"{header}: {value}"])

    if proxy:
        if proxy.lower().split(":")[0] != "http":
            # HTTPS proxies are not supported by aria2(c).
            # Proxy the proxy via pproxy to access it as an HTTP proxy.
            async with start_pproxy(proxy) as pproxy_:
                return await aria2c(uri, out, headers, pproxy_, silent, segmented, progress, *args)
        arguments += ["--all-proxy", proxy]

    try:
        p = await asyncio.create_subprocess_exec(
            executable,
            *arguments,
            stdin=subprocess.PIPE,
            stdout=[subprocess.PIPE, subprocess.DEVNULL][silent]
        )

        p.stdin.write(uri.encode())
        await p.stdin.drain()
        p.stdin.close()

        if p.stdout:
            is_dl_summary = False
            aria_log_buffer = ""
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
                        aria_log_buffer += f"{line.strip()}\n"

            if aria_log_buffer:
                # wrap to console width - padding - '[Aria2c]: '
                aria_log_buffer = "\n          ".join(textwrap.wrap(
                    aria_log_buffer.rstrip(),
                    width=console.width - 20,
                    initial_indent=""
                ))
                console.log(Text.from_ansi("\n[Aria2c]: " + aria_log_buffer))

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


__ALL__ = (aria2c,)
