from __future__ import annotations

import base64
import html
import logging
import math
import re
import sys
from copy import copy
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional, Union
from urllib.parse import urljoin, urlparse
from uuid import UUID
from zlib import crc32

import requests
from langcodes import Language, tag_is_valid
from lxml.etree import Element, ElementTree
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session

from devine.core.constants import DOWNLOAD_CANCELLED, DOWNLOAD_LICENCE_ONLY, AnyTrack
from devine.core.downloaders import requests as requests_downloader
from devine.core.drm import Widevine
from devine.core.events import events
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
                    segment_base = rep.find("SegmentBase")

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
                        track_fps = get("frameRate")
                        if not track_fps and segment_base is not None:
                            track_fps = segment_base.get("timescale")

                        track_args = dict(
                            range_=self.get_video_range(
                                codecs,
                                findall("SupplementalProperty"),
                                findall("EssentialProperty")
                            ),
                            bitrate=get("bandwidth") or None,
                            width=get("width") or 0,
                            height=get("height") or 0,
                            fps=track_fps or None
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
                            cc=self.is_closed_caption(adaptation_set),
                            sdh=self.is_sdh(adaptation_set),
                            forced=self.is_forced(adaptation_set)
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
                    track_id = hex(crc32("{codec}-{lang}-{bitrate}-{base_url}-{ids}-{track_args}".format(
                        codec=codecs,
                        lang=track_lang,
                        bitrate=get("bitrate"),
                        base_url=(rep.findtext("BaseURL") or "").split("?")[0],
                        ids=[get("audioTrackId"), get("id"), period.get("id")],
                        track_args=track_args
                    ).encode()))[2:]

                    tracks.add(track_type(
                        id_=track_id,
                        url=self.url,
                        codec=track_codec,
                        language=track_lang,
                        is_original_lang=language and is_close_match(track_lang, [language]),
                        descriptor=Video.Descriptor.DASH,
                        data={
                            "dash": {
                                "manifest": self.manifest,
                                "period": period,
                                "adaptation_set": adaptation_set,
                                "representation": rep
                            }
                        },
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
        max_workers: Optional[int] = None,
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

        manifest: ElementTree = track.data["dash"]["manifest"]
        period: Element = track.data["dash"]["period"]
        adaptation_set: Element = track.data["dash"]["adaptation_set"]
        representation: Element = track.data["dash"]["representation"]

        track.drm = DASH.get_drm(
            representation.findall("ContentProtection") +
            adaptation_set.findall("ContentProtection")
        )

        manifest_base_url = manifest.findtext("BaseURL")
        if not manifest_base_url:
            manifest_base_url = track.url
        elif not re.match("^https?://", manifest_base_url, re.IGNORECASE):
            manifest_base_url = urljoin(track.url, f"./{manifest_base_url}")
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

        segment_base = representation.find("SegmentBase")
        if segment_base is None:
            segment_base = adaptation_set.find("SegmentBase")

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
                if not urlparse(value).query:
                    manifest_url_query = urlparse(track.url).query
                    if manifest_url_query:
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
                if not source_url:
                    source_url = rep_base_url
                elif not re.match("^https?://", source_url, re.IGNORECASE):
                    source_url = urljoin(rep_base_url, f"./{source_url}")

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
                if not media_url:
                    media_url = rep_base_url
                elif not re.match("^https?://", media_url, re.IGNORECASE):
                    media_url = urljoin(rep_base_url, f"./{media_url}")

                segments.append((
                    media_url,
                    segment_url.get("mediaRange")
                ))
        elif segment_base is not None:
            media_range = None
            init_data = None
            initialization = segment_base.find("Initialization")
            if initialization is not None:
                if initialization.get("range"):
                    init_range_header = {"Range": f"bytes={initialization.get('range')}"}
                else:
                    init_range_header = None

                res = session.get(url=rep_base_url, headers=init_range_header)
                res.raise_for_status()
                init_data = res.content
                track_kid = track.get_key_id(init_data)
                total_size = res.headers.get("Content-Range", "").split("/")[-1]
                if total_size:
                    media_range = f"{len(init_data)}-{total_size}"

            segments.append((
                rep_base_url,
                media_range
            ))
        elif rep_base_url:
            segments.append((
                rep_base_url,
                None
            ))
        else:
            log.error("Could not find a way to get segments from this MPD manifest.")
            log.debug(track.url)
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

        downloader = track.downloader
        if downloader.__name__ == "aria2c" and any(bytes_range is not None for url, bytes_range in segments):
            # aria2(c) is shit and doesn't support the Range header, fallback to the requests downloader
            downloader = requests_downloader

        for status_update in downloader(
            urls=[
                {
                    "url": url,
                    "headers": {
                        "Range": f"bytes={bytes_range}"
                    } if bytes_range else {}
                }
                for url, bytes_range in segments
            ],
            output_dir=save_dir,
            filename="{i:0%d}.mp4" % (len(str(len(segments)))),
            headers=session.headers,
            cookies=session.cookies,
            proxy=proxy,
            max_workers=max_workers
        ):
            file_downloaded = status_update.get("file_downloaded")
            if file_downloaded:
                events.emit(events.Types.SEGMENT_DOWNLOADED, track=track, segment=file_downloaded)
            else:
                downloaded = status_update.get("downloaded")
                if downloaded and downloaded.endswith("/s"):
                    status_update["downloaded"] = f"DASH {downloaded}"
                progress(**status_update)

        # see https://github.com/devine-dl/devine/issues/71
        for control_file in save_dir.glob("*.aria2__temp"):
            control_file.unlink()

        segments_to_merge = [
            x
            for x in sorted(save_dir.iterdir())
            if x.is_file()
        ]
        with open(save_path, "wb") as f:
            if init_data:
                f.write(init_data)
            if len(segments_to_merge) > 1:
                progress(downloaded="Merging", completed=0, total=len(segments_to_merge))
            for segment_file in segments_to_merge:
                segment_data = segment_file.read_bytes()
                # TODO: fix encoding after decryption?
                if (
                    not drm and isinstance(track, Subtitle) and
                    track.codec not in (Subtitle.Codec.fVTT, Subtitle.Codec.fTTML)
                ):
                    segment_data = try_ensure_utf8(segment_data)
                    segment_data = segment_data.decode("utf8"). \
                        replace("&lrm;", html.unescape("&lrm;")). \
                        replace("&rlm;", html.unescape("&rlm;")). \
                        encode("utf8")
                f.write(segment_data)
                f.flush()
                segment_file.unlink()
                progress(advance=1)

        track.path = save_path
        events.emit(events.Types.TRACK_DOWNLOADED, track=track)

        if drm:
            progress(downloaded="Decrypting", completed=0, total=100)
            drm.decrypt(save_path)
            track.drm = None
            events.emit(
                events.Types.TRACK_DECRYPTED,
                track=track,
                drm=drm,
                segment=None
            )
            progress(downloaded="Decrypting", advance=100)

        save_dir.rmdir()

        progress(downloaded="Downloaded")

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
    def is_sdh(adaptation_set: Element) -> bool:
        """Check if contents of Adaptation Set is for the Hearing Impaired."""
        return any(
            (x.get("schemeIdUri"), x.get("value")) == ("urn:tva:metadata:cs:AudioPurposeCS:2007", "2")
            for x in adaptation_set.findall("Accessibility")
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
