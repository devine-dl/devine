import subprocess

import click

from devine.core.config import config
from devine.core.constants import context_settings
from devine.core.utilities import get_binary_path


@click.command(
    short_help="Serve your Local Widevine Devices for Remote Access.",
    context_settings=context_settings)
@click.option("-h", "--host", type=str, default="0.0.0.0", help="Host to serve from.")
@click.option("-p", "--port", type=int, default=8786, help="Port to serve from.")
@click.option("--caddy", is_flag=True, default=False, help="Also serve with Caddy.")
def serve(host: str, port: int, caddy: bool) -> None:
    """
    Serve your Local Widevine Devices for Remote Access.

    \b
    Host as 127.0.0.1 may block remote access even if port-forwarded.
    Instead, use 0.0.0.0 and ensure the TCP port you choose is forwarded.

    \b
    You may serve with Caddy at the same time with --caddy. You can use Caddy
    as a reverse-proxy to serve with HTTPS. The config used will be the Caddyfile
    next to the devine config.
    """
    from pywidevine import serve

    if caddy:
        executable = get_binary_path("caddy")
        if not executable:
            raise click.ClickException("Caddy executable \"caddy\" not found but is required for --caddy.")
        caddy_p = subprocess.Popen([
            executable,
            "run",
            "--config", str(config.directories.user_configs / "Caddyfile")
        ])
    else:
        caddy_p = None

    try:
        if not config.serve.get("devices"):
            config.serve["devices"] = []
        config.serve["devices"].extend(list(config.directories.wvds.glob("*.wvd")))
        serve.run(config.serve, host, port)
    finally:
        if caddy_p:
            caddy_p.kill()
