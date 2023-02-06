from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Union


class Chapter:
    line_1 = re.compile(r"^CHAPTER(?P<number>\d+)=(?P<timecode>[\d\\.]+)$")
    line_2 = re.compile(r"^CHAPTER(?P<number>\d+)NAME=(?P<title>[\d\\.]+)$")

    def __init__(self, number: int, timecode: str, title: Optional[str] = None):
        self.id = f"chapter-{number}"
        self.number = number
        self.timecode = timecode
        self.title = title

        if "." not in self.timecode:
            self.timecode += ".000"

    def __bool__(self) -> bool:
        return self.number and self.number >= 0 and self.timecode

    def __repr__(self) -> str:
        """
        OGM-based Simple Chapter Format intended for use with MKVToolNix.

        This format is not officially part of the Matroska spec. This was a format
        designed for OGM tools that MKVToolNix has since re-used. More Information:
        https://mkvtoolnix.download/doc/mkvmerge.html#mkvmerge.chapters.simple
        """
        return "CHAPTER{num}={time}\nCHAPTER{num}NAME={name}".format(
            num=f"{self.number:02}",
            time=self.timecode,
            name=self.title or ""
        )

    def __str__(self) -> str:
        return " | ".join(filter(bool, [
            "CHP",
            f"[{self.number:02}]",
            self.timecode,
            self.title
        ]))

    @property
    def named(self) -> bool:
        """Check if Chapter is named."""
        return bool(self.title)

    @classmethod
    def loads(cls, data: str) -> Chapter:
        """Load chapter data from a string."""
        lines = [x.strip() for x in data.strip().splitlines(keepends=False)]
        if len(lines) > 2:
            return cls.loads("\n".join(lines))
        one, two = lines

        one_m = cls.line_1.match(one)
        two_m = cls.line_2.match(two)
        if not one_m or not two_m:
            raise SyntaxError(f"An unexpected syntax error near:\n{one}\n{two}")

        one_str, timecode = one_m.groups()
        two_str, title = two_m.groups()
        one_num, two_num = int(one_str.lstrip("0")), int(two_str.lstrip("0"))

        if one_num != two_num:
            raise SyntaxError(f"The chapter numbers ({one_num},{two_num}) does not match.")
        if not timecode:
            raise SyntaxError("The timecode is missing.")
        if not title:
            title = None

        return cls(number=one_num, timecode=timecode, title=title)

    @classmethod
    def load(cls, path: Union[Path, str]) -> Chapter:
        """Load chapter data from a file."""
        if isinstance(path, str):
            path = Path(path)
        return cls.loads(path.read_text(encoding="utf8"))

    def dumps(self) -> str:
        """Return chapter data as a string."""
        return repr(self)

    def dump(self, path: Union[Path, str]) -> int:
        """Write chapter data to a file."""
        if isinstance(path, str):
            path = Path(path)
        return path.write_text(self.dumps(), encoding="utf8")


__ALL__ = (Chapter,)
