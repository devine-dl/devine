from __future__ import annotations

import re
from typing import Optional, Union
from zlib import crc32

TIMESTAMP_FORMAT = re.compile(r"^(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})(?P<ms>.\d{3}|)$")


class Chapter:
    def __init__(self, timestamp: Union[str, int, float], name: Optional[str] = None):
        """
        Create a new Chapter with a Timestamp and optional name.

        The timestamp may be in the following formats:
        - "HH:MM:SS" string, e.g., `25:05:23`.
        - "HH:MM:SS.mss" string, e.g., `25:05:23.120`.
        - a timecode integer in milliseconds, e.g., `90323120` is `25:05:23.120`.
        - a timecode float in seconds, e.g., `90323.12` is `25:05:23.120`.

        If you have a timecode integer in seconds, just multiply it by 1000.
        If you have a timecode float in milliseconds (no decimal value), just convert
        it to an integer.
        """
        if timestamp is None:
            raise ValueError("The timestamp must be provided.")

        if not isinstance(timestamp, (str, int, float)):
            raise TypeError(f"Expected timestamp to be {str}, {int} or {float}, not {type(timestamp)}")
        if not isinstance(name, (str, type(None))):
            raise TypeError(f"Expected name to be {str}, not {type(name)}")

        if not isinstance(timestamp, str):
            if isinstance(timestamp, int):  # ms
                hours, remainder = divmod(timestamp, 1000 * 60 * 60)
                minutes, remainder = divmod(remainder, 1000 * 60)
                seconds, ms = divmod(remainder, 1000)
            elif isinstance(timestamp, float):  # seconds.ms
                hours, remainder = divmod(timestamp, 60 * 60)
                minutes, remainder = divmod(remainder, 60)
                seconds, ms = divmod(int(remainder * 1000), 1000)
            else:
                raise TypeError
            timestamp = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}.{str(ms).zfill(3)[:3]}"

        timestamp_m = TIMESTAMP_FORMAT.match(timestamp)
        if not timestamp_m:
            raise ValueError(f"The timestamp format is invalid: {timestamp}")

        hour, minute, second, ms = timestamp_m.groups()
        if not ms:
            timestamp += ".000"

        self.timestamp = timestamp
        self.name = name

    def __repr__(self) -> str:
        return "{name}({items})".format(
            name=self.__class__.__name__,
            items=", ".join([f"{k}={repr(v)}" for k, v in self.__dict__.items()])
        )

    def __str__(self) -> str:
        return " | ".join(filter(bool, [
            "CHP",
            self.timestamp,
            self.name
        ]))

    @property
    def id(self) -> str:
        """Compute an ID from the Chapter data."""
        checksum = crc32(str(self).encode("utf8"))
        return hex(checksum)

    @property
    def named(self) -> bool:
        """Check if Chapter is named."""
        return bool(self.name)


__all__ = ("Chapter",)
