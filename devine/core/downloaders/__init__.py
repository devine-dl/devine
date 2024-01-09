import asyncio

from ..config import config
from .aria2c import aria2c
from .curl_impersonate import curl_impersonate
from .requests import requests

downloader = {
    "aria2c": lambda *args, **kwargs: asyncio.run(aria2c(*args, **kwargs)),
    "curl_impersonate": curl_impersonate,
    "requests": requests
}[config.downloader]


__all__ = ("downloader", "aria2c", "curl_impersonate", "requests")
