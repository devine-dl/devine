import random
from typing import Optional, Union

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

        proxy = random.choice(servers)

        if "://" not in proxy:
            # TODO: Improve the test for a valid URI
            raise ValueError(f"The proxy '{proxy}' is not a valid proxy URI supported by Python-Requests.")

        return proxy
