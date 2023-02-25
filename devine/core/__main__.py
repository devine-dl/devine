import logging
from datetime import datetime
from pathlib import Path

import click
import coloredlogs
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from devine.core import __version__
from devine.core.commands import Commands
from devine.core.config import config
from devine.core.constants import LOG_FORMAT, LOG_FORMATTER, context_settings
from devine.core.utilities import rotate_log_file


@click.command(cls=Commands, invoke_without_command=True, context_settings=context_settings)
@click.option("-v", "--version", is_flag=True, default=False, help="Print version information.")
@click.option("-d", "--debug", is_flag=True, default=False, help="Enable DEBUG level logs.")
@click.option("--log", "log_path", type=Path, default=config.directories.logs / config.filenames.log,
              help="Log path (or filename). Path can contain the following f-string args: {name} {time}.")
def main(version: bool, debug: bool, log_path: Path) -> None:
    """Devine—Open-Source Movie, TV, and Music Downloading Solution."""
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
    log = logging.getLogger()
    coloredlogs.install(level=log.level, fmt=LOG_FORMAT, style="{")

    if log_path:
        new_log_path = rotate_log_file(log_path)
        fh = logging.FileHandler(new_log_path, encoding="utf8")
        fh.setFormatter(LOG_FORMATTER)
        log.addHandler(fh)

    urllib3.disable_warnings(InsecureRequestWarning)

    log.info(f"Devine version {__version__} Copyright (c) 2019-{datetime.now().year} rlaphoenix")
    log.info("Convenient Widevine-DRM Downloader and Decrypter.")
    log.info("https://github.com/devine-dl/devine")
    if version:
        return


if __name__ == "__main__":
    main()
