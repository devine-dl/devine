from __future__ import annotations

from abc import abstractmethod
from typing import Any, Optional, Union

from langcodes import Language
from pymediainfo import MediaInfo

from devine.core.tracks import Tracks


class Title:
    def __init__(
        self,
        id_: Any,
        service: type,
        language: Optional[Union[str, Language]] = None,
        data: Optional[Any] = None
    ) -> None:
        """
        Media Title from a Service.

        Parameters:
            id_: An identifier for this specific title. It must be unique. Can be of any
                value.
            service: Service class that this title is from.
            language: The original recorded language for the title. If that information
                is not available, this should not be set to anything.
            data: Arbitrary storage for the title. Often used to store extra metadata
                information, IDs, URIs, and so on.
        """
        if not id_:  # includes 0, false, and similar values, this is intended
            raise ValueError("A unique ID must be provided")
        if hasattr(id_, "__len__") and len(id_) < 4:
            raise ValueError("The unique ID is not large enough, clash likely.")

        if not service:
            raise ValueError("Service class must be provided")
        if not isinstance(service, type):
            raise TypeError(f"Expected service to be a Class (type), not {service!r}")

        if language is not None:
            if isinstance(language, str):
                language = Language.get(language)
            elif not isinstance(language, Language):
                raise TypeError(f"Expected language to be a {Language} or str, not {language!r}")

        self.id = id_
        self.service = service
        self.language = language
        self.data = data

        self.tracks = Tracks()

    def __eq__(self, other: Title) -> bool:
        return self.id == other.id

    @abstractmethod
    def get_filename(self, media_info: MediaInfo, folder: bool = False, show_service: bool = True) -> str:
        """
        Get a Filename for this Title with the provided Media Info.
        All filenames should be sanitized with the sanitize_filename() utility function.

        Parameters:
            media_info: MediaInfo object of the file this name will be used for.
            folder: This filename will be used as a folder name. Some changes may want to
                be made if this is the case.
            show_service: Show the service tag (e.g., iT, NF) in the filename.
        """


__all__ = ("Title",)
