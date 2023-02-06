from typing import Union

from .episode import Episode, Series
from .movie import Movie, Movies
from .song import Song, Album


Title_T = Union[Movie, Episode, Song]
Titles_T = Union[Movies, Series, Album]
