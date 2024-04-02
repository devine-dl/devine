import random
import re
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

        match = re.match(r"^([a-z]{2})(\d+)?$", query, re.IGNORECASE)
        if not match:
            raise ValueError(f"The query \"{query}\" was not recognized...")

        country_code = match.group(1)
        entry = match.group(2)

        servers: Optional[Union[str, list[str]]] = self.countries.get(country_code)
        if not servers:
            raise ValueError(f"There's no proxies configured for \"{country_code}\"...")

        if isinstance(servers, str):
            proxy = servers
        elif entry:
            try:
                proxy = servers[int(entry) - 1]
            except IndexError:
                raise ValueError(
                    f"There's only {len(servers)} prox{'y' if len(servers) == 1 else 'ies'} "
                    f"for \"{country_code}\"..."
                )
        else:
            proxy = random.choice(servers)

        proxy = prepend_scheme_if_needed(proxy, "http")
        parsed_proxy = parse_url(proxy)
        if not parsed_proxy.host:
            raise ValueError(f"The proxy '{proxy}' is not a valid proxy URI supported by Python-Requests.")

        return proxy
