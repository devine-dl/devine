from __future__ import annotations

from typing import Optional, Union
from urllib.parse import urljoin

import requests
from Cryptodome.Cipher import AES
from m3u8.model import Key

from devine.core.constants import TrackT


class ClearKey:
    """AES Clear Key DRM System."""
    def __init__(self, key: Union[bytes, str], iv: Optional[Union[bytes, str]] = None):
        """
        Generally IV should be provided where possible. If not provided, it will be
        set to \x00 of the same bit-size of the key.
        """
        if isinstance(key, str):
            key = bytes.fromhex(key.replace("0x", ""))
        if not isinstance(key, bytes):
            raise ValueError(f"Expected AES Key to be bytes, not {key!r}")
        if not iv:
            iv = b"\x00"
        if isinstance(iv, str):
            iv = bytes.fromhex(iv.replace("0x", ""))
        if not isinstance(iv, bytes):
            raise ValueError(f"Expected IV to be bytes, not {iv!r}")

        if len(iv) < len(key):
            iv = iv * (len(key) - len(iv) + 1)

        self.key: bytes = key
        self.iv: bytes = iv

    def decrypt(self, track: TrackT) -> None:
        """Decrypt a Track with AES Clear Key DRM."""
        if not track.path or not track.path.exists():
            raise ValueError("Tried to decrypt a track that has not yet been downloaded.")

        decrypted = AES. \
            new(self.key, AES.MODE_CBC, self.iv). \
            decrypt(track.path.read_bytes())

        decrypted_path = track.path.with_suffix(f".decrypted{track.path.suffix}")
        decrypted_path.write_bytes(decrypted)

        track.swap(decrypted_path)
        track.drm = None

    @classmethod
    def from_m3u_key(cls, m3u_key: Key, proxy: Optional[str] = None) -> ClearKey:
        if not isinstance(m3u_key, Key):
            raise ValueError(f"Provided M3U Key is in an unexpected type {m3u_key!r}")
        if not m3u_key.method.startswith("AES"):
            raise ValueError(f"Provided M3U Key is not an AES Clear Key, {m3u_key.method}")
        if not m3u_key.uri:
            raise ValueError("No URI in M3U Key, unable to get Key.")

        res = requests.get(
            url=urljoin(m3u_key.base_uri, m3u_key.uri),
            headers={
                "User-Agent": "smartexoplayer/1.1.0 (Linux;Android 8.0.0) ExoPlayerLib/2.13.3"
            },
            proxies={"all": proxy} if proxy else None
        )
        res.raise_for_status()
        if not res.content:
            raise EOFError("Unexpected Empty Response by M3U Key URI.")
        if len(res.content) < 16:
            raise EOFError(f"Unexpected Length of Key ({len(res.content)} bytes) in M3U Key.")

        key = res.content
        iv = None
        if m3u_key.iv:
            iv = bytes.fromhex(m3u_key.iv.replace("0x", ""))

        return cls(key=key, iv=iv)


__ALL__ = (ClearKey,)
