import logging
import tkinter.filedialog
from pathlib import Path
from typing import Optional

import click
from ruamel.yaml import YAML

from devine.core.config import Config, config
from devine.core.constants import context_settings
from devine.core.credential import Credential


@click.group(
    short_help="Manage cookies and credentials for profiles of services.",
    context_settings=context_settings)
@click.pass_context
def auth(ctx: click.Context) -> None:
    """Manage cookies and credentials for profiles of services."""
    ctx.obj = logging.getLogger("auth")


@auth.command(
    name="list",
    short_help="List profiles and their state for a service or all services.",
    context_settings=context_settings)
@click.argument("service", type=str, required=False)
@click.pass_context
def list_(ctx: click.Context, service: Optional[str] = None) -> None:
    """
    List profiles and their state for a service or all services.

    \b
    Profile and Service names are case-insensitive.
    """
    log = ctx.obj
    service_f = service

    profiles: dict[str, dict[str, list]] = {}
    for cookie_dir in config.directories.cookies.iterdir():
        service = cookie_dir.name
        profiles[service] = {}
        for cookie in cookie_dir.glob("*.txt"):
            if cookie.stem not in profiles[service]:
                profiles[service][cookie.stem] = ["Cookie"]

    for service, credentials in config.credentials.items():
        if service not in profiles:
            profiles[service] = {}
        for profile, credential in credentials.items():
            if profile not in profiles[service]:
                profiles[service][profile] = []
            profiles[service][profile].append("Credential")

    for service, profiles in profiles.items():
        if service_f and service != service_f.upper():
            continue
        log.info(service)
        for profile, authorizations in profiles.items():
            log.info(f'  "{profile}": {", ".join(authorizations)}')


@auth.command(
    short_help="View profile cookies and credentials for a service.",
    context_settings=context_settings)
@click.argument("profile", type=str)
@click.argument("service", type=str)
@click.pass_context
def view(ctx: click.Context, profile: str, service: str) -> None:
    """
    View profile cookies and credentials for a service.

    \b
    Profile and Service names are case-sensitive.
    """
    log = ctx.obj
    service_f = service
    profile_f = profile
    found = False

    for cookie_dir in config.directories.cookies.iterdir():
        if cookie_dir.name == service_f:
            for cookie in cookie_dir.glob("*.txt"):
                if cookie.stem == profile_f:
                    log.info(f"Cookie: {cookie}")
                    log.debug(cookie.read_text(encoding="utf8").strip())
                    found = True
                    break

    for service, credentials in config.credentials.items():
        if service == service_f:
            for profile, credential in credentials.items():
                if profile == profile_f:
                    log.info(f"Credential: {':'.join(list(credential))}")
                    found = True
                    break

    if not found:
        raise click.ClickException(
            f"Could not find Profile '{profile_f}' for Service '{service_f}'."
            f"\nThe profile and service values are case-sensitive."
        )


@auth.command(
    short_help="Check what profile is used by services.",
    context_settings=context_settings)
@click.argument("service", type=str, required=False)
@click.pass_context
def status(ctx: click.Context, service: Optional[str] = None) -> None:
    """
    Check what profile is used by services.

    \b
    Service names are case-sensitive.
    """
    log = ctx.obj
    found_profile = False
    for service_, profile in config.profiles.items():
        if not service or service_.upper() == service.upper():
            log.info(f"{service_}: {profile or '--'}")
            found_profile = True

    if not found_profile:
        log.info(f"No profile has been explicitly set for {service}")

    default = config.profiles.get("default", "not set")
    log.info(f"The default profile is {default}")


@auth.command(
    short_help="Delete a profile and all of its authorization from a service.",
    context_settings=context_settings)
@click.argument("profile", type=str)
@click.argument("service", type=str)
@click.option("--cookie", is_flag=True, default=False, help="Only delete the cookie.")
@click.option("--credential", is_flag=True, default=False, help="Only delete the credential.")
@click.pass_context
def delete(ctx: click.Context, profile: str, service: str, cookie: bool, credential: bool):
    """
    Delete a profile and all of its authorization from a service.

    \b
    By default this does remove both Cookies and Credentials.
    You may remove only one of them with --cookie or --credential.

    \b
    Profile and Service names are case-sensitive.
    Comments may be removed from config!
    """
    log = ctx.obj
    service_f = service
    profile_f = profile
    found = False

    if not credential:
        for cookie_dir in config.directories.cookies.iterdir():
            if cookie_dir.name == service_f:
                for cookie_ in cookie_dir.glob("*.txt"):
                    if cookie_.stem == profile_f:
                        cookie_.unlink()
                        log.info(f"Deleted Cookie: {cookie_}")
                        found = True
                        break

    if not cookie:
        for key, credentials in config.credentials.items():
            if key == service_f:
                for profile, credential_ in credentials.items():
                    if profile == profile_f:
                        config_path = Config._Directories.user_configs / Config._Filenames.root_config
                        yaml, data = YAML(), None
                        yaml.default_flow_style = False
                        data = yaml.load(config_path)
                        del data["credentials"][key][profile_f]
                        yaml.dump(data, config_path)
                        log.info(f"Deleted Credential: {credential_}")
                        found = True
                        break

    if not found:
        raise click.ClickException(
            f"Could not find Profile '{profile_f}' for Service '{service_f}'."
            f"\nThe profile and service values are case-sensitive."
        )


@auth.command(
    short_help="Add a Credential and/or Cookies to an existing or new profile for a service.",
    context_settings=context_settings)
@click.argument("profile", type=str)
@click.argument("service", type=str)
@click.option("--cookie", type=str, default=None, help="Direct path to Cookies to add.")
@click.option("--credential", type=str, default=None, help="Direct Credential string to add.")
@click.pass_context
def add(ctx: click.Context, profile: str, service: str, cookie: Optional[str] = None, credential: Optional[str] = None):
    """
    Add a Credential and/or Cookies to an existing or new profile for a service.

    \b
    Cancel the Open File dialogue when presented if you do not wish to provide
    cookies. The Credential should be in `Username:Password` form. The username
    may be an email. If you do not wish to add a Credential, just hit enter.

    \b
    Profile and Service names are case-sensitive!
    Comments may be removed from config!
    """
    log = ctx.obj
    service = service.upper()
    profile = profile.lower()

    if cookie:
        cookie = Path(cookie)
    else:
        print("Opening File Dialogue, select a Cookie file to import.")
        cookie = tkinter.filedialog.askopenfilename(
            title="Select a Cookie file (Cancel to skip)",
            filetypes=[("Cookies", "*.txt"), ("All files", "*.*")]
        )
        if cookie:
            cookie = Path(cookie)
        else:
            log.info("Skipped adding a Cookie...")

    if credential:
        try:
            credential = Credential.loads(credential)
        except ValueError as e:
            raise click.ClickException(str(e))
    else:
        credential = input("Credential: ")
        if credential:
            try:
                credential = Credential.loads(credential)
            except ValueError as e:
                raise click.ClickException(str(e))
        else:
            log.info("Skipped adding a Credential...")

    if cookie:
        cookie = cookie.rename((config.directories.cookies / service / profile).with_suffix(".txt"))
        log.info(f"Moved Cookie file to: {cookie}")

    if credential:
        config_path = Config._Directories.user_configs / Config._Filenames.root_config
        yaml, data = YAML(), None
        yaml.default_flow_style = False
        data = yaml.load(config_path)
        data["credentials"][service][profile] = credential.dumps()
        yaml.dump(data, config_path)
        log.info(f"Added Credential: {credential}")
