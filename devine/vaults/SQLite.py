from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, Optional, Union
from uuid import UUID

from devine.core.services import Services
from devine.core.utils.atomicsql import AtomicSQL
from devine.core.vault import Vault


class SQLite(Vault):
    """Key Vault using a locally-accessed sqlite DB file."""

    def __init__(self, name: str, path: Union[str, Path]):
        super().__init__(name)
        self.path = Path(path).expanduser()
        # TODO: Use a DictCursor or such to get fetches as dict?
        self.con = sqlite3.connect(self.path)
        self.adb = AtomicSQL()
        self.ticket = self.adb.load(self.con)

    def get_key(self, kid: Union[UUID, str], service: str) -> Optional[str]:
        if not self.has_table(service):
            # no table, no key, simple
            return None

        if isinstance(kid, UUID):
            kid = kid.hex

        c = self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"SELECT `id`, `key_` FROM `{service}` WHERE `kid`=? AND `key_`!=?",
                [kid, "0" * 32]
            )
        ).fetchone()
        if not c:
            return None

        return c[1]  # `key_`

    def get_keys(self, service: str) -> Iterator[tuple[str, str]]:
        if not self.has_table(service):
            # no table, no keys, simple
            return None
        c = self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"SELECT `kid`, `key_` FROM `{service}` WHERE `key_`!=?",
                ["0" * 32]
            )
        )
        for (kid, key_) in c.fetchall():
            yield kid, key_

    def add_key(self, service: str, kid: Union[UUID, str], key: str, commit: bool = False) -> bool:
        if not key or key.count("0") == len(key):
            raise ValueError("You cannot add a NULL Content Key to a Vault.")

        if not self.has_table(service):
            self.create_table(service, commit)

        if isinstance(kid, UUID):
            kid = kid.hex

        if self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"SELECT `id` FROM `{service}` WHERE `kid`=? AND `key_`=?",
                [kid, key]
            )
        ).fetchone():
            # table already has this exact KID:KEY stored
            return True

        self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"INSERT INTO `{service}` (kid, key_) VALUES (?, ?)",
                (kid, key)
            )
        )

        if commit:
            self.commit()

        return True

    def add_keys(self, service: str, kid_keys: dict[Union[UUID, str], str], commit: bool = False) -> int:
        for kid, key in kid_keys.items():
            if not key or key.count("0") == len(key):
                raise ValueError("You cannot add a NULL Content Key to a Vault.")

        if not self.has_table(service):
            self.create_table(service, commit)

        if not isinstance(kid_keys, dict):
            raise ValueError(f"The kid_keys provided is not a dictionary, {kid_keys!r}")
        if not all(isinstance(kid, (str, UUID)) and isinstance(key_, str) for kid, key_ in kid_keys.items()):
            raise ValueError("Expecting dict with Key of str/UUID and value of str.")

        if any(isinstance(kid, UUID) for kid, key_ in kid_keys.items()):
            kid_keys = {
                kid.hex if isinstance(kid, UUID) else kid: key_
                for kid, key_ in kid_keys.items()
            }

        c = self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.executemany(
                # TODO: SQL injection risk
                f"INSERT OR IGNORE INTO `{service}` (kid, key_) VALUES (?, ?)",
                kid_keys.items()
            )
        )

        if commit:
            self.commit()

        return c.rowcount

    def get_services(self) -> Iterator[str]:
        c = self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        )
        for (name,) in c.fetchall():
            if name != "sqlite_sequence":
                yield Services.get_tag(name)

    def has_table(self, name: str) -> bool:
        """Check if the Vault has a Table with the specified name."""
        return self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                "SELECT count(name) FROM sqlite_master WHERE type='table' AND name=?",
                [name]
            )
        ).fetchone()[0] == 1

    def create_table(self, name: str, commit: bool = False):
        """Create a Table with the specified name if not yet created."""
        if self.has_table(name):
            return

        self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"""
                CREATE TABLE IF NOT EXISTS {name} (
                  "id"        INTEGER NOT NULL UNIQUE,
                  "kid"       TEXT NOT NULL COLLATE NOCASE,
                  "key_"      TEXT NOT NULL COLLATE NOCASE,
                  PRIMARY KEY("id" AUTOINCREMENT),
                  UNIQUE("kid", "key_")
                );
                """
            )
        )

        if commit:
            self.commit()

    def commit(self):
        """Commit any changes made that has not been written to db."""
        self.adb.commit(self.ticket)
