from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urljoin

from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad
from m3u8.model import Key
from requests import Session


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

    def decrypt(self, path: Path) -> None:
        """Decrypt a Track with AES Clear Key DRM."""
        if not path or not path.exists():
            raise ValueError("Tried to decrypt a file that does not exist.")

        decrypted = AES. \
            new(self.key, AES.MODE_CBC, self.iv). \
            decrypt(pad(path.read_bytes(), AES.block_size))

        try:
            decrypted = unpad(decrypted, AES.block_size)
        except ValueError:
            # the decrypted data is likely already in the block size boundary
            pass

        decrypted_path = path.with_suffix(f".decrypted{path.suffix}")
        decrypted_path.write_bytes(decrypted)

        path.unlink()
        shutil.move(decrypted_path, path)

    @classmethod
    def from_m3u_key(cls, m3u_key: Key, session: Optional[Session] = None) -> ClearKey:
        """
        Load a ClearKey from an M3U(8) Playlist's EXT-X-KEY.

        Parameters:
            m3u_key: A Key object parsed from a m3u(8) playlist using
                the `m3u8` library.
            session: Optional session used to request external URIs with.
                Useful to set headers, proxies, cookies, and so forth.
        """
        if not isinstance(m3u_key, Key):
            raise ValueError(f"Provided M3U Key is in an unexpected type {m3u_key!r}")
        if not isinstance(session, (Session, type(None))):
            raise TypeError(f"Expected session to be a {Session}, not a {type(session)}")

        if not m3u_key.method.startswith("AES"):
            raise ValueError(f"Provided M3U Key is not an AES Clear Key, {m3u_key.method}")
        if not m3u_key.uri:
            raise ValueError("No URI in M3U Key, unable to get Key.")

        if not session:
            session = Session()

        if not session.headers.get("User-Agent"):
            # commonly needed default for HLS playlists
            session.headers["User-Agent"] = "smartexoplayer/1.1.0 (Linux;Android 8.0.0) ExoPlayerLib/2.13.3"

        if m3u_key.uri.startswith("data:"):
            media_types, data = m3u_key.uri[5:].split(",")
            media_types = media_types.split(";")
            if "base64" in media_types:
                data = base64.b64decode(data)
            key = data
        else:
            url = urljoin(m3u_key.base_uri, m3u_key.uri)
            res = session.get(url)
            res.raise_for_status()
            if not res.content:
                raise EOFError("Unexpected Empty Response by M3U Key URI.")
            if len(res.content) < 16:
                raise EOFError(f"Unexpected Length of Key ({len(res.content)} bytes) in M3U Key.")
            key = res.content

        if m3u_key.iv:
            iv = bytes.fromhex(m3u_key.iv.replace("0x", ""))
        else:
            iv = None

        return cls(key=key, iv=iv)


__all__ = ("ClearKey",)
