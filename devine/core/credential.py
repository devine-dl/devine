from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from typing import Optional, Union


class Credential:
    """Username (or Email) and Password Credential."""

    def __init__(self, username: str, password: str, extra: Optional[str] = None):
        self.username = username
        self.password = password
        self.extra = extra
        self.sha1 = hashlib.sha1(self.dumps().encode()).hexdigest()

    def __bool__(self) -> bool:
        return bool(self.username) and bool(self.password)

    def __str__(self) -> str:
        return self.dumps()

    def __repr__(self) -> str:
        return "{name}({items})".format(
            name=self.__class__.__name__,
            items=", ".join([f"{k}={repr(v)}" for k, v in self.__dict__.items()])
        )

    def dumps(self) -> str:
        """Return credential data as a string."""
        return f"{self.username}:{self.password}" + (f":{self.extra}" if self.extra else "")

    def dump(self, path: Union[Path, str]) -> int:
        """Write credential data to a file."""
        if isinstance(path, str):
            path = Path(path)
        return path.write_text(self.dumps(), encoding="utf8")

    def as_base64(self, with_extra: bool = False, encode_password: bool = False, encode_extra: bool = False) -> str:
        """
        Dump Credential as a Base64-encoded string in Basic Authorization style.
        encode_password and encode_extra will also Base64-encode the password and extra respectively.
        """
        value = f"{self.username}:"
        if encode_password:
            value += base64.b64encode(self.password.encode()).decode()
        else:
            value += self.password
        if with_extra and self.extra:
            if encode_extra:
                value += f":{base64.b64encode(self.extra.encode()).decode()}"
            else:
                value += f":{self.extra}"
        return base64.b64encode(value.encode()).decode()

    @classmethod
    def loads(cls, text: str) -> Credential:
        """
        Load credential from a text string.

        Format: {username}:{password}
        Rules:
            Only one Credential must be in this text contents.
            All whitespace before and after all text will be removed.
            Any whitespace between text will be kept and used.
            The credential can be spanned across one or multiple lines as long as it
                abides with all the above rules and the format.

        Example that follows the format and rules:
            `\tJohnd\noe@gm\n\rail.com\n:Pass1\n23\n\r  \t  \t`
            >>>Credential(username='Johndoe@gmail.com', password='Pass123')
        """
        text = "".join([
            x.strip() for x in text.splitlines(keepends=False)
        ]).strip()
        credential = re.fullmatch(r"^([^:]+?):([^:]+?)(?::(.+))?$", text)
        if credential:
            return cls(*credential.groups())
        raise ValueError("No credentials found in text string. Expecting the format `username:password`")

    @classmethod
    def load(cls, path: Path) -> Credential:
        """
        Load Credential from a file path.
        Use Credential.loads() for loading from text content and seeing the rules and
        format expected to be found in the URIs contents.
        """
        return cls.loads(path.read_text("utf8"))
