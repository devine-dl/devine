from typing import Union

from .episode import Episode, Series
from .movie import Movie, Movies
from .song import Album, Song

Title_T = Union[Movie, Episode, Song]
Titles_T = Union[Movies, Series, Album]


__all__ = ("Episode", "Series", "Movie", "Movies", "Album", "Song", "Title_T", "Titles_T")
