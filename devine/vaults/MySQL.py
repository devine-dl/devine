from __future__ import annotations

from typing import Iterator, Optional, Union
from uuid import UUID

import pymysql
from pymysql.cursors import DictCursor

from devine.core.services import Services
from devine.core.utils.atomicsql import AtomicSQL
from devine.core.vault import Vault


class MySQL(Vault):
    """Key Vault using a remotely-accessed mysql database connection."""

    def __init__(self, name: str, host: str, database: str, username: str, **kwargs):
        """
        All extra arguments provided via **kwargs will be sent to pymysql.connect.
        This can be used to provide more specific connection information.
        """
        super().__init__(name)
        self.slug = f"{host}:{database}:{username}"
        self.con = pymysql.connect(
            host=host,
            db=database,
            user=username,
            cursorclass=DictCursor,
            **kwargs
        )
        self.adb = AtomicSQL()
        self.ticket = self.adb.load(self.con)

        self.permissions = self.get_permissions()
        if not self.has_permission("SELECT"):
            raise PermissionError(f"MySQL vault {self.slug} has no SELECT permission.")

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
                f"SELECT `id`, `key_` FROM `{service}` WHERE `kid`=%s AND `key_`!=%s",
                [kid, "0" * 32]
            )
        ).fetchone()
        if not c:
            return None

        return c["key_"]

    def get_keys(self, service: str) -> Iterator[tuple[str, str]]:
        if not self.has_table(service):
            # no table, no keys, simple
            return None

        c = self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"SELECT `kid`, `key_` FROM `{service}` WHERE `key_`!=%s",
                ["0" * 32]
            )
        )

        for row in c.fetchall():
            yield row["kid"], row["key_"]

    def add_key(self, service: str, kid: Union[UUID, str], key: str, commit: bool = False) -> bool:
        if not key or key.count("0") == len(key):
            raise ValueError("You cannot add a NULL Content Key to a Vault.")

        if not self.has_permission("INSERT", table=service):
            raise PermissionError(f"MySQL vault {self.slug} has no INSERT permission.")

        if not self.has_table(service):
            try:
                self.create_table(service, commit)
            except PermissionError:
                return False

        if isinstance(kid, UUID):
            kid = kid.hex

        if self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"SELECT `id` FROM `{service}` WHERE `kid`=%s AND `key_`=%s",
                [kid, key]
            )
        ).fetchone():
            # table already has this exact KID:KEY stored
            return True

        self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"INSERT INTO `{service}` (kid, key_) VALUES (%s, %s)",
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

        if not self.has_permission("INSERT", table=service):
            raise PermissionError(f"MySQL vault {self.slug} has no INSERT permission.")

        if not self.has_table(service):
            try:
                self.create_table(service, commit)
            except PermissionError:
                return 0

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
                f"INSERT IGNORE INTO `{service}` (kid, key_) VALUES (%s, %s)",
                kid_keys.items()
            )
        )

        if commit:
            self.commit()

        return c.rowcount

    def get_services(self) -> Iterator[str]:
        c = self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute("SHOW TABLES")
        )
        for table in c.fetchall():
            # each entry has a key named `Tables_in_<db name>`
            yield Services.get_tag(list(table.values())[0])

    def has_table(self, name: str) -> bool:
        """Check if the Vault has a Table with the specified name."""
        return list(self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                "SELECT count(TABLE_NAME) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                [self.con.db, name]
            )
        ).fetchone().values())[0] == 1

    def create_table(self, name: str, commit: bool = False):
        """Create a Table with the specified name if not yet created."""
        if self.has_table(name):
            return

        if not self.has_permission("CREATE"):
            raise PermissionError(f"MySQL vault {self.slug} has no CREATE permission.")

        self.adb.safe_execute(
            self.ticket,
            lambda db, cursor: cursor.execute(
                # TODO: SQL injection risk
                f"""
                CREATE TABLE IF NOT EXISTS {name} (
                  id          int AUTO_INCREMENT PRIMARY KEY,
                  kid         VARCHAR(255) NOT NULL,
                  key_        VARCHAR(255) NOT NULL,
                  UNIQUE(kid, key_)
                );
                """
            )
        )

        if commit:
            self.commit()

    def get_permissions(self) -> list:
        """Get and parse Grants to a more easily usable list tuple array."""
        with self.con.cursor() as c:
            c.execute("SHOW GRANTS")
            grants = c.fetchall()
            grants = [next(iter(x.values())) for x in grants]
        grants = [tuple(x[6:].split(" TO ")[0].split(" ON ")) for x in list(grants)]
        grants = [(
            list(map(str.strip, perms.replace("ALL PRIVILEGES", "*").split(","))),
            location.replace("`", "").split(".")
        ) for perms, location in grants]
        return grants

    def has_permission(self, operation: str, database: Optional[str] = None, table: Optional[str] = None) -> bool:
        """Check if the current connection has a specific permission."""
        grants = [x for x in self.permissions if x[0] == ["*"] or operation.upper() in x[0]]
        if grants and database:
            grants = [x for x in grants if x[1][0] in (database, "*")]
        if grants and table:
            grants = [x for x in grants if x[1][1] in (table, "*")]
        return bool(grants)

    def commit(self):
        """Commit any changes made that has not been written to db."""
        self.adb.commit(self.ticket)
