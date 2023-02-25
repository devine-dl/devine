import atexit
import logging
import textwrap
from datetime import datetime
from pathlib import Path

import click
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from rich.padding import Padding

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

    if log_path:
        global LOGGING_PATH
        console.record = True
        new_log_path = rotate_log_file(log_path)
        LOGGING_PATH = new_log_path

    urllib3.disable_warnings(InsecureRequestWarning)

    console.print(
        Padding(
            textwrap.dedent(
                f"""
                [ascii.art]
                ⠀⠀⠀/ __ \/ ____/ |  / /  _/ | / / ____/
                ⠀⠀/ / / / __/  | | / // //  |/ / __/⠀⠀⠀
                ⠀/ /_/ / /___  | |/ // // /|  / /___⠀⠀⠀
                /_____/_____/  |___/___/_/ |_/_____/⠀⠀⠀
                [/]
                v[repr.number]{__version__}[/] Copyright © 2019-{datetime.now().year} rlaphoenix
                [bright_blue]https://github.com/devine-dl/devine[/]
                """
            ).strip(),
            (0, 21, 1, 20)
        ),
        justify="center"
    )

    if version:
        return


@atexit.register
def save_log():
    if console.record and LOGGING_PATH:
        # TODO: Currently semi-bust. Everything that refreshes gets duplicated.
        console.save_text(LOGGING_PATH)


if __name__ == "__main__":
    main()
