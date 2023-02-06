import subprocess
from pathlib import Path
from typing import Union, Optional

from devine.core.utilities import get_binary_path


async def saldl(
    uri: Union[str, list[str]],
    out: Union[Path, str],
    headers: Optional[dict] = None,
    proxy: Optional[str] = None
) -> int:
    out = Path(out)

    if headers:
        headers.update({k: v for k, v in headers.items() if k.lower() != "accept-encoding"})

    executable = get_binary_path("saldl", "saldl-win64", "saldl-win32")
    if not executable:
        raise EnvironmentError("Saldl executable not found...")

    arguments = [
        executable,
        # "--no-status",
        "--skip-TLS-verification",
        "--resume",
        "--merge-in-order",
        "-c8",
        "--auto-size", "1",
        "-D", str(out.parent),
        "-o", out.name
    ]

    if headers:
        arguments.extend([
            "--custom-headers",
            "\r\n".join([f"{k}: {v}" for k, v in headers.items()])
        ])

    if proxy:
        arguments.extend(["--proxy", proxy])

    if isinstance(uri, list):
        raise ValueError("Saldl code does not yet support multiple uri (e.g. segmented) downloads.")
    arguments.append(uri)

    return subprocess.check_call(arguments)


__ALL__ = (saldl,)
