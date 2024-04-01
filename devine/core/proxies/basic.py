import random
from typing import Optional, Union

from requests.utils import prepend_scheme_if_needed
from urllib3.util import parse_url

from devine.core.proxies.proxy import Proxy


class Basic(Proxy):
    def __init__(self, **countries: dict[str, Union[str, list[str]]]):
        """Basic Proxy Service using Proxies specified in the config."""
        self.countries = {
            k.lower(): v
            for k, v in countries.items()
        }

    def __repr__(self) -> str:
        countries = len(self.countries)
        servers = len(self.countries.values())

        return f"{countries} Countr{['ies', 'y'][countries == 1]} ({servers} Server{['s', ''][servers == 1]})"

    def get_proxy(self, query: str) -> Optional[str]:
        """Get a proxy URI from the config."""
        query = query.lower()

        servers = self.countries.get(query)
        if not servers:
            return

        if isinstance(servers, str):
            proxy = servers
        else:
            proxy = random.choice(servers)

        proxy = prepend_scheme_if_needed(proxy, "http")
        parsed_proxy = parse_url(proxy)
        if not parsed_proxy.host:
            raise ValueError(f"The proxy '{proxy}' is not a valid proxy URI supported by Python-Requests.")

        return proxy
