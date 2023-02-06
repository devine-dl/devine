from abc import abstractmethod
from typing import Optional


class Proxy:
    @abstractmethod
    def __init__(self, **kwargs):
        """
        The constructor initializes the Service using passed configuration data.

        Any authorization or pre-fetching of data should be done here.
        """

    @abstractmethod
    def __repr__(self) -> str:
        """Return a string denoting a list of Countries and Servers (if possible)."""
        countries = ...
        servers = ...
        return f"{countries} Countr{['ies', 'y'][countries == 1]} ({servers} Server{['s', ''][servers == 1]})"

    @abstractmethod
    def get_proxy(self, query: str) -> Optional[str]:
        """
        Get a Proxy URI from the Proxy Service.

        Only return None if the query was accepted, but no proxy could be returned.
        Otherwise, please use exceptions to denote any errors with the call or query.

        The returned Proxy URI must be a string supported by Python-Requests:
        '{scheme}://[{user}:{pass}@]{host}:{port}'
        """
