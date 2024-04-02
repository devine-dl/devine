import base64
import logging
from abc import ABCMeta, abstractmethod
from collections.abc import Generator
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

import click
import m3u8
import requests
from requests.adapters import HTTPAdapter, Retry
from rich.padding import Padding
from rich.rule import Rule

from devine.core.cacher import Cacher
from devine.core.config import config
from devine.core.console import console
from devine.core.constants import AnyTrack
from devine.core.credential import Credential
from devine.core.drm import DRM_T
from devine.core.search_result import SearchResult
from devine.core.titles import Title_T, Titles_T
from devine.core.tracks import Chapters, Tracks
from devine.core.utilities import get_ip_info


class Service(metaclass=ABCMeta):
    """The Service Base Class."""

    # Abstract class variables
    ALIASES: tuple[str, ...] = ()  # list of aliases for the service; alternatives to the service tag.
    GEOFENCE: tuple[str, ...] = ()  # list of ip regions required to use the service. empty list == no specific region.

    def __init__(self, ctx: click.Context):
        console.print(Padding(
            Rule(f"[rule.text]Service: {self.__class__.__name__}"),
            (1, 2)
        ))

        self.config = ctx.obj.config

        self.log = logging.getLogger(self.__class__.__name__)

        self.session = self.get_session()
        self.cache = Cacher(self.__class__.__name__)

        if not ctx.parent or not ctx.parent.params.get("no_proxy"):
            if ctx.parent:
                proxy = ctx.parent.params["proxy"]
            else:
                proxy = None

            if not proxy:
                # don't override the explicit proxy set by the user, even if they may be geoblocked
                with console.status("Checking if current region is Geoblocked...", spinner="dots"):
                    if self.GEOFENCE:
                        # no explicit proxy, let's get one to GEOFENCE if needed
                        current_region = get_ip_info(self.session)["country"].lower()
                        if any(x.lower() == current_region for x in self.GEOFENCE):
                            self.log.info("Service is not Geoblocked in your region")
                        else:
                            requested_proxy = self.GEOFENCE[0]  # first is likely main region
                            self.log.info(f"Service is Geoblocked in your region, getting a Proxy to {requested_proxy}")
                            for proxy_provider in ctx.obj.proxy_providers:
                                proxy = proxy_provider.get_proxy(requested_proxy)
                                if proxy:
                                    self.log.info(f"Got Proxy from {proxy_provider.__class__.__name__}")
                                    break
                    else:
                        self.log.info("Service has no Geofence")

            if proxy:
                self.session.proxies.update({"all": proxy})
                proxy_parse = urlparse(proxy)
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

    @staticmethod
    def get_session() -> requests.Session:
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
            ),
            pool_block=True
        ))
        session.mount("http://", session.adapters["https://"])
        return session

    def authenticate(self, cookies: Optional[CookieJar] = None, credential: Optional[Credential] = None) -> None:
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
                raise TypeError(f"Expected cookies to be a {CookieJar}, not {cookies!r}.")
            self.session.cookies.update(cookies)

    def search(self) -> Generator[SearchResult, None, None]:
        """
        Search by query for titles from the Service.

        The query must be taken as a CLI argument by the Service class.
        Ideally just re-use the title ID argument (i.e. self.title).

        Search results will be displayed in the order yielded.
        """
        raise NotImplementedError(f"Search functionality has not been implemented by {self.__class__.__name__}")

    def get_widevine_service_certificate(self, *, challenge: bytes, title: Title_T, track: AnyTrack) \
            -> Union[bytes, str]:
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
    def get_chapters(self, title: Title_T) -> Chapters:
        """
        Get Chapters for the Title.

        Parameters:
            title: The current Title from `get_titles` that is being processed.

        You must return a Chapters object containing 0 or more Chapter objects.

        You do not need to set a Chapter number or sort/order the chapters in any way as
        the Chapters class automatically handles all of that for you. If there's no
        descriptive name for a Chapter then do not set a name at all.

        You must not set Chapter names to "Chapter {n}" or such. If you (or the user)
        wants "Chapter {n}" style Chapter names (or similar) then they can use the config
        option `chapter_fallback_name`. For example, `"Chapter {i:02}"` for "Chapter 01".
        """

    # Optional Event methods

    def on_segment_downloaded(self, track: AnyTrack, segment: Path) -> None:
        """
        Called when one of a Track's Segments has finished downloading.

        Parameters:
            track: The Track object that had a Segment downloaded.
            segment: The Path to the Segment that was downloaded.
        """

    def on_track_downloaded(self, track: AnyTrack) -> None:
        """
        Called when a Track has finished downloading.

        Parameters:
            track: The Track object that was downloaded.
        """

    def on_track_decrypted(self, track: AnyTrack, drm: DRM_T, segment: Optional[m3u8.Segment] = None) -> None:
        """
        Called when a Track has finished decrypting.

        Parameters:
            track: The Track object that was decrypted.
            drm: The DRM object it decrypted with.
            segment: The HLS segment information that was decrypted.
        """

    def on_track_repacked(self, track: AnyTrack) -> None:
        """
        Called when a Track has finished repacking.

        Parameters:
            track: The Track object that was repacked.
        """

    def on_track_multiplex(self, track: AnyTrack) -> None:
        """
        Called when a Track is about to be Multiplexed into a Container.

        Note: Right now only MKV containers are multiplexed but in the future
        this may also be called when multiplexing to other containers like
        MP4 via ffmpeg/mp4box.

        Parameters:
            track: The Track object that was repacked.
        """

__all__ = ("Service",)
