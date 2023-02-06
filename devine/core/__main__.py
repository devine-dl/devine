import logging
from datetime import datetime

import click
import coloredlogs

from devine.core import __version__
from devine.core.commands import Commands
from devine.core.constants import context_settings, LOG_FORMAT


@click.command(cls=Commands, invoke_without_command=True, context_settings=context_settings)
@click.option("-v", "--version", is_flag=True, default=False, help="Print version information.")
@click.option("-d", "--debug", is_flag=True, default=False, help="Enable DEBUG level logs.")
def main(version: bool, debug: bool) -> None:
    """Devine—Open-Source Movie, TV, and Music Downloading Solution."""
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
    log = logging.getLogger()
    coloredlogs.install(level=log.level, fmt=LOG_FORMAT, style="{")

    log.info(f"Devine version {__version__} Copyright (c) 2019-{datetime.now().year} rlaphoenix")
    log.info("Convenient Widevine-DRM Downloader and Decrypter.")
    log.info("https://github.com/devine/devine")
    if version:
        return


if __name__ == "__main__":
    main()
