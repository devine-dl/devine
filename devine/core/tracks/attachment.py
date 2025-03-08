from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Optional, Union
from zlib import crc32
import requests
from urllib.parse import urlparse
from devine.core.config import config


class Attachment:
    def __init__(
        self,
        path: Union[Path, str, None] = None,
        url: Optional[str] = None,
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
        description: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        """
        Create a new Attachment.

        If providing a path, the file must already exist.
        If providing a URL, the file will be downloaded to the temp directory.
        Either path or url must be provided.

        If name is not provided it will use the file name (without extension).
        If mime_type is not provided, it will try to guess it.

        Args:
            path: Path to an existing file.
            url: URL to download the attachment from.
            name: Name of the attachment.
            mime_type: MIME type of the attachment.
            description: Description of the attachment.
            session: Optional requests session to use for downloading.
        """
        if path is None and url is None:
            raise ValueError("Either path or url must be provided.")

        if url:
            if not isinstance(url, str):
                raise ValueError("The attachment URL must be a string.")

            parsed_url = urlparse(url)
            file_name = os.path.basename(parsed_url.path) or "attachment"

            if name:
                file_name = f"{name.replace(' ', '_')}{os.path.splitext(file_name)[1]}"

            download_path = config.directories.temp / file_name

            try:
                session = session or requests.Session()
                response = session.get(url, stream=True)
                response.raise_for_status()

                with open(download_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                path = download_path
            except Exception as e:
                raise ValueError(f"Failed to download attachment from URL: {e}")

        if not isinstance(path, (str, Path)):
            raise ValueError("The attachment path must be provided.")

        path = Path(path)
        if not path.exists():
            raise ValueError("The attachment file does not exist.")

        name = (name or path.stem).strip()
        mime_type = (mime_type or "").strip() or None
        description = (description or "").strip() or None

        if not mime_type:
            mime_type = {
                ".ttf": "application/x-truetype-font",
                ".otf": "application/vnd.ms-opentype",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
            }.get(path.suffix.lower(), mimetypes.guess_type(path)[0])
            if not mime_type:
                raise ValueError("The attachment mime-type could not be automatically detected.")

        self.path = path
        self.name = name
        self.mime_type = mime_type
        self.description = description

    def __repr__(self) -> str:
        return "{name}({items})".format(
            name=self.__class__.__name__, items=", ".join([f"{k}={repr(v)}" for k, v in self.__dict__.items()])
        )

    def __str__(self) -> str:
        return " | ".join(filter(bool, ["ATT", self.name, self.mime_type, self.description]))

    @property
    def id(self) -> str:
        """Compute an ID from the attachment data."""
        checksum = crc32(self.path.read_bytes())
        return hex(checksum)

    @classmethod
    def from_url(
        cls,
        url: str,
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
        description: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> "Attachment":
        """
        Create an attachment from a URL.

        Args:
            url: URL to download the attachment from.
            name: Name of the attachment.
            mime_type: MIME type of the attachment.
            description: Description of the attachment.
            session: Optional requests session to use for downloading.

        Returns:
            Attachment: A new attachment instance.
        """
        return cls(url=url, name=name, mime_type=mime_type, description=description, session=session)


__all__ = ("Attachment",)
