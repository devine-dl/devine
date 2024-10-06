import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

import click
from rich.padding import Padding
from rich.table import Table
from rich.tree import Tree

from devine.core.config import POSSIBLE_CONFIG_PATHS, config, config_path
from devine.core.console import console
from devine.core.constants import context_settings
from devine.core.services import Services
from devine.core.utils.osenvironment import get_os_arch


@click.group(short_help="Manage and configure the project environment.", context_settings=context_settings)
def env() -> None:
    """Manage and configure the project environment."""

@env.command()
def check() -> None:
    """Checks environment for the required dependencies."""
    table = Table(title="Dependencies", expand=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Installed", justify="center")
    table.add_column("Path", no_wrap=False,  overflow="fold")

    # builds shaka-packager based on os, arch
    packager_dep = get_os_arch("packager")

    dependencies = [
        {"name": "CCExtractor", "binary": "ccextractor"},
        {"name": "FFMpeg", "binary": "ffmpeg"},
        {"name": "MKVToolNix", "binary": "mkvmerge"},
        {"name": "Shaka-Packager", "binary": packager_dep},
        {"name": "Aria2(c)", "binary": "aria2c"}
    ]

    for dep in dependencies:
        path = shutil.which(dep["binary"])

        if path:
            installed = "[green]:heavy_check_mark:[/green]"
            path_output = path.lower()
        else:
            installed = "[red]:x:[/red]"
            path_output = "Not Found"

        # Add to the table
        table.add_row(dep["name"], installed, path_output)

    # Replace spinner with the result
    console.clear()
    console.print(Padding(
        table,
        (1, 5)
    ))

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
    table.add_column("Path", no_wrap=False,  overflow="fold")

    path_vars = {
        x: Path(os.getenv(x))
        for x in ("TEMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE")
        if sys.platform == "win32" and os.getenv(x)
    }

    for name in sorted(dir(config.directories)):
        if name.startswith("__") or name == "app_dirs":
            continue
        path = getattr(config.directories, name).resolve()
        for var, var_path in path_vars.items():
            if path.is_relative_to(var_path):
                path = rf"%{var}%\{path.relative_to(var_path)}"
                break
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
