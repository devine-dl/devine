import asyncio
from functools import partial

from devine.core.config import config
from devine.core.downloaders import aria2c, saldl


downloader = {
    "aria2c": partial(asyncio.run, aria2c),
    "saldl": partial(asyncio.run, saldl)
}[config.downloader]
