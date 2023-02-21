from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from queue import Empty, Queue
from sqlite3 import Connection
from threading import Lock
from typing import Iterator, Optional, Union
from uuid import UUID

from devine.core.services import Services
from devine.core.vault import Vault


class SQLite(Vault):
    """Key Vault using a locally-accessed sqlite DB file."""

    def __init__(self, name: str, path: Union[str, Path]):
        super().__init__(name)
        self.path = Path(path).expanduser()
        # TODO: Use a DictCursor or such to get fetches as dict?
        self.con_pool = ConnectionPool(self.path, 5)

    def get_key(self, kid: Union[UUID, str], service: str) -> Optional[str]:
        if not self.has_table(service):
            # no table, no key, simple
            return None

        if isinstance(kid, UUID):
            kid = kid.hex

        conn = self.con_pool.get()
        cursor = conn.cursor()

        try:
            cursor.execute(
                f"SELECT `id`, `key_` FROM `{service}` WHERE `kid`=? AND `key_`!=?",
                (kid, "0" * 32)
            )
            cek = cursor.fetchone()
            if not cek:
                return None
            return cek[1]
        finally:
            cursor.close()
            self.con_pool.put(conn)

    def get_keys(self, service: str) -> Iterator[tuple[str, str]]:
        if not self.has_table(service):
            # no table, no keys, simple
            return None

        conn = self.con_pool.get()
        cursor = conn.cursor()

        try:
            cursor.execute(
                f"SELECT `kid`, `key_` FROM `{service}` WHERE `key_`!=?",
                ("0" * 32,)
            )
            for (kid, key_) in cursor.fetchall():
                yield kid, key_
        finally:
            cursor.close()
            self.con_pool.put(conn)

    def add_key(self, service: str, kid: Union[UUID, str], key: str) -> bool:
        if not key or key.count("0") == len(key):
            raise ValueError("You cannot add a NULL Content Key to a Vault.")

        if not self.has_table(service):
            self.create_table(service)

        if isinstance(kid, UUID):
            kid = kid.hex

        conn = self.con_pool.get()
        cursor = conn.cursor()

        try:
            cursor.execute(
                # TODO: SQL injection risk
                f"SELECT `id` FROM `{service}` WHERE `kid`=? AND `key_`=?",
                (kid, key)
            )
            if cursor.fetchone():
                # table already has this exact KID:KEY stored
                return True
            cursor.execute(
                # TODO: SQL injection risk
                f"INSERT INTO `{service}` (kid, key_) VALUES (?, ?)",
                (kid, key)
            )
        finally:
            conn.commit()
            cursor.close()
            self.con_pool.put(conn)

        return True

    def add_keys(self, service: str, kid_keys: dict[Union[UUID, str], str]) -> int:
        for kid, key in kid_keys.items():
            if not key or key.count("0") == len(key):
                raise ValueError("You cannot add a NULL Content Key to a Vault.")

        if not self.has_table(service):
            self.create_table(service)

        if not isinstance(kid_keys, dict):
            raise ValueError(f"The kid_keys provided is not a dictionary, {kid_keys!r}")
        if not all(isinstance(kid, (str, UUID)) and isinstance(key_, str) for kid, key_ in kid_keys.items()):
            raise ValueError("Expecting dict with Key of str/UUID and value of str.")

        if any(isinstance(kid, UUID) for kid, key_ in kid_keys.items()):
            kid_keys = {
                kid.hex if isinstance(kid, UUID) else kid: key_
                for kid, key_ in kid_keys.items()
            }

        conn = self.con_pool.get()
        cursor = conn.cursor()

        try:
            cursor.executemany(
                # TODO: SQL injection risk
                f"INSERT OR IGNORE INTO `{service}` (kid, key_) VALUES (?, ?)",
                kid_keys.items()
            )
            return cursor.rowcount
        finally:
            conn.commit()
            cursor.close()
            self.con_pool.put(conn)

    def get_services(self) -> Iterator[str]:
        conn = self.con_pool.get()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            for (name,) in cursor.fetchall():
                if name != "sqlite_sequence":
                    yield Services.get_tag(name)
        finally:
            cursor.close()
            self.con_pool.put(conn)

    def has_table(self, name: str) -> bool:
        """Check if the Vault has a Table with the specified name."""
        conn = self.con_pool.get()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT count(name) FROM sqlite_master WHERE type='table' AND name=?",
                (name,)
            )
            return cursor.fetchone()[0] == 1
        finally:
            cursor.close()
            self.con_pool.put(conn)

    def create_table(self, name: str):
        """Create a Table with the specified name if not yet created."""
        if self.has_table(name):
            return

        conn = self.con_pool.get()
        cursor = conn.cursor()

        try:
            cursor.execute(
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
        finally:
            conn.commit()
            cursor.close()
            self.con_pool.put(conn)


class ConnectionPool:
    def __init__(self, path: Union[str, Path], size: int):
        self._path = path
        self._size = size
        self._pool = Queue(self._size)
        self._lock = Lock()

    def _create_connection(self):
        return sqlite3.connect(self._path)

    def get(self) -> Connection:
        while True:
            try:
                return self._pool.get(block=False)
            except Empty:
                with self._lock:
                    if self._pool.qsize() < self._size:
                        return self._create_connection()
                    else:
                        # pool full, wait before retrying
                        time.sleep(0.1)

    def put(self, conn: Connection):
        self._pool.put(conn)
