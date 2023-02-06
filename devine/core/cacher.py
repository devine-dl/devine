from __future__ import annotations

import zlib
from datetime import datetime, timedelta
from os import stat_result
from pathlib import Path
from typing import Optional, Any, Union

import jsonpickle
import jwt

from devine.core.config import config


EXP_T = Union[datetime, str, int, float]


class Cacher:
    """Cacher for Services to get and set arbitrary data with expiration dates."""

    def __init__(
        self,
        service_tag: str,
        key: Optional[str] = None,
        version: Optional[int] = 1,
        data: Optional[Any] = None,
        expiration: Optional[datetime] = None
    ) -> None:
        self.service_tag = service_tag
        self.key = key
        self.version = version
        self.data = data or {}
        self.expiration = expiration

        if self.expiration and self.expired:
            # if its expired, remove the data for safety and delete cache file
            self.data = None
            self.path.unlink()

    def __bool__(self) -> bool:
        return bool(self.data)

    @property
    def path(self) -> Path:
        """Get the path at which the cache will be read and written."""
        return (config.directories.cache / self.service_tag / self.key).with_suffix(".json")

    @property
    def expired(self) -> bool:
        return self.expiration and self.expiration < datetime.utcnow()

    def get(self, key: str, version: int = 1) -> Cacher:
        """
        Get Cached data for the Service by Key.
        :param key: the filename to save the data to, should be url-safe.
        :param version: the config data version you expect to use.
        :returns: Cache object containing the cached data or None if the file does not exist.
        """
        cache = Cacher(self.service_tag, key, version)
        if cache.path.is_file():
            data = jsonpickle.loads(cache.path.read_text(encoding="utf8"))
            payload = data.copy()
            del payload["crc32"]
            checksum = data["crc32"]
            calculated = zlib.crc32(jsonpickle.dumps(payload).encode("utf8"))
            if calculated != checksum:
                raise ValueError(
                    f"The checksum of the Cache payload mismatched. "
                    f"Checksum: {checksum} !== Calculated: {calculated}"
                )
            cache.data = data["data"]
            cache.expiration = data["expiration"]
            cache.version = data["version"]
            if cache.version != version:
                raise ValueError(
                    f"The version of your {self.service_tag} {key} cache is outdated. "
                    f"Please delete: {cache.path}"
                )
        return cache

    def set(self, data: Any, expiration: Optional[EXP_T] = None) -> Any:
        """
        Set Cached data for the Service by Key.
        :param data: absolutely anything including None.
        :param expiration: when the data expires, optional. Can be ISO 8601, seconds
            til expiration, unix timestamp, or a datetime object.
        :returns: the data provided for quick wrapping of functions or vars.
        """
        self.data = data

        if not expiration:
            try:
                expiration = jwt.decode(self.data, options={"verify_signature": False})["exp"]
            except jwt.DecodeError:
                pass

        self.expiration = self._resolve_datetime(expiration) if expiration else None

        payload = {
            "data": self.data,
            "expiration": self.expiration,
            "version": self.version
        }
        payload["crc32"] = zlib.crc32(jsonpickle.dumps(payload).encode("utf8"))

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(jsonpickle.dumps(payload))

        return self.data

    def stat(self) -> stat_result:
        """
        Get Cache file OS Stat data like Creation Time, Modified Time, and such.
        :returns: an os.stat_result tuple
        """
        return self.path.stat()

    @staticmethod
    def _resolve_datetime(timestamp: EXP_T) -> datetime:
        """
        Resolve multiple formats of a Datetime or Timestamp to an absolute Datetime.

        Examples:
            >>> now = datetime.now()
            datetime.datetime(2022, 6, 27, 9, 49, 13, 657208)
            >>> iso8601 = now.isoformat()
            '2022-06-27T09:49:13.657208'
            >>> Cacher._resolve_datetime(iso8601)
            datetime.datetime(2022, 6, 27, 9, 49, 13, 657208)
            >>> Cacher._resolve_datetime(iso8601 + "Z")
            datetime.datetime(2022, 6, 27, 9, 49, 13, 657208)
            >>> Cacher._resolve_datetime(3600)
            datetime.datetime(2022, 6, 27, 10, 52, 50, 657208)
            >>> Cacher._resolve_datetime('3600')
            datetime.datetime(2022, 6, 27, 10, 52, 51, 657208)
            >>> Cacher._resolve_datetime(7800.113)
            datetime.datetime(2022, 6, 27, 11, 59, 13, 770208)

        In the int/float examples you may notice that it did not return now + 3600 seconds
        but rather something a bit more than that. This is because it did not resolve 3600
        seconds from the `now` variable but from right now as the function was called.
        """
        if isinstance(timestamp, datetime):
            return timestamp
        if isinstance(timestamp, str):
            if timestamp.endswith("Z"):
                # fromisoformat doesn't accept the final Z
                timestamp = timestamp.split("Z")[0]
            try:
                return datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = float(timestamp)
        try:
            timestamp = datetime.fromtimestamp(timestamp)
        except ValueError:
            raise ValueError(f"Unrecognized Timestamp value {timestamp!r}")
        if timestamp < datetime.now():
            # timestamp is likely an amount of seconds til expiration
            # or, it's an already expired timestamp which is unlikely
            timestamp = timestamp + timedelta(seconds=datetime.now().timestamp())
        return timestamp
