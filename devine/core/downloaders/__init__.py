import asyncio

from .aria2c import aria2c
from .requests import requests
from .saldl import saldl
from ..config import config

downloader = {
    "aria2c": lambda *args, **kwargs: asyncio.run(aria2c(*args, **kwargs)),
    "requests": requests,
    "saldl": lambda *args, **kwargs: asyncio.run(saldl(*args, **kwargs))
}[config.downloader]


__ALL__ = (downloader, aria2c, requests, saldl)
