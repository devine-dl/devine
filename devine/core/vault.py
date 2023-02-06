from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Iterator, Optional, Union
from uuid import UUID


class Vault(metaclass=ABCMeta):
    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        return f"{self.name} {type(self).__name__}"

    @abstractmethod
    def get_key(self, kid: Union[UUID, str], service: str) -> Optional[str]:
        """
        Get Key from Vault by KID (Key ID) and Service.

        It does not get Key by PSSH as the PSSH can be different depending on it's implementation,
        or even how it was crafted. Some PSSH values may also actually be a CENC Header rather
        than a PSSH MP4 Box too, which makes the value even more confusingly different.

        However, the KID never changes unless the video file itself has changed too, meaning the
        key for the presumed-matching KID wouldn't work, further proving matching by KID is
        superior.
        """

    @abstractmethod
    def get_keys(self, service: str) -> Iterator[tuple[str, str]]:
        """Get All Keys from Vault by Service."""

    @abstractmethod
    def add_key(self, service: str, kid: Union[UUID, str], key: str, commit: bool = False) -> bool:
        """Add KID:KEY to the Vault."""

    @abstractmethod
    def add_keys(self, service: str, kid_keys: dict[Union[UUID, str], str], commit: bool = False) -> int:
        """
        Add Multiple Content Keys with Key IDs for Service to the Vault.
        Pre-existing Content Keys are ignored/skipped.
        Raises PermissionError if the user has no permission to create the table.
        """

    @abstractmethod
    def get_services(self) -> Iterator[str]:
        """Get a list of Service Tags from Vault."""


__ALL__ = (Vault,)
