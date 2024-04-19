import logging
import shutil
from typing import Optional

import click
from rich.padding import Padding
from rich.table import Table
from rich.tree import Tree

from devine.core.config import POSSIBLE_CONFIG_PATHS, config, config_path
from devine.core.console import console
from devine.core.constants import context_settings
from devine.core.services import Services


@click.group(short_help="Manage and configure the project environment.", context_settings=context_settings)
def env() -> None:
    """Manage and configure the project environment."""


@env.command()
def info() -> None:
    """Displays information about the current environment."""
    log = logging.getLogger("env")

    if config_path:
        log.info(f"Config loaded from {config_path}")
    else:
        tree = Tree("No config file found, you can use any of the following locations:")
        for i, path in enumerate(POSSIBLE_CONFIG_PATHS, start=1):
            tree.add(f"[repr.number]{i}.[/] [text2]{path.resolve()}[/]")
        console.print(Padding(
            tree,
            (0, 5)
        ))

    table = Table(title="Directories", expand=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Path")

    for name in sorted(dir(config.directories)):
        if name.startswith("__") or name == "app_dirs":
            continue
        path = getattr(config.directories, name).resolve()
        table.add_row(name.title(), str(path))

    console.print(Padding(
        table,
        (1, 5)
    ))


@env.group(name="clear", short_help="Clear an environment directory.", context_settings=context_settings)
def clear() -> None:
    """Clear an environment directory."""


@clear.command()
@click.argument("service", type=str, required=False)
def cache(service: Optional[str]) -> None:
    """Clear the environment cache directory."""
    log = logging.getLogger("env")
    cache_dir = config.directories.cache
    if service:
        cache_dir = cache_dir / Services.get_tag(service)
    log.info(f"Clearing cache directory: {cache_dir}")
    files_count = len(list(cache_dir.glob("**/*")))
    if not files_count:
        log.info("No files to delete")
    else:
        log.info(f"Deleting {files_count} files...")
        shutil.rmtree(cache_dir)
        log.info("Cleared")


@clear.command()
def temp() -> None:
    """Clear the environment temp directory."""
    log = logging.getLogger("env")
    log.info(f"Clearing temp directory: {config.directories.temp}")
    files_count = len(list(config.directories.temp.glob("**/*")))
    if not files_count:
        log.info("No files to delete")
    else:
        log.info(f"Deleting {files_count} files...")
        shutil.rmtree(config.directories.temp)
        log.info("Cleared")
