from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional, Union
from zlib import crc32


class Attachment:
    def __init__(
        self,
        path: Union[Path, str],
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
        description: Optional[str] = None
    ):
        """
        Create a new Attachment.

        If name is not provided it will use the file name (without extension).
        If mime_type is not provided, it will try to guess it.
        """
        if not isinstance(path, (str, Path)):
            raise ValueError("The attachment path must be provided.")
        if not isinstance(name, (str, type(None))):
            raise ValueError("The attachment name must be provided.")

        path = Path(path)
        if not path.exists():
            raise ValueError("The attachment file does not exist.")

        name = (name or path.stem).strip()
        mime_type = (mime_type or "").strip() or None
        description = (description or "").strip() or None

        if not mime_type:
            mime_type = {
                ".ttf": "application/x-truetype-font",
                ".otf": "application/vnd.ms-opentype"
            }.get(path.suffix, mimetypes.guess_type(path)[0])
            if not mime_type:
                raise ValueError("The attachment mime-type could not be automatically detected.")

        self.path = path
        self.name = name
        self.mime_type = mime_type
        self.description = description

    def __repr__(self) -> str:
        return "{name}({items})".format(
            name=self.__class__.__name__,
            items=", ".join([f"{k}={repr(v)}" for k, v in self.__dict__.items()])
        )

    def __str__(self) -> str:
        return " | ".join(filter(bool, [
            "ATT",
            self.name,
            self.mime_type,
            self.description
        ]))

    @property
    def id(self) -> str:
        """Compute an ID from the attachment data."""
        checksum = crc32(self.path.read_bytes())
        return hex(checksum)


__all__ = ("Attachment",)
