from __future__ import annotations

import base64
from hashlib import md5

import math
import re
from copy import copy
from typing import Any, Optional, Union, Callable
from urllib.parse import urljoin, urlparse
from uuid import UUID

import requests
from langcodes import Language, tag_is_valid
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session

from devine.core.drm import Widevine
from devine.core.tracks import Tracks, Video, Audio, Subtitle
from devine.core.utilities import is_close_match, FPS
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

    def to_tracks(self, language: Union[str, Language], period_filter: Optional[Callable] = None) -> Tracks:
        """
        Convert an MPEG-DASH MPD (Media Presentation Description) document to Video, Audio and Subtitle Track objects.

        Parameters:
            language: Language you expect the Primary Track to be in.
            period_filter: Filter out period's within the manifest.

        All Track URLs will be a list of segment URLs.
        """
        tracks = Tracks()

        for period in self.manifest.findall("Period"):
            if callable(period_filter) and period_filter(period):
                continue

            period_base_url = period.findtext("BaseURL") or self.manifest.findtext("BaseURL")
            if not period_base_url or not re.match("^https?://", period_base_url, re.IGNORECASE):
                period_base_url = urljoin(self.url, period_base_url)

            for adaptation_set in period.findall("AdaptationSet"):
                # flags
                trick_mode = any(
                    x.get("schemeIdUri") == "http://dashif.org/guidelines/trickmode"
                    for x in (
                            adaptation_set.findall("EssentialProperty") +
                            adaptation_set.findall("SupplementalProperty")
                    )
                )
                descriptive = any(
                    (x.get("schemeIdUri"), x.get("value")) == ("urn:mpeg:dash:role:2011", "descriptive")
                    for x in adaptation_set.findall("Accessibility")
                ) or any(
                    (x.get("schemeIdUri"), x.get("value")) == ("urn:tva:metadata:cs:AudioPurposeCS:2007", "1")
                    for x in adaptation_set.findall("Accessibility")
                )
                forced = any(
                    (x.get("schemeIdUri"), x.get("value")) == ("urn:mpeg:dash:role:2011", "forced-subtitle")
                    for x in adaptation_set.findall("Role")
                )
                cc = any(
                    (x.get("schemeIdUri"), x.get("value")) == ("urn:mpeg:dash:role:2011", "caption")
                    for x in adaptation_set.findall("Role")
                )

                if trick_mode:
                    # we don't want trick mode streams (they are only used for fast-forward/rewind)
                    continue

                for rep in adaptation_set.findall("Representation"):
                    supplements = rep.findall("SupplementalProperty") + adaptation_set.findall("SupplementalProperty")

                    content_type = adaptation_set.get("contentType") or \
                        adaptation_set.get("mimeType") or \
                        rep.get("contentType") or \
                        rep.get("mimeType")
                    if not content_type:
                        raise ValueError("No content type value could be found")
                    content_type = content_type.split("/")[0]

                    codecs = rep.get("codecs") or adaptation_set.get("codecs")

                    if content_type.startswith("image"):
                        # we don't want what's likely thumbnails for the seekbar
                        continue
                    if content_type == "application":
                        # possibly application/mp4 which could be mp4-boxed subtitles
                        try:
                            Subtitle.Codec.from_mime(codecs)
                            content_type = "text"
                        except ValueError:
                            raise ValueError(f"Unsupported content type '{content_type}' with codecs of '{codecs}'")

                    if content_type == "text":
                        mime = adaptation_set.get("mimeType")
                        if mime and not mime.endswith("/mp4"):
                            codecs = mime.split("/")[1]

                    joc = next((
                        x.get("value")
                        for x in supplements
                        if x.get("schemeIdUri") == "tag:dolby.com,2018:dash:EC3_ExtensionComplexityIndex:2018"
                    ), None)

                    track_lang = DASH.get_language(rep.get("lang"), adaptation_set.get("lang"), language)
                    if not track_lang:
                        raise ValueError(
                            "One or more Tracks had no Language information. "
                            "The provided fallback language is not valid or is `None` or `und`."
                        )

                    drm = DASH.get_drm(rep.findall("ContentProtection") + adaptation_set.findall("ContentProtection"))

                    # from here we need to calculate the Segment Template and compute a final list of URLs

                    segment_urls = DASH.get_segment_urls(
                        representation=rep,
                        period_duration=period.get("duration") or self.manifest.get("mediaPresentationDuration"),
                        fallback_segment_template=adaptation_set.find("SegmentTemplate"),
                        fallback_base_url=period_base_url,
                        fallback_query=urlparse(self.url).query
                    )

                    # for some reason it's incredibly common for services to not provide
                    # a good and actually unique track ID, sometimes because of the lang
                    # dialect not being represented in the id, or the bitrate, or such.
                    # this combines all of them as one and hashes it to keep it small(ish).
                    track_id = md5("{codec}-{lang}-{bitrate}-{base_url}-{extra}".format(
                        codec=codecs,
                        lang=track_lang,
                        bitrate=rep.get("bandwidth") or 0,  # subs may not state bandwidth
                        base_url=(rep.findtext("BaseURL") or "").split("?")[0],
                        extra=(adaptation_set.get("audioTrackId") or "") + (rep.get("id") or "") +
                              (period.get("id") or "")
                    ).encode()).hexdigest()

                    if content_type == "video":
                        track_type = Video
                        track_codec = Video.Codec.from_codecs(codecs)
                    elif content_type == "audio":
                        track_type = Audio
                        track_codec = Audio.Codec.from_codecs(codecs)
                    elif content_type == "text":
                        track_type = Subtitle
                        track_codec = Subtitle.Codec.from_codecs(codecs or "vtt")
                    else:
                        raise ValueError(f"Unknown Track Type '{content_type}'")

                    tracks.add(track_type(
                        id_=track_id,
                        url=segment_urls,
                        codec=track_codec,
                        language=track_lang,
                        is_original_lang=not track_lang or not language or is_close_match(track_lang, [language]),
                        descriptor=Video.Descriptor.MPD,
                        extra=(rep, adaptation_set),
                        # video track args
                        **(dict(
                            range_=(
                                Video.Range.DV
                                if codecs.startswith(("dva1", "dvav", "dvhe", "dvh1")) else
                                Video.Range.from_cicp(
                                    primaries=next((
                                        int(x.get("value"))
                                        for x in (
                                            adaptation_set.findall("SupplementalProperty")
                                            + adaptation_set.findall("EssentialProperty")
                                        )
                                        if x.get("schemeIdUri") == "urn:mpeg:mpegB:cicp:ColourPrimaries"
                                    ), 0),
                                    transfer=next((
                                        int(x.get("value"))
                                        for x in (
                                            adaptation_set.findall("SupplementalProperty")
                                            + adaptation_set.findall("EssentialProperty")
                                        )
                                        if x.get("schemeIdUri") == "urn:mpeg:mpegB:cicp:TransferCharacteristics"
                                    ), 0),
                                    matrix=next((
                                        int(x.get("value"))
                                        for x in (
                                            adaptation_set.findall("SupplementalProperty")
                                            + adaptation_set.findall("EssentialProperty")
                                        )
                                        if x.get("schemeIdUri") == "urn:mpeg:mpegB:cicp:MatrixCoefficients"
                                    ), 0)
                                )
                            ),
                            bitrate=rep.get("bandwidth"),
                            width=int(rep.get("width") or 0) or adaptation_set.get("width"),
                            height=int(rep.get("height") or 0) or adaptation_set.get("height"),
                            fps=(
                                rep.get("frameRate") or
                                adaptation_set.get("frameRate") or
                                FPS.parse(rep.find("SegmentBase").get("timescale"))
                            ),
                            drm=drm
                        ) if track_type is Video else dict(
                            bitrate=rep.get("bandwidth"),
                            channels=next(iter(
                                rep.xpath("AudioChannelConfiguration/@value")
                                or adaptation_set.xpath("AudioChannelConfiguration/@value")
                            ), None),
                            joc=joc,
                            descriptive=descriptive,
                            drm=drm
                        ) if track_type is Audio else dict(
                            forced=forced,
                            cc=cc
                        ) if track_type is Subtitle else {})
                    ))

            # only get tracks from the first main-content period
            break

        return tracks

    @staticmethod
    def get_language(*options: Any) -> Optional[Language]:
        for option in options:
            option = (str(option) or "").strip()
            if not tag_is_valid(option) or option.startswith("und"):
                continue
            return Language.get(option)

    @staticmethod
    def get_drm(protections) -> Optional[list[Widevine]]:
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

        if not drm:
            drm = None

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

    @staticmethod
    def get_segment_urls(
        representation,
        period_duration: str,
        fallback_segment_template,
        fallback_base_url: Optional[str] = None,
        fallback_query: Optional[str] = None
    ) -> list[str]:
        segment_urls: list[str] = []
        segment_template = representation.find("SegmentTemplate") or fallback_segment_template
        base_url = representation.findtext("BaseURL") or fallback_base_url

        if segment_template is None:
            # We could implement SegmentBase, but it's basically a list of Byte Range's to download
            # So just return the Base URL as a segment, why give the downloader extra effort
            return [urljoin(fallback_base_url, base_url)]

        segment_template = copy(segment_template)
        start_number = int(segment_template.get("startNumber") or 1)
        segment_timeline = segment_template.find("SegmentTimeline")

        for item in ("initialization", "media"):
            value = segment_template.get(item)
            if not value:
                continue
            if not re.match("^https?://", value, re.IGNORECASE):
                if not base_url:
                    raise ValueError("Resolved Segment URL is not absolute, and no Base URL is available.")
                value = urljoin(base_url, value)
            if not urlparse(value).query and fallback_query:
                value += f"?{fallback_query}"
            segment_template.set(item, value)

        initialization = segment_template.get("initialization")
        if initialization:
            segment_urls.append(DASH.replace_fields(
                initialization,
                Bandwidth=representation.get("bandwidth"),
                RepresentationID=representation.get("id")
            ))

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
            segment_urls += [
                DASH.replace_fields(
                    segment_template.get("media"),
                    Bandwidth=representation.get("bandwidth"),
                    Number=n,
                    RepresentationID=representation.get("id"),
                    Time=t
                )
                for t, n in zip(seg_time_list, seg_num_list)
            ]
        else:
            if not period_duration:
                raise ValueError("Duration of the Period was unable to be determined.")
            period_duration = DASH.pt_to_sec(period_duration)

            segment_duration = (
                float(segment_template.get("duration")) / float(segment_template.get("timescale") or 1)
            )
            total_segments = math.ceil(period_duration / segment_duration)
            segment_urls += [
                DASH.replace_fields(
                    segment_template.get("media"),
                    Bandwidth=representation.get("bandwidth"),
                    Number=s,
                    RepresentationID=representation.get("id"),
                    Time=s
                )
                for s in range(start_number, start_number + total_segments)
            ]

        return segment_urls


__ALL__ = (DASH,)
