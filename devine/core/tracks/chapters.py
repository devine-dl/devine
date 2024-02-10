from __future__ import annotations

import re
from abc import ABC
from pathlib import Path
from typing import Any, Iterable, Optional, Union
from zlib import crc32

from sortedcontainers import SortedKeyList

from devine.core.tracks import Chapter

OGM_SIMPLE_LINE_1_FORMAT = re.compile(r"^CHAPTER(?P<number>\d+)=(?P<timestamp>\d{2,}:\d{2}:\d{2}\.\d{3})$")
OGM_SIMPLE_LINE_2_FORMAT = re.compile(r"^CHAPTER(?P<number>\d+)NAME=(?P<name>.*)$")


class Chapters(SortedKeyList, ABC):
    def __init__(self, iterable: Optional[Iterable[Chapter]] = None):
        super().__init__(key=lambda x: x.timestamp or 0)
        for chapter in iterable or []:
            self.add(chapter)

    def __repr__(self) -> str:
        return "{name}({items})".format(
            name=self.__class__.__name__,
            items=", ".join([f"{k}={repr(v)}" for k, v in self.__dict__.items()])
        )

    def __str__(self) -> str:
        return "\n".join([
            " | ".join(filter(bool, [
                "CHP",
                f"[{i:02}]",
                chapter.timestamp,
                chapter.name
            ]))
            for i, chapter in enumerate(self, start=1)
        ])

    @classmethod
    def loads(cls, data: str) -> Chapters:
        """Load chapter data from a string."""
        lines = [
            line.strip()
            for line in data.strip().splitlines(keepends=False)
        ]

        if len(lines) % 2 != 0:
            raise ValueError("The number of chapter lines must be even.")

        chapters = []

        for line_1, line_2 in zip(lines[::2], lines[1::2]):
            line_1_match = OGM_SIMPLE_LINE_1_FORMAT.match(line_1)
            if not line_1_match:
                raise SyntaxError(f"An unexpected syntax error occurred on: {line_1}")
            line_2_match = OGM_SIMPLE_LINE_2_FORMAT.match(line_2)
            if not line_2_match:
                raise SyntaxError(f"An unexpected syntax error occurred on: {line_2}")

            line_1_number, timestamp = line_1_match.groups()
            line_2_number, name = line_2_match.groups()

            if line_1_number != line_2_number:
                raise SyntaxError(
                    f"The chapter numbers {line_1_number} and {line_2_number} do not match on:\n{line_1}\n{line_2}")

            if not timestamp:
                raise SyntaxError(f"The timestamp is missing on: {line_1}")

            chapters.append(Chapter(timestamp, name))

        return cls(chapters)

    @classmethod
    def load(cls, path: Union[Path, str]) -> Chapters:
        """Load chapter data from a file."""
        if isinstance(path, str):
            path = Path(path)
        return cls.loads(path.read_text(encoding="utf8"))

    def dumps(self, fallback_name: str = "") -> str:
        """
        Return chapter data in OGM-based Simple Chapter format.
        https://mkvtoolnix.download/doc/mkvmerge.html#mkvmerge.chapters.simple

        Parameters:
            fallback_name: Name used for Chapters without a Name set.

        The fallback name can use the following variables in f-string style:

        - {i}: The Chapter number starting at 1.
               E.g., `"Chapter {i}"`: "Chapter 1", "Intro", "Chapter 3".
        - {j}: A number starting at 1 that increments any time a Chapter has no name.
               E.g., `"Chapter {j}"`: "Chapter 1", "Intro", "Chapter 2".

        These are formatted with f-strings, directives are supported.
        For example, `"Chapter {i:02}"` will result in `"Chapter 01"`.
        """
        chapters = []
        j = 0

        for i, chapter in enumerate(self, start=1):
            if not chapter.name:
                j += 1
            chapters.append("CHAPTER{num}={time}\nCHAPTER{num}NAME={name}".format(
                num=f"{i:02}",
                time=chapter.timestamp,
                name=chapter.name or fallback_name.format(
                    i=i,
                    j=j
                )
            ))

        return "\n".join(chapters)

    def dump(self, path: Union[Path, str], *args: Any, **kwargs: Any) -> int:
        """
        Write chapter data in OGM-based Simple Chapter format to a file.

        Parameters:
            path: The file path to write the Chapter data to, overwriting
                any existing data.

        See `Chapters.dumps` for more parameter documentation.
        """
        if isinstance(path, str):
            path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        ogm_text = self.dumps(*args, **kwargs)
        return path.write_text(ogm_text, encoding="utf8")

    def add(self, value: Chapter) -> None:
        if not isinstance(value, Chapter):
            raise TypeError(f"Can only add {Chapter} objects, not {type(value)}")

        if any(chapter.timestamp == value.timestamp for chapter in self):
            raise ValueError(f"A Chapter with the Timestamp {value.timestamp} already exists")

        super().add(value)

        if not any(chapter.timestamp == "00:00:00.000" for chapter in self):
            self.add(Chapter(0))

    @property
    def id(self) -> str:
        """Compute an ID from the Chapter data."""
        checksum = crc32("\n".join([
            chapter.id
            for chapter in self
        ]).encode("utf8"))
        return hex(checksum)


__all__ = ("Chapters", "Chapter")
