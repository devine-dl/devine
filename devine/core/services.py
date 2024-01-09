from pathlib import Path

import click

from devine.core.config import config
from devine.core.service import Service
from devine.core.utilities import import_module_by_path

_SERVICES = sorted(
    (
        path
        for path in config.directories.services.glob("*/__init__.py")
    ),
    key=lambda x: x.parent.stem
)

_MODULES = {
    path.parent.stem: getattr(import_module_by_path(path), path.parent.stem)
    for path in _SERVICES
}

_ALIASES = {
    tag: getattr(module, "ALIASES")
    for tag, module in _MODULES.items()
}


class Services(click.MultiCommand):
    """Lazy-loaded command group of project services."""

    # Click-specific methods

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Returns a list of all available Services as command names for Click."""
        return Services.get_tags()

    def get_command(self, ctx: click.Context, name: str) -> click.Command:
        """Load the Service and return the Click CLI method."""
        tag = Services.get_tag(name)
        try:
            service = Services.load(tag)
        except KeyError as e:
            available_services = self.list_commands(ctx)
            if not available_services:
                raise click.ClickException(
                    f"There are no Services added yet, therefore the '{name}' Service could not be found."
                )
            raise click.ClickException(f"{e}. Available Services: {', '.join(available_services)}")

        if hasattr(service, "cli"):
            return service.cli

        raise click.ClickException(f"Service '{tag}' has no 'cli' method configured.")

    # Methods intended to be used anywhere

    @staticmethod
    def get_tags() -> list[str]:
        """Returns a list of service tags from all available Services."""
        return [x.parent.stem for x in _SERVICES]

    @staticmethod
    def get_path(name: str) -> Path:
        """Get the directory path of a command."""
        tag = Services.get_tag(name)
        for service in _SERVICES:
            if service.parent.stem == tag:
                return service.parent
        raise KeyError(f"There is no Service added by the Tag '{name}'")

    @staticmethod
    def get_tag(value: str) -> str:
        """
        Get the Service Tag (e.g. DSNP, not DisneyPlus/Disney+, etc.) by an Alias.
        Input value can be of any case-sensitivity.
        Original input value is returned if it did not match a service tag.
        """
        original_value = value
        value = value.lower()
        for path in _SERVICES:
            tag = path.parent.stem
            if value in (tag.lower(), *_ALIASES.get(tag, [])):
                return tag
        return original_value

    @staticmethod
    def load(tag: str) -> Service:
        """Load a Service module by Service tag."""
        module = _MODULES.get(tag)
        if not module:
            raise KeyError(f"There is no Service added by the Tag '{tag}'")
        return module


__all__ = ("Services",)
