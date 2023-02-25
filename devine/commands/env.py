import shutil
from typing import Optional

import click

from devine.core.config import config
from devine.core.console import console
from devine.core.constants import context_settings
from devine.core.services import Services


@click.group(short_help="Manage and configure the project environment.", context_settings=context_settings)
def env() -> None:
    """Manage and configure the project environment."""


@env.command()
def info() -> None:
    """Displays information about the current environment."""
    console.log(f"[Root Config]     : {config.directories.user_configs / config.filenames.root_config}")
    console.log(f"[Cookies]         : {config.directories.cookies}")
    console.log(f"[WVDs]            : {config.directories.wvds}")
    console.log(f"[Cache]           : {config.directories.cache}")
    console.log(f"[Logs]            : {config.directories.logs}")
    console.log(f"[Temp Files]      : {config.directories.temp}")
    console.log(f"[Downloads]       : {config.directories.downloads}")


@env.group(name="clear", short_help="Clear an environment directory.", context_settings=context_settings)
def clear() -> None:
    """Clear an environment directory."""


@clear.command()
@click.argument("service", type=str, required=False)
def cache(service: Optional[str]) -> None:
    """Clear the environment cache directory."""
    cache_dir = config.directories.cache
    if service:
        cache_dir = cache_dir / Services.get_tag(service)
    console.log(f"Clearing cache directory: {cache_dir}")
    files_count = len(list(cache_dir.glob("**/*")))
    if not files_count:
        console.log("No files to delete")
    else:
        console.log(f"Deleting {files_count} files...")
        shutil.rmtree(cache_dir)
        console.log("Cleared")


@clear.command()
def temp() -> None:
    """Clear the environment temp directory."""
    console.log(f"Clearing temp directory: {config.directories.temp}")
    files_count = len(list(config.directories.temp.glob("**/*")))
    if not files_count:
        console.log("No files to delete")
    else:
        console.log(f"Deleting {files_count} files...")
        shutil.rmtree(config.directories.temp)
        console.log("Cleared")
