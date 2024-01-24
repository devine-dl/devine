from typing import Iterator, Optional, Union
from uuid import UUID

from requests import Session

from devine.core import __version__
from devine.core.vault import Vault


class API(Vault):
    """Key Vault using a simple RESTful HTTP API call."""

    def __init__(self, name: str, uri: str, token: str):
        super().__init__(name)
        self.uri = uri.rstrip("/")
        self.session = Session()
        self.session.headers.update({
            "User-Agent": f"Devine v{__version__}"
        })
        self.session.headers.update({
            "Authorization": f"Bearer {token}"
        })

    def get_key(self, kid: Union[UUID, str], service: str) -> Optional[str]:
        if isinstance(kid, UUID):
            kid = kid.hex

        data = self.session.get(
            url=f"{self.uri}/{service.lower()}/{kid}",
            headers={
                "Accept": "application/json"
            }
        ).json()

        code = int(data.get("code", 0))
        message = data.get("message")
        error = {
            0: None,
            1: Exceptions.AuthRejected,
            2: Exceptions.TooManyRequests,
            3: Exceptions.ServiceTagInvalid,
            4: Exceptions.KeyIdInvalid
        }.get(code, ValueError)

        if error:
            raise error(f"{message} ({code})")

        content_key = data.get("content_key")
        if not content_key:
            return None

        if not isinstance(content_key, str):
            raise ValueError(f"Expected {content_key} to be {str}, was {type(content_key)}")

        return content_key

    def get_keys(self, service: str) -> Iterator[tuple[str, str]]:
        page = 1

        while True:
            data = self.session.get(
                url=f"{self.uri}/{service.lower()}",
                params={
                    "page": page,
                    "total": 10
                },
                headers={
                    "Accept": "application/json"
                }
            ).json()

            code = int(data.get("code", 0))
            message = data.get("message")
            error = {
                0: None,
                1: Exceptions.AuthRejected,
                2: Exceptions.TooManyRequests,
                3: Exceptions.PageInvalid,
                4: Exceptions.ServiceTagInvalid,
            }.get(code, ValueError)

            if error:
                raise error(f"{message} ({code})")

            content_keys = data.get("content_keys")
            if content_keys:
                if not isinstance(content_keys, dict):
                    raise ValueError(f"Expected {content_keys} to be {dict}, was {type(content_keys)}")

                for key_id, key in content_keys.items():
                    yield key_id, key

            pages = int(data["pages"])
            if pages <= page:
                break

            page += 1

    def add_key(self, service: str, kid: Union[UUID, str], key: str) -> bool:
        if isinstance(kid, UUID):
            kid = kid.hex

        data = self.session.post(
            url=f"{self.uri}/{service.lower()}/{kid}",
            json={
                "content_key": key
            },
            headers={
                "Accept": "application/json"
            }
        ).json()

        code = int(data.get("code", 0))
        message = data.get("message")
        error = {
            0: None,
            1: Exceptions.AuthRejected,
            2: Exceptions.TooManyRequests,
            3: Exceptions.ServiceTagInvalid,
            4: Exceptions.KeyIdInvalid,
            5: Exceptions.ContentKeyInvalid
        }.get(code, ValueError)

        if error:
            raise error(f"{message} ({code})")

        # the kid:key was new to the vault (optional)
        added = bool(data.get("added"))
        # the key for kid was changed/updated (optional)
        updated = bool(data.get("updated"))

        return added or updated

    def add_keys(self, service: str, kid_keys: dict[Union[UUID, str], str]) -> int:
        data = self.session.post(
            url=f"{self.uri}/{service.lower()}",
            json={
                "content_keys": {
                    str(kid).replace("-", ""): key
                    for kid, key in kid_keys.items()
                }
            },
            headers={
                "Accept": "application/json"
            }
        ).json()

        code = int(data.get("code", 0))
        message = data.get("message")
        error = {
            0: None,
            1: Exceptions.AuthRejected,
            2: Exceptions.TooManyRequests,
            3: Exceptions.ServiceTagInvalid,
            4: Exceptions.KeyIdInvalid,
            5: Exceptions.ContentKeyInvalid
        }.get(code, ValueError)

        if error:
            raise error(f"{message} ({code})")

        # each kid:key that was new to the vault (optional)
        added = int(data.get("added"))
        # each key for a kid that was changed/updated (optional)
        updated = int(data.get("updated"))

        return added + updated

    def get_services(self) -> Iterator[str]:
        data = self.session.post(
            url=self.uri,
            headers={
                "Accept": "application/json"
            }
        ).json()

        code = int(data.get("code", 0))
        message = data.get("message")
        error = {
            0: None,
            1: Exceptions.AuthRejected,
            2: Exceptions.TooManyRequests,
        }.get(code, ValueError)

        if error:
            raise error(f"{message} ({code})")

        service_list = data.get("service_list", [])

        if not isinstance(service_list, list):
            raise ValueError(f"Expected {service_list} to be {list}, was {type(service_list)}")

        for service in service_list:
            yield service


class Exceptions:
    class AuthRejected(Exception):
        """Authentication Error Occurred, is your token valid? Do you have permission to make this call?"""

    class TooManyRequests(Exception):
        """Rate Limited; Sent too many requests in a given amount of time."""

    class PageInvalid(Exception):
        """Requested page does not exist."""

    class ServiceTagInvalid(Exception):
        """The Service Tag is invalid."""

    class KeyIdInvalid(Exception):
        """The Key ID is invalid."""

    class ContentKeyInvalid(Exception):
        """The Content Key is invalid."""
