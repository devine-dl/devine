from __future__ import annotations

import base64
import logging
from abc import ABCMeta, abstractmethod
from http.cookiejar import MozillaCookieJar, CookieJar
from typing import Optional, Union
from urllib.parse import urlparse

import click
import requests
from requests.adapters import Retry, HTTPAdapter

from devine.core.config import config
from devine.core.constants import AnyTrack
from devine.core.titles import Titles_T, Title_T
from devine.core.tracks import Chapter, Tracks
from devine.core.utilities import get_ip_info
from devine.core.cacher import Cacher
from devine.core.credential import Credential


class Service(metaclass=ABCMeta):
    """The Service Base Class."""

    # Abstract class variables
    ALIASES: tuple[str, ...] = ()  # list of aliases for the service; alternatives to the service tag.
    GEOFENCE: tuple[str, ...] = ()  # list of ip regions required to use the service. empty list == no specific region.

    def __init__(self, ctx: click.Context):
        self.config = ctx.obj.config

        assert ctx.parent is not None
        assert ctx.parent.parent is not None

        self.log = logging.getLogger(self.__class__.__name__)
        self.session = self.get_session()
        self.cache = Cacher(self.__class__.__name__)

        self.proxy = ctx.parent.params["proxy"]
        if not self.proxy and self.GEOFENCE:
            # no explicit proxy, let's get one to GEOFENCE if needed
            current_region = get_ip_info(self.session)["country"].lower()
            if not any([x.lower() == current_region for x in self.GEOFENCE]):
                requested_proxy = self.GEOFENCE[0]  # first is likely main region
                self.log.info(f"Current IP region is blocked by the service, getting Proxy to {requested_proxy}")
                # current region is not in any of the service's supported regions
                for proxy_provider in ctx.obj.proxy_providers:
                    self.proxy = proxy_provider.get_proxy(requested_proxy)
                    if self.proxy:
                        self.log.info(f" + {self.proxy} (from {proxy_provider.__class__.__name__})")
                        break
        if self.proxy:
            self.session.proxies.update({"all": self.proxy})
            proxy_parse = urlparse(self.proxy)
            if proxy_parse.username and proxy_parse.password:
                self.session.headers.update({
                    "Proxy-Authorization": base64.b64encode(
                        f"{proxy_parse.username}:{proxy_parse.password}".encode("utf8")
                    ).decode()
                })

    # Optional Abstract functions
    # The following functions may be implemented by the Service.
    # Otherwise, the base service code (if any) of the function will be executed on call.
    # The functions will be executed in shown order.

    def get_session(self) -> requests.Session:
        """
        Creates a Python-requests Session, adds common headers
        from config, cookies, retry handler, and a proxy if available.
        :returns: Prepared Python-requests Session
        """
        session = requests.Session()
        session.headers.update(config.headers)
        session.mount("https://", HTTPAdapter(
            max_retries=Retry(
                total=15,
                backoff_factor=0.2,
                status_forcelist=[429, 500, 502, 503, 504]
            )
        ))
        session.mount("http://", session.adapters["https://"])
        return session

    def authenticate(self, cookies: Optional[MozillaCookieJar] = None, credential: Optional[Credential] = None) -> None:
        """
        Authenticate the Service with Cookies and/or Credentials (Email/Username and Password).

        This is effectively a login() function. Any API calls or object initializations
        needing to be made, should be made here. This will be run before any of the
        following abstract functions.

        You should avoid storing or using the Credential outside this function.
        Make any calls you need for any Cookies, Tokens, or such, then use those.

        The Cookie jar should also not be stored outside this function. However, you may load
        the Cookie jar into the service session.
        """
        if cookies is not None:
            if not isinstance(cookies, CookieJar):
                raise TypeError(f"Expected cookies to be a {MozillaCookieJar}, not {cookies!r}.")
            self.session.cookies.update(cookies)

    def get_widevine_service_certificate(self, *, challenge: bytes, title: Title_T, track: AnyTrack) -> Union[bytes, str]:
        """
        Get the Widevine Service Certificate used for Privacy Mode.

        :param challenge: The service challenge, providing this to a License endpoint should return the
            privacy certificate that the service uses.
        :param title: The current `Title` from get_titles that is being executed. This is provided in
            case it has data needed to be used, e.g. for a HTTP request.
        :param track: The current `Track` needing decryption. Provided for same reason as `title`.
        :return: The Service Privacy Certificate as Bytes or a Base64 string. Don't Base64 Encode or
            Decode the data, return as is to reduce unnecessary computations.
        """

    def get_widevine_license(self, *, challenge: bytes, title: Title_T, track: AnyTrack) -> Optional[Union[bytes, str]]:
        """
        Get a Widevine License message by sending a License Request (challenge).

        This License message contains the encrypted Content Decryption Keys and will be
        read by the Cdm and decrypted.

        This is a very important request to get correct. A bad, unexpected, or missing
        value in the request can cause your key to be detected and promptly banned,
        revoked, disabled, or downgraded.

        :param challenge: The license challenge from the Widevine CDM.
        :param title: The current `Title` from get_titles that is being executed. This is provided in
            case it has data needed to be used, e.g. for a HTTP request.
        :param track: The current `Track` needing decryption. Provided for same reason as `title`.
        :return: The License response as Bytes or a Base64 string. Don't Base64 Encode or
            Decode the data, return as is to reduce unnecessary computations.
        """

    # Required Abstract functions
    # The following functions *must* be implemented by the Service.
    # The functions will be executed in shown order.

    @abstractmethod
    def get_titles(self) -> Titles_T:
        """
        Get Titles for the provided title ID.

        Return a Movies, Series, or Album objects containing Movie, Episode, or Song title objects respectively.
        The returned data must be for the given title ID, or a spawn of the title ID.

        At least one object is expected to be returned, or it will presume an invalid Title ID was
        provided.

        You can use the `data` dictionary class instance attribute of each Title to store data you may need later on.
        This can be useful to store information on each title that will be required like any sub-asset IDs, or such.
        """

    @abstractmethod
    def get_tracks(self, title: Title_T) -> Tracks:
        """
        Get Track objects of the Title.

        Return a Tracks object, which itself can contain Video, Audio, Subtitle or even Chapters.
        Tracks.videos, Tracks.audio, Tracks.subtitles, and Track.chapters should be a List of Track objects.

        Each Track in the Tracks should represent a Video/Audio Stream/Representation/Adaptation or
        a Subtitle file.

        While one Track should only hold information for one stream/downloadable, try to get as many
        unique Track objects per stream type so Stream selection by the root code can give you more
        options in terms of Resolution, Bitrate, Codecs, Language, e.t.c.

        No decision making or filtering of which Tracks get returned should happen here. It can be
        considered an error to filter for e.g. resolution, codec, and such. All filtering based on
        arguments will be done by the root code automatically when needed.

        Make sure you correctly mark which Tracks are encrypted or not, and by which DRM System
        via its `drm` property.

        If you are able to obtain the Track's KID (Key ID) as a 32 char (16 bit) HEX string, provide
        it to the Track's `kid` variable as it will speed up the decryption process later on. It may
        or may not be needed, that depends on the service. Generally if you can provide it, without
        downloading any of the Track's stream data, then do.

        :param title: The current `Title` from get_titles that is being executed.
        :return: Tracks object containing Video, Audio, Subtitles, and Chapters, if available.
        """

    @abstractmethod
    def get_chapters(self, title: Title_T) -> list[Chapter]:
        """
        Get Chapter objects of the Title.

        Return a list of Chapter objects. This will be run after get_tracks. If there's anything
        from the get_tracks that may be needed, e.g. "device_id" or a-like, store it in the class
        via `self` and re-use the value in get_chapters.

        How it's used is generally the same as get_titles. These are only separated as to reduce
        function complexity and keep them focused on simple tasks.

        You do not need to sort or order the chapters in any way. However, you do need to filter
        and alter them as needed by the service. No modification is made after get_chapters is
        ran. So that means ensure that the Chapter objects returned have consistent Chapter Titles
        and Chapter Numbers.

        :param title: The current `Title` from get_titles that is being executed.
        :return: List of Chapter objects, if available, empty list otherwise.
        """


__ALL__ = (Service,)
