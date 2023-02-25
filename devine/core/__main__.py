import atexit
import logging
from datetime import datetime
from pathlib import Path

import click
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from devine.core import __version__
from devine.core.commands import Commands
from devine.core.config import config
from devine.core.console import ComfyRichHandler, console
from devine.core.constants import context_settings
from devine.core.utilities import rotate_log_file

LOGGING_PATH = None


@click.command(cls=Commands, invoke_without_command=True, context_settings=context_settings)
@click.option("-v", "--version", is_flag=True, default=False, help="Print version information.")
@click.option("-d", "--debug", is_flag=True, default=False, help="Enable DEBUG level logs.")
@click.option("--log", "log_path", type=Path, default=config.directories.logs / config.filenames.log,
              help="Log path (or filename). Path can contain the following f-string args: {name} {time}.")
def main(version: bool, debug: bool, log_path: Path) -> None:
    """Devine—Open-Source Movie, TV, and Music Downloading Solution."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(message)s",
        handlers=[ComfyRichHandler(
            show_time=False,
            show_path=debug,
            console=console,
            rich_tracebacks=True,
            tracebacks_suppress=[click],
            log_renderer=console._log_render  # noqa
        )]
    )
    log = logging.getLogger()

    if log_path:
        global LOGGING_PATH
        console.record = True
        new_log_path = rotate_log_file(log_path)
        LOGGING_PATH = new_log_path

    urllib3.disable_warnings(InsecureRequestWarning)

    log.info(f"Devine version {__version__} Copyright (c) 2019-{datetime.now().year} rlaphoenix")
    log.info("Convenient Widevine-DRM Downloader and Decrypter.")
    log.info("https://github.com/devine-dl/devine")
    if version:
        return


@atexit.register
def save_log():
    if console.record and LOGGING_PATH:
        # TODO: Currently semi-bust. Everything that refreshes gets duplicated.
        console.save_text(LOGGING_PATH)


if __name__ == "__main__":
    main()
