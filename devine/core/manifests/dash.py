from __future__ import annotations

import base64
import html
import logging
import math
import re
import sys
import time
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from functools import partial
from hashlib import md5
from pathlib import Path
from typing import Any, Callable, MutableMapping, Optional, Union
from urllib.parse import urljoin, urlparse
from uuid import UUID

import requests
from langcodes import Language, tag_is_valid
from lxml.etree import Element
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session
from requests.cookies import RequestsCookieJar
from rich import filesize

from devine.core.constants import DOWNLOAD_CANCELLED, DOWNLOAD_LICENCE_ONLY, AnyTrack
from devine.core.downloaders import downloader
from devine.core.downloaders import requests as requests_downloader
from devine.core.drm import Widevine
from devine.core.tracks import Audio, Subtitle, Tracks, Video
from devine.core.utilities import is_close_match, try_ensure_utf8
from devine.core.utils.xml import load_xml


class DASH:
    def __init__(self, manifest, url: str):
        if manifest is None:
            raise ValueError("DASH manifest must be provided.")
        if manifest.tag != "MPD":
            raise TypeError(f"Expected 'MPD' document, but received a '{manifest.tag}' document instead.")

        if not url:
            raise requests.URLRequired("DASH manifest URL must be provided for relative path computations.")
        if not isinstance(url, str):
            raise TypeError(f"Expected url to be a {str}, not {url!r}")

        self.manifest = manifest
        self.url = url

    @classmethod
    def from_url(cls, url: str, session: Optional[Session] = None, **args: Any) -> DASH:
        if not url:
            raise requests.URLRequired("DASH manifest URL must be provided for relative path computations.")
        if not isinstance(url, str):
            raise TypeError(f"Expected url to be a {str}, not {url!r}")

        if not session:
            session = Session()
        elif not isinstance(session, Session):
            raise TypeError(f"Expected session to be a {Session}, not {session!r}")

        res = session.get(url, **args)
        if res.url != url:
            url = res.url

        if not res.ok:
            raise requests.ConnectionError(
                "Failed to request the MPD document.",
                response=res
            )

        return DASH.from_text(res.text, url)

    @classmethod
    def from_text(cls, text: str, url: str) -> DASH:
        if not text:
            raise ValueError("DASH manifest Text must be provided.")
        if not isinstance(text, str):
            raise TypeError(f"Expected text to be a {str}, not {text!r}")

        if not url:
            raise requests.URLRequired("DASH manifest URL must be provided for relative path computations.")
        if not isinstance(url, str):
            raise TypeError(f"Expected url to be a {str}, not {url!r}")

        manifest = load_xml(text)

        return cls(manifest, url)

    def to_tracks(
        self,
        language: Optional[Union[str, Language]] = None,
        period_filter: Optional[Callable] = None
    ) -> Tracks:
        """
        Convert an MPEG-DASH document to Video, Audio and Subtitle Track objects.

        Parameters:
            language: The Title's Original Recorded Language. It will also be used as a fallback
                track language value if the manifest does not list language information.
            period_filter: Filter out period's within the manifest.

        All Track URLs will be a list of segment URLs.
        """
        tracks = Tracks()

        for period in self.manifest.findall("Period"):
            if callable(period_filter) and period_filter(period):
                continue

            for adaptation_set in period.findall("AdaptationSet"):
                if self.is_trick_mode(adaptation_set):
                    # we don't want trick mode streams (they are only used for fast-forward/rewind)
                    continue

                for rep in adaptation_set.findall("Representation"):
                    get = partial(self._get, adaptation_set=adaptation_set, representation=rep)
                    findall = partial(self._findall, adaptation_set=adaptation_set, representation=rep, both=True)

                    codecs = get("codecs")
                    content_type = get("contentType")
                    mime_type = get("mimeType")

                    if not content_type and mime_type:
                        content_type = mime_type.split("/")[0]
                    if not content_type and not mime_type:
                        raise ValueError("Unable to determine the format of a Representation, cannot continue...")

                    if mime_type == "application/mp4" or content_type == "application":
                        # likely mp4-boxed subtitles
                        # TODO: It may not actually be subtitles
                        try:
                            real_codec = Subtitle.Codec.from_mime(codecs)
                            content_type = "text"
                            mime_type = f"application/mp4; codecs='{real_codec.value.lower()}'"
                        except ValueError:
                            raise ValueError(f"Unsupported content type '{content_type}' with codecs of '{codecs}'")

                    if content_type == "text" and mime_type and "/mp4" not in mime_type:
                        # mimeType likely specifies the subtitle codec better than `codecs`
                        codecs = mime_type.split("/")[1]

                    if content_type == "video":
                        track_type = Video
                        track_codec = Video.Codec.from_codecs(codecs)
                        track_args = dict(
                            range_=self.get_video_range(
                                codecs,
                                findall("SupplementalProperty"),
                                findall("EssentialProperty")
                            ),
                            bitrate=get("bandwidth") or None,
                            width=get("width") or 0,
                            height=get("height") or 0,
                            fps=get("frameRate") or (rep.find("SegmentBase") or {}).get("timescale") or None
                        )
                    elif content_type == "audio":
                        track_type = Audio
                        track_codec = Audio.Codec.from_codecs(codecs)
                        track_args = dict(
                            bitrate=get("bandwidth") or None,
                            channels=next(iter(
                                rep.xpath("AudioChannelConfiguration/@value")
                                or adaptation_set.xpath("AudioChannelConfiguration/@value")
                            ), None),
                            joc=self.get_ddp_complexity_index(adaptation_set, rep),
                            descriptive=self.is_descriptive(adaptation_set)
                        )
                    elif content_type == "text":
                        track_type = Subtitle
                        track_codec = Subtitle.Codec.from_codecs(codecs or "vtt")
                        track_args = dict(
                            forced=self.is_forced(adaptation_set),
                            cc=self.is_closed_caption(adaptation_set)
                        )
                    elif content_type == "image":
                        # we don't want what's likely thumbnails for the seekbar
                        continue
                    else:
                        raise ValueError(f"Unknown Track Type '{content_type}'")

                    track_lang = self.get_language(adaptation_set, rep, fallback=language)
                    if not track_lang:
                        msg = "Language information could not be derived from a Representation."
                        if language is None:
                            msg += " No fallback language was provided when calling DASH.to_tracks()."
                        elif not tag_is_valid((str(language) or "").strip()) or str(language).startswith("und"):
                            msg += f" The fallback language provided is also invalid: {language}"
                        raise ValueError(msg)

                    # for some reason it's incredibly common for services to not provide
                    # a good and actually unique track ID, sometimes because of the lang
                    # dialect not being represented in the id, or the bitrate, or such.
                    # this combines all of them as one and hashes it to keep it small(ish).
                    track_id = md5("{codec}-{lang}-{bitrate}-{base_url}-{ids}-{track_args}".format(
                        codec=codecs,
                        lang=track_lang,
                        bitrate=get("bitrate"),
                        base_url=(rep.findtext("BaseURL") or "").split("?")[0],
                        ids=[get("audioTrackId"), get("id"), period.get("id")],
                        track_args=track_args
                    ).encode()).hexdigest()

                    tracks.add(track_type(
                        id_=track_id,
                        url=(self.url, self.manifest, rep, adaptation_set, period),
                        codec=track_codec,
                        language=track_lang,
                        is_original_lang=language and is_close_match(track_lang, [language]),
                        descriptor=Video.Descriptor.MPD,
                        extra=(rep, adaptation_set),
                        **track_args
                    ))

            # only get tracks from the first main-content period
            break

        return tracks

    @staticmethod
    def download_track(
        track: AnyTrack,
        save_path: Path,
        save_dir: Path,
        progress: partial,
        session: Optional[Session] = None,
        proxy: Optional[str] = None,
        license_widevine: Optional[Callable] = None
    ):
        if not session:
            session = Session()
        elif not isinstance(session, Session):
            raise TypeError(f"Expected session to be a {Session}, not {session!r}")

        if proxy:
            session.proxies.update({
                "all": proxy
            })

        log = logging.getLogger("DASH")

        manifest_url, manifest, representation, adaptation_set, period = track.url

        track.drm = DASH.get_drm(
            representation.findall("ContentProtection") +
            adaptation_set.findall("ContentProtection")
        )

        manifest_url_query = urlparse(manifest_url).query

        manifest_base_url = manifest.findtext("BaseURL")
        if not manifest_base_url or not re.match("^https?://", manifest_base_url, re.IGNORECASE):
            manifest_base_url = urljoin(manifest_url, "./", manifest_base_url)
        period_base_url = urljoin(manifest_base_url, period.findtext("BaseURL"))
        rep_base_url = urljoin(period_base_url, representation.findtext("BaseURL"))

        period_duration = period.get("duration") or manifest.get("mediaPresentationDuration")
        init_data: Optional[bytes] = None

        segment_template = representation.find("SegmentTemplate")
        if segment_template is None:
            segment_template = adaptation_set.find("SegmentTemplate")

        segment_list = representation.find("SegmentList")
        if segment_list is None:
            segment_list = adaptation_set.find("SegmentList")

        if segment_template is None and segment_list is None and rep_base_url:
            # If there's no SegmentTemplate and no SegmentList, then SegmentBase is used or just BaseURL
            # Regardless which of the two is used, we can just directly grab the BaseURL
            # Players would normally calculate segments via Byte-Ranges, but we don't care
            track.url = rep_base_url
            track.descriptor = track.Descriptor.URL
        else:
            segments: list[tuple[str, Optional[str]]] = []
            track_kid: Optional[UUID] = None

            if segment_template is not None:
                segment_template = copy(segment_template)
                start_number = int(segment_template.get("startNumber") or 1)
                segment_timeline = segment_template.find("SegmentTimeline")

                for item in ("initialization", "media"):
                    value = segment_template.get(item)
                    if not value:
                        continue
                    if not re.match("^https?://", value, re.IGNORECASE):
                        if not rep_base_url:
                            raise ValueError("Resolved Segment URL is not absolute, and no Base URL is available.")
                        value = urljoin(rep_base_url, value)
                    if not urlparse(value).query and manifest_url_query:
                        value += f"?{manifest_url_query}"
                    segment_template.set(item, value)

                init_url = segment_template.get("initialization")
                if init_url:
                    res = session.get(DASH.replace_fields(
                        init_url,
                        Bandwidth=representation.get("bandwidth"),
                        RepresentationID=representation.get("id")
                    ))
                    res.raise_for_status()
                    init_data = res.content
                    track_kid = track.get_key_id(init_data)

                if segment_timeline is not None:
                    seg_time_list = []
                    current_time = 0
                    for s in segment_timeline.findall("S"):
                        if s.get("t"):
                            current_time = int(s.get("t"))
                        for _ in range(1 + (int(s.get("r") or 0))):
                            seg_time_list.append(current_time)
                            current_time += int(s.get("d"))
                    seg_num_list = list(range(start_number, len(seg_time_list) + start_number))

                    for t, n in zip(seg_time_list, seg_num_list):
                        segments.append((
                            DASH.replace_fields(
                                segment_template.get("media"),
                                Bandwidth=representation.get("bandwidth"),
                                Number=n,
                                RepresentationID=representation.get("id"),
                                Time=t
                            ), None
                        ))
                else:
                    if not period_duration:
                        raise ValueError("Duration of the Period was unable to be determined.")
                    period_duration = DASH.pt_to_sec(period_duration)
                    segment_duration = float(segment_template.get("duration"))
                    segment_timescale = float(segment_template.get("timescale") or 1)
                    total_segments = math.ceil(period_duration / (segment_duration / segment_timescale))

                    for s in range(start_number, start_number + total_segments):
                        segments.append((
                            DASH.replace_fields(
                                segment_template.get("media"),
                                Bandwidth=representation.get("bandwidth"),
                                Number=s,
                                RepresentationID=representation.get("id"),
                                Time=s
                            ), None
                        ))
            elif segment_list is not None:
                init_data = None
                initialization = segment_list.find("Initialization")
                if initialization is not None:
                    source_url = initialization.get("sourceURL")
                    if source_url is None:
                        source_url = rep_base_url

                    if initialization.get("range"):
                        init_range_header = {"Range": f"bytes={initialization.get('range')}"}
                    else:
                        init_range_header = None

                    res = session.get(url=source_url, headers=init_range_header)
                    res.raise_for_status()
                    init_data = res.content
                    track_kid = track.get_key_id(init_data)

                segment_urls = segment_list.findall("SegmentURL")
                for segment_url in segment_urls:
                    media_url = segment_url.get("media")
                    if media_url is None:
                        media_url = rep_base_url

                    segments.append((
                        media_url,
                        segment_url.get("mediaRange")
                    ))
            else:
                log.error("Could not find a way to get segments from this MPD manifest.")
                log.debug(manifest_url)
                sys.exit(1)

            if not track.drm and isinstance(track, (Video, Audio)):
                try:
                    track.drm = [Widevine.from_init_data(init_data)]
                except Widevine.Exceptions.PSSHNotFound:
                    # it might not have Widevine DRM, or might not have found the PSSH
                    log.warning("No Widevine PSSH was found for this track, is it DRM free?")

            if track.drm:
                # last chance to find the KID, assumes first segment will hold the init data
                track_kid = track_kid or track.get_key_id(url=segments[0][0], session=session)
                # TODO: What if we don't want to use the first DRM system?
                drm = track.drm[0]
                if isinstance(drm, Widevine):
                    # license and grab content keys
                    try:
                        if not license_widevine:
                            raise ValueError("license_widevine func must be supplied to use Widevine DRM")
                        progress(downloaded="LICENSING")
                        license_widevine(drm, track_kid=track_kid)
                        progress(downloaded="[yellow]LICENSED")
                    except Exception:  # noqa
                        DOWNLOAD_CANCELLED.set()  # skip pending track downloads
                        progress(downloaded="[red]FAILED")
                        raise
            else:
                drm = None

            if DOWNLOAD_LICENCE_ONLY.is_set():
                progress(downloaded="[yellow]SKIPPED")
                return

            progress(total=len(segments))

            download_sizes = []
            download_speed_window = 5
            last_speed_refresh = time.time()

            with ThreadPoolExecutor(max_workers=16) as pool:
                for i, download in enumerate(futures.as_completed((
                    pool.submit(
                        DASH.download_segment,
                        url=url,
                        out_path=(save_dir / str(n).zfill(len(str(len(segments))))).with_suffix(".mp4"),
                        track=track,
                        proxy=proxy,
                        headers=session.headers,
                        cookies=session.cookies,
                        bytes_range=bytes_range
                    )
                    for n, (url, bytes_range) in enumerate(segments)
                ))):
                    try:
                        download_size = download.result()
                    except KeyboardInterrupt:
                        DOWNLOAD_CANCELLED.set()  # skip pending track downloads
                        progress(downloaded="[yellow]CANCELLING")
                        pool.shutdown(wait=True, cancel_futures=True)
                        progress(downloaded="[yellow]CANCELLED")
                        # tell dl that it was cancelled
                        # the pool is already shut down, so exiting loop is fine
                        raise
                    except Exception:
                        DOWNLOAD_CANCELLED.set()  # skip pending track downloads
                        progress(downloaded="[red]FAILING")
                        pool.shutdown(wait=True, cancel_futures=True)
                        progress(downloaded="[red]FAILED")
                        # tell dl that it failed
                        # the pool is already shut down, so exiting loop is fine
                        raise
                    else:
                        progress(advance=1)

                        now = time.time()
                        time_since = now - last_speed_refresh

                        if download_size:  # no size == skipped dl
                            download_sizes.append(download_size)

                        if download_sizes and (time_since > download_speed_window or i == len(segments)):
                            data_size = sum(download_sizes)
                            download_speed = data_size / (time_since or 1)
                            progress(downloaded=f"DASH {filesize.decimal(download_speed)}/s")
                            last_speed_refresh = now
                            download_sizes.clear()

            with open(save_path, "wb") as f:
                if init_data:
                    f.write(init_data)
                for segment_file in sorted(save_dir.iterdir()):
                    segment_data = segment_file.read_bytes()
                    # TODO: fix encoding after decryption?
                    if (
                        not drm and isinstance(track, Subtitle) and
                        track.codec not in (Subtitle.Codec.fVTT, Subtitle.Codec.fTTML)
                    ):
                        segment_data = try_ensure_utf8(segment_data)
                        segment_data = html.unescape(segment_data.decode("utf8")).encode("utf8")
                    f.write(segment_data)
                    segment_file.unlink()

            if drm:
                progress(downloaded="Decrypting", completed=0, total=100)
                drm.decrypt(save_path)
                track.drm = None
                if callable(track.OnDecrypted):
                    track.OnDecrypted(track)
                progress(downloaded="Decrypted", completed=100)

            track.path = save_path
            save_dir.rmdir()

            progress(downloaded="Downloaded")

    @staticmethod
    def download_segment(
        url: str,
        out_path: Path,
        track: AnyTrack,
        proxy: Optional[str] = None,
        headers: Optional[MutableMapping[str, str | bytes]] = None,
        cookies: Optional[Union[MutableMapping[str, str], RequestsCookieJar]] = None,
        bytes_range: Optional[str] = None
    ) -> int:
        """
        Download a DASH Media Segment.

        Parameters:
            url: Full HTTP(S) URL to the Segment you want to download.
            out_path: Path to save the downloaded Segment file to.
            track: The Track object of which this Segment is for. Currently only used to
                fix an invalid value in the TFHD box of Audio Tracks.
            proxy: Proxy URI to use when downloading the Segment file.
            headers: HTTP Headers to send when requesting the Segment file.
            cookies: Cookies to send when requesting the Segment file. The actual cookies sent
                will be resolved based on the URI among other parameters. Multiple cookies with
                the same name but a different domain/path are resolved.
            bytes_range: Download only specific bytes of the Segment file using the Range header.

        Returns the file size of the downloaded Segment in bytes.
        """
        if DOWNLOAD_CANCELLED.is_set():
            raise KeyboardInterrupt()

        if bytes_range:
            # aria2(c) doesn't support byte ranges, use python-requests
            downloader_ = requests_downloader
            headers_ = dict(**headers, Range=f"bytes={bytes_range}")
        else:
            downloader_ = downloader
            headers_ = headers

        downloader_(
            uri=url,
            out=out_path,
            headers=headers_,
            cookies=cookies,
            proxy=proxy,
            segmented=True
        )

        # fix audio decryption on ATVP by fixing the sample description index
        # TODO: Should this be done in the video data or the init data?
        if isinstance(track, Audio):
            with open(out_path, "rb+") as f:
                segment_data = f.read()
                fixed_segment_data = re.sub(
                    b"(tfhd\x00\x02\x00\x1a\x00\x00\x00\x01\x00\x00\x00)\x02",
                    b"\\g<1>\x01",
                    segment_data
                )
                if fixed_segment_data != segment_data:
                    f.seek(0)
                    f.write(fixed_segment_data)

        return out_path.stat().st_size

    @staticmethod
    def _get(
        item: str,
        adaptation_set: Element,
        representation: Optional[Element] = None
    ) -> Optional[Any]:
        """Helper to get a requested item from the Representation, otherwise from the AdaptationSet."""
        adaptation_set_item = adaptation_set.get(item)
        if representation is None:
            return adaptation_set_item

        representation_item = representation.get(item)
        if representation_item is not None:
            return representation_item

        return adaptation_set_item

    @staticmethod
    def _findall(
        item: str,
        adaptation_set: Element,
        representation: Optional[Element] = None,
        both: bool = False
    ) -> list[Any]:
        """
        Helper to get all requested items from the Representation, otherwise from the AdaptationSet.
        Optionally, you may pass both=True to keep both values (where available).
        """
        adaptation_set_items = adaptation_set.findall(item)
        if representation is None:
            return adaptation_set_items

        representation_items = representation.findall(item)

        if both:
            return representation_items + adaptation_set_items

        if representation_items:
            return representation_items

        return adaptation_set_items

    @staticmethod
    def get_language(
        adaptation_set: Element,
        representation: Optional[Element] = None,
        fallback: Optional[Union[str, Language]] = None
    ) -> Optional[Language]:
        """
        Get Language (if any) from the AdaptationSet or Representation.

        A fallback language may be provided if no language information could be
        retrieved.
        """
        options = []

        if representation is not None:
            options.append(representation.get("lang"))
            # derive language from somewhat common id string format
            # the format is typically "{rep_id}_{lang}={bitrate}" or similar
            rep_id = representation.get("id")
            if rep_id:
                m = re.match(r"\w+_(\w+)=\d+", rep_id)
                if m:
                    options.append(m.group(1))

        options.append(adaptation_set.get("lang"))

        if fallback:
            options.append(fallback)

        for option in options:
            option = (str(option) or "").strip()
            if not tag_is_valid(option) or option.startswith("und"):
                continue
            return Language.get(option)

    @staticmethod
    def get_video_range(
        codecs: str,
        all_supplemental_props: list[Element],
        all_essential_props: list[Element]
    ) -> Video.Range:
        if codecs.startswith(("dva1", "dvav", "dvhe", "dvh1")):
            return Video.Range.DV

        return Video.Range.from_cicp(
            primaries=next((
                int(x.get("value"))
                for x in all_supplemental_props + all_essential_props
                if x.get("schemeIdUri") == "urn:mpeg:mpegB:cicp:ColourPrimaries"
            ), 0),
            transfer=next((
                int(x.get("value"))
                for x in all_supplemental_props + all_essential_props
                if x.get("schemeIdUri") == "urn:mpeg:mpegB:cicp:TransferCharacteristics"
            ), 0),
            matrix=next((
                int(x.get("value"))
                for x in all_supplemental_props + all_essential_props
                if x.get("schemeIdUri") == "urn:mpeg:mpegB:cicp:MatrixCoefficients"
            ), 0)
        )

    @staticmethod
    def is_trick_mode(adaptation_set: Element) -> bool:
        """Check if contents of Adaptation Set is a Trick-Mode stream."""
        essential_props = adaptation_set.findall("EssentialProperty")
        supplemental_props = adaptation_set.findall("SupplementalProperty")

        return any(
            prop.get("schemeIdUri") == "http://dashif.org/guidelines/trickmode"
            for prop in essential_props + supplemental_props
        )

    @staticmethod
    def is_descriptive(adaptation_set: Element) -> bool:
        """Check if contents of Adaptation Set is Descriptive."""
        return any(
            (x.get("schemeIdUri"), x.get("value")) in (
                ("urn:mpeg:dash:role:2011", "descriptive"),
                ("urn:tva:metadata:cs:AudioPurposeCS:2007", "1")
            )
            for x in adaptation_set.findall("Accessibility")
        )

    @staticmethod
    def is_forced(adaptation_set: Element) -> bool:
        """Check if contents of Adaptation Set is a Forced Subtitle."""
        return any(
            x.get("schemeIdUri") == "urn:mpeg:dash:role:2011"
            and x.get("value") in ("forced-subtitle", "forced_subtitle")
            for x in adaptation_set.findall("Role")
        )

    @staticmethod
    def is_closed_caption(adaptation_set: Element) -> bool:
        """Check if contents of Adaptation Set is a Closed Caption Subtitle."""
        return any(
            (x.get("schemeIdUri"), x.get("value")) == ("urn:mpeg:dash:role:2011", "caption")
            for x in adaptation_set.findall("Role")
        )

    @staticmethod
    def get_ddp_complexity_index(adaptation_set: Element, representation: Optional[Element]) -> Optional[int]:
        """Get the DD+ Complexity Index (if any) from the AdaptationSet or Representation."""
        return next((
            int(x.get("value"))
            for x in DASH._findall("SupplementalProperty", adaptation_set, representation, both=True)
            if x.get("schemeIdUri") == "tag:dolby.com,2018:dash:EC3_ExtensionComplexityIndex:2018"
        ), None)

    @staticmethod
    def get_drm(protections: list[Element]) -> list[Widevine]:
        drm = []

        for protection in protections:
            # TODO: Add checks for PlayReady, FairPlay, maybe more
            urn = (protection.get("schemeIdUri") or "").lower()
            if urn != WidevineCdm.urn:
                continue

            pssh = protection.findtext("pssh")
            if not pssh:
                continue
            pssh = PSSH(pssh)

            kid = protection.get("kid")
            if kid:
                kid = UUID(bytes=base64.b64decode(kid))

            default_kid = protection.get("default_KID")
            if default_kid:
                kid = UUID(default_kid)

            if not pssh.key_ids and not kid:
                # weird manifest, look across all protections for a default_KID
                kid = next((
                    UUID(protection.get("default_KID"))
                    for protection in protections
                    if protection.get("default_KID")
                ), None)

            drm.append(Widevine(
                pssh=pssh,
                kid=kid
            ))

        return drm

    @staticmethod
    def pt_to_sec(d: Union[str, float]) -> float:
        if isinstance(d, float):
            return d
        has_ymd = d[0:8] == "P0Y0M0DT"
        if d[0:2] != "PT" and not has_ymd:
            raise ValueError("Input data is not a valid time string.")
        if has_ymd:
            d = d[6:].upper()  # skip `P0Y0M0DT`
        else:
            d = d[2:].upper()  # skip `PT`
        m = re.findall(r"([\d.]+.)", d)
        return sum(
            float(x[0:-1]) * {"H": 60 * 60, "M": 60, "S": 1}[x[-1].upper()]
            for x in m
        )

    @staticmethod
    def replace_fields(url: str, **kwargs: Any) -> str:
        for field, value in kwargs.items():
            url = url.replace(f"${field}$", str(value))
            m = re.search(fr"\${re.escape(field)}%([a-z0-9]+)\$", url, flags=re.I)
            if m:
                url = url.replace(m.group(), f"{value:{m.group(1)}}")
        return url


__all__ = ("DASH",)
