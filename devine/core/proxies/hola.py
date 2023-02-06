import random
import re
import subprocess
from typing import Optional

from devine.core.proxies.proxy import Proxy
from devine.core.utilities import get_binary_path


class Hola(Proxy):
    def __init__(self):
        """
        Proxy Service using Hola's direct connections via the hola-proxy project.
        https://github.com/Snawoot/hola-proxy
        """
        self.binary = get_binary_path("hola-proxy")
        if not self.binary:
            raise EnvironmentError("hola-proxy executable not found but is required for the Hola proxy provider.")

        self.countries = self.get_countries()

    def __repr__(self) -> str:
        countries = len(self.countries)

        return f"{countries} Countr{['ies', 'y'][countries == 1]}"

    def get_proxy(self, query: str) -> Optional[str]:
        """
        Get an HTTP proxy URI for a Datacenter ('direct') or Residential ('lum') Hola server.

        TODO: - Add ability to select 'lum' proxies (residential proxies).
              - Return and use Proxy Authorization
        """
        query = query.lower()

        p = subprocess.check_output([
            self.binary,
            "-country", query,
            "-list-proxies"
        ], stderr=subprocess.STDOUT).decode()

        if "Transaction error: temporary ban detected." in p:
            raise ConnectionError("Hola banned your IP temporarily from it's services. Try change your IP.")

        username, password, proxy_authorization = re.search(
            r"Login: (.*)\nPassword: (.*)\nProxy-Authorization: (.*)", p
        ).groups()

        servers = re.findall(r"(zagent.*)", p)
        proxies = []
        for server in servers:
            host, ip_address, direct, peer, hola, trial, trial_peer, vendor = server.split(",")
            proxies.append(f"http://{username}:{password}@{ip_address}:{peer}")

        proxy = random.choice(proxies)
        return proxy

    def get_countries(self) -> list[dict[str, str]]:
        """Get a list of available Countries."""
        p = subprocess.check_output([
            self.binary,
            "-list-countries"
        ]).decode("utf8")

        return [
            {code: name}
            for country in p.splitlines()
            for (code, name) in [country.split(" - ", maxsplit=1)]
        ]
