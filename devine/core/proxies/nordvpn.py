import json
import re
from typing import Optional

import requests

from devine.core.proxies.proxy import Proxy


class NordVPN(Proxy):
    def __init__(self, username: str, password: str, server_map: Optional[dict[str, int]] = None):
        """
        Proxy Service using NordVPN Service Credentials.

        A username and password must be provided. These are Service Credentials, not your Login Credentials.
        The Service Credentials can be found here: https://my.nordaccount.com/dashboard/nordvpn/
        """
        if not username:
            raise ValueError("No Username was provided to the NordVPN Proxy Service.")
        if not password:
            raise ValueError("No Password was provided to the NordVPN Proxy Service.")
        if not re.match(r"^[a-z0-9]{48}$", username + password, re.IGNORECASE) or "@" in username:
            raise ValueError(
                "The Username and Password must be NordVPN Service Credentials, not your Login Credentials. "
                "The Service Credentials can be found here: https://my.nordaccount.com/dashboard/nordvpn/"
            )

        if server_map is not None and not isinstance(server_map, dict):
            raise TypeError(f"Expected server_map to be a dict mapping a region to a server ID, not '{server_map!r}'.")

        self.username = username
        self.password = password
        self.server_map = server_map or {}

        self.countries = self.get_countries()

    def __repr__(self) -> str:
        countries = len(self.countries)
        servers = sum(x["servers_count"] for x in self.countries)

        return f"{countries} Countr{['ies', 'y'][countries == 1]} ({servers} Server{['s', ''][servers == 1]})"

    def get_proxy(self, query: str) -> Optional[str]:
        """
        Get an HTTP(SSL) proxy URI for a NordVPN server.

        HTTP proxies under port 80 were disabled on the 15th of Feb, 2021:
        https://nordvpn.com/blog/removing-http-proxies
        """
        query = query.lower()
        if re.match(r"^[a-z]{2}\d+$", query):
            # country and nordvpn server id, e.g., us1, fr1234
            hostname = f"{query}.nordvpn.com"
        else:
            if query.isdigit():
                # country id
                country = self.get_country(by_id=int(query))
            elif re.match(r"^[a-z]+$", query):
                # country code
                country = self.get_country(by_code=query)
            else:
                raise ValueError(f"The query provided is unsupported and unrecognized: {query}")
            if not country:
                # NordVPN doesnt have servers in this region
                return

            server_mapping = self.server_map.get(country["code"].lower())
            if server_mapping:
                # country was set to a specific server ID in config
                hostname = f"{country['code'].lower()}{server_mapping}.nordvpn.com"
            else:
                # get the recommended server ID
                recommended_servers = self.get_recommended_servers(country["id"])
                if not recommended_servers:
                    raise ValueError(
                        f"The NordVPN Country {query} currently has no recommended servers. "
                        "Try again later. If the issue persists, double-check the query."
                    )
                hostname = recommended_servers[0]["hostname"]

        if hostname.startswith("gb"):
            # NordVPN uses the alpha2 of 'GB' in API responses, but 'UK' in the hostname
            hostname = f"gb{hostname[2:]}"

        return f"https://{self.username}:{self.password}@{hostname}:89"

    def get_country(
        self,
        by_id: Optional[int] = None,
        by_code: Optional[str] = None
    ) -> Optional[dict]:
        """Search for a Country and it's metadata."""
        if all(x is None for x in (by_id, by_code)):
            raise ValueError("At least one search query must be made.")

        for country in self.countries:
            if all([
                by_id is None or country["id"] == int(by_id),
                by_code is None or country["code"] == by_code.upper()
            ]):
                return country

    @staticmethod
    def get_recommended_servers(country_id: int) -> list[dict]:
        """
        Get the list of recommended Servers for a Country.

        Note: There may not always be more than one recommended server.
        """
        res = requests.get(
            url="https://nordvpn.com/wp-admin/admin-ajax.php",
            params={
                "action": "servers_recommendations",
                "filters": json.dumps({"country_id": country_id})
            }
        )
        if not res.ok:
            raise ValueError(f"Failed to get a list of NordVPN countries [{res.status_code}]")

        try:
            return res.json()
        except json.JSONDecodeError:
            raise ValueError("Could not decode list of NordVPN countries, not JSON data.")

    @staticmethod
    def get_countries() -> list[dict]:
        """Get a list of available Countries and their metadata."""
        res = requests.get(
            url="https://nordvpn.com/wp-admin/admin-ajax.php",
            params={"action": "servers_countries"}
        )
        if not res.ok:
            raise ValueError(f"Failed to get a list of NordVPN countries [{res.status_code}]")

        try:
            return res.json()
        except json.JSONDecodeError:
            raise ValueError("Could not decode list of NordVPN countries, not JSON data.")
