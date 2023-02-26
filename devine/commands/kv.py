import logging
import re
from pathlib import Path
from typing import Optional

import click

from devine.core.config import config
from devine.core.constants import context_settings
from devine.core.services import Services
from devine.core.vault import Vault
from devine.core.vaults import Vaults


@click.group(short_help="Manage and configure Key Vaults.", context_settings=context_settings)
def kv() -> None:
    """Manage and configure Key Vaults."""


@kv.command()
@click.argument("to_vault", type=str)
@click.argument("from_vaults", nargs=-1, type=click.UNPROCESSED)
@click.option("-s", "--service", type=str, default=None,
              help="Only copy data to and from a specific service.")
def copy(to_vault: str, from_vaults: list[str], service: Optional[str] = None) -> None:
    """
    Copy data from multiple Key Vaults into a single Key Vault.
    Rows with matching KIDs are skipped unless there's no KEY set.
    Existing data is not deleted or altered.

    The `to_vault` argument is the key vault you wish to copy data to.
    It should be the name of a Key Vault defined in the config.

    The `from_vaults` argument is the key vault(s) you wish to take
    data from. You may supply multiple key vaults.
    """
    if not from_vaults:
        raise click.ClickException("No Vaults were specified to copy data from.")

    log = logging.getLogger("kv")

    vaults = Vaults()
    for vault_name in [to_vault] + list(from_vaults):
        vault = next((x for x in config.key_vaults if x["name"] == vault_name), None)
        if not vault:
            raise click.ClickException(f"Vault ({vault_name}) is not defined in the config.")
        vault_type = vault["type"]
        vault_args = vault.copy()
        del vault_args["type"]
        vaults.load(vault_type, **vault_args)

    to_vault: Vault = vaults.vaults[0]
    from_vaults: list[Vault] = vaults.vaults[1:]

    log.info(f"Copying data from {', '.join([x.name for x in from_vaults])}, into {to_vault.name}")
    if service:
        service = Services.get_tag(service)
        log.info(f"Only copying data for service {service}")

    total_added = 0
    for from_vault in from_vaults:
        if service:
            services = [service]
        else:
            services = from_vault.get_services()

        for service_ in services:
            log.info(f"Getting data from {from_vault} for {service_}")
            content_keys = list(from_vault.get_keys(service_))  # important as it's a generator we iterate twice

            bad_keys = {
                kid: key
                for kid, key in content_keys
                if not key or key.count("0") == len(key)
            }

            for kid, key in bad_keys.items():
                log.warning(f"Cannot add a NULL Content Key to a Vault, skipping: {kid}:{key}")

            content_keys = {
                kid: key
                for kid, key in content_keys
                if kid not in bad_keys
            }

            total_count = len(content_keys)
            log.info(f"Adding {total_count} Content Keys to {to_vault} for {service_}")

            try:
                added = to_vault.add_keys(service_, content_keys)
            except PermissionError:
                log.warning(f" - No permission to create table ({service_}) in {to_vault}, skipping...")
                continue

            total_added += added
            existed = total_count - added

            log.info(f"{to_vault} ({service_}): {added} newly added, {existed} already existed (skipped)")

    log.info(f"{to_vault}: {total_added} total newly added")


@kv.command()
@click.argument("vaults", nargs=-1, type=click.UNPROCESSED)
@click.option("-s", "--service", type=str, default=None,
              help="Only sync data to and from a specific service.")
@click.pass_context
def sync(ctx: click.Context, vaults: list[str], service: Optional[str] = None) -> None:
    """
    Ensure multiple Key Vaults copies of all keys as each other.
    It's essentially just a bi-way copy between each vault.
    To see the precise details of what it's doing between each
    provided vault, see the documentation for the `copy` command.
    """
    if not len(vaults) > 1:
        raise click.ClickException("You must provide more than one Vault to sync.")

    ctx.invoke(copy, to_vault=vaults[0], from_vaults=vaults[1:], service=service)
    for i in range(1, len(vaults)):
        ctx.invoke(copy, to_vault=vaults[i], from_vaults=[vaults[i-1]], service=service)


@kv.command()
@click.argument("file", type=Path)
@click.argument("service", type=str)
@click.argument("vaults", nargs=-1, type=click.UNPROCESSED)
def add(file: Path, service: str, vaults: list[str]) -> None:
    """
    Add new Content Keys to Key Vault(s) by service.

    File should contain one key per line in the format KID:KEY (HEX:HEX).
    Each line should have nothing else within it except for the KID:KEY.
    Encoding is presumed to be UTF8.
    """
    if not file.exists():
        raise click.ClickException(f"File provided ({file}) does not exist.")
    if not file.is_file():
        raise click.ClickException(f"File provided ({file}) is not a file.")
    if not service or not isinstance(service, str):
        raise click.ClickException(f"Service provided ({service}) is invalid.")
    if len(vaults) < 1:
        raise click.ClickException("You must provide at least one Vault.")

    log = logging.getLogger("kv")
    service = Services.get_tag(service)

    vaults_ = Vaults()
    for vault_name in vaults:
        vault = next((x for x in config.key_vaults if x["name"] == vault_name), None)
        if not vault:
            raise click.ClickException(f"Vault ({vault_name}) is not defined in the config.")
        vault_type = vault["type"]
        vault_args = vault.copy()
        del vault_args["type"]
        vaults_.load(vault_type, **vault_args)

    data = file.read_text(encoding="utf8")
    kid_keys: dict[str, str] = {}
    for line in data.splitlines(keepends=False):
        line = line.strip()
        match = re.search(r"^(?P<kid>[0-9a-fA-F]{32}):(?P<key>[0-9a-fA-F]{32})$", line)
        if not match:
            continue
        kid = match.group("kid").lower()
        key = match.group("key").lower()
        kid_keys[kid] = key

    total_count = len(kid_keys)

    for vault in vaults_:
        log.info(f"Adding {total_count} Content Keys to {vault}")
        added_count = vault.add_keys(service, kid_keys)
        existed_count = total_count - added_count
        log.info(f"{vault}: {added_count} newly added, {existed_count} already existed (skipped)")

    log.info("Done!")


@kv.command()
@click.argument("vaults", nargs=-1, type=click.UNPROCESSED)
def prepare(vaults: list[str]) -> None:
    """Create Service Tables on Vaults if not yet created."""
    log = logging.getLogger("kv")

    vaults_ = Vaults()
    for vault_name in vaults:
        vault = next((x for x in config.key_vaults if x["name"] == vault_name), None)
        if not vault:
            raise click.ClickException(f"Vault ({vault_name}) is not defined in the config.")
        vault_type = vault["type"]
        vault_args = vault.copy()
        del vault_args["type"]
        vaults_.load(vault_type, **vault_args)

    for vault in vaults_:
        if hasattr(vault, "has_table") and hasattr(vault, "create_table"):
            for service_tag in Services.get_tags():
                if vault.has_table(service_tag):
                    log.info(f"{vault} already has a {service_tag} Table")
                else:
                    try:
                        vault.create_table(service_tag, commit=True)
                        log.info(f"{vault}: Created {service_tag} Table")
                    except PermissionError:
                        log.error(f"{vault} user has no create table permission, skipping...")
                        continue
        else:
            log.info(f"{vault} does not use tables, skipping...")

    log.info("Done!")
