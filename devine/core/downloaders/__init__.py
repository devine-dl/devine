import asyncio

from ..config import config
from .aria2c import aria2c
from .requests import requests

downloader = {
    "aria2c": lambda *args, **kwargs: asyncio.run(aria2c(*args, **kwargs)),
    "requests": requests
}[config.downloader]


__all__ = ("downloader", "aria2c", "requests")
