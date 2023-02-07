import ast
import logging
import sys

import click
from ruamel.yaml import YAML

from devine.core.config import config
from devine.core.constants import context_settings


@click.command(
    short_help="Manage configuration values for the program and its services.",
    context_settings=context_settings)
@click.argument("key", type=str, required=False)
@click.argument("value", type=str, required=False)
@click.option("--unset", is_flag=True, default=False, help="Unset/remove the configuration value.")
@click.option("--list", "list_", is_flag=True, default=False, help="List all set configuration values.")
@click.pass_context
def cfg(ctx: click.Context, key: str, value: str, unset: bool, list_: bool) -> None:
    """
    Manage configuration values for the program and its services.

    \b
    Known Issues:
    - Config changes remove all comments of the changed files, which may hold critical data. (#14)
    """
    if not key and not value and not list_:
        raise click.UsageError("Nothing to do.", ctx)

    if value:
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            pass  # probably a str without quotes or similar, assume it's a string value

    log = logging.getLogger("cfg")

    config_path = config.directories.user_configs / config.filenames.root_config

    yaml, data = YAML(), None
    yaml.default_flow_style = False
    if config_path.is_file():
        data = yaml.load(config_path)

    if not data:
        log.warning(f"{config_path} has no configuration data, yet")
        # yaml.load() returns `None` if the input data is blank instead of a usable object
        # force a usable object by making one and removing the only item within it
        data = yaml.load("""__TEMP__: null""")
        del data["__TEMP__"]

    if list_:
        yaml.dump(data, sys.stdout)
        return

    key_items = key.split(".")
    parent_key = key_items[:-1]
    trailing_key = key_items[-1]

    is_write = value is not None
    is_delete = unset
    if is_write and is_delete:
        raise click.ClickException("You cannot set a value and use --unset at the same time.")

    if not is_write and not is_delete:
        data = data.mlget(key_items, default=KeyError)
        if data == KeyError:
            raise click.ClickException(f"Key '{key}' does not exist in the config.")
        yaml.dump(data, sys.stdout)
    else:
        try:
            parent_data = data
            if parent_key:
                parent_data = data.mlget(parent_key, default=data)
                if parent_data == data:
                    for key in parent_key:
                        if not hasattr(parent_data, key):
                            parent_data[key] = {}
                        parent_data = parent_data[key]
            if is_write:
                parent_data[trailing_key] = value
                log.info(f"Set {key} to {repr(value)}")
            elif is_delete:
                del parent_data[trailing_key]
                log.info(f"Unset {key}")
        except KeyError:
            raise click.ClickException(f"Key '{key}' does not exist in the config.")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        yaml.dump(data, config_path)
