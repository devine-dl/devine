from __future__ import annotations

import asyncio
import base64
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
from threading import Event
from typing import Any, Callable, Optional, Union
from urllib.parse import urljoin, urlparse
from uuid import UUID

import requests
from langcodes import Language, tag_is_valid
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session
from rich import filesize

from devine.core.constants import AnyTrack
from devine.core.downloaders import aria2c
from devine.core.drm import Widevine
from devine.core.tracks import Audio, Subtitle, Tracks, Video
from devine.core.utilities import is_close_match
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

            for adaptation_set in period.findall("AdaptationSet"):
                trick_mode = any(
                    x.get("schemeIdUri") == "http://dashif.org/guidelines/trickmode"
                    for x in (
                            adaptation_set.findall("EssentialProperty") +
                            adaptation_set.findall("SupplementalProperty")
                    )
                )
                if trick_mode:
                    # we don't want trick mode streams (they are only used for fast-forward/rewind)
                    continue

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

                for rep in adaptation_set.findall("Representation"):
                    codecs = rep.get("codecs") or adaptation_set.get("codecs")

                    content_type = adaptation_set.get("contentType") or \
                        adaptation_set.get("mimeType") or \
                        rep.get("contentType") or \
                        rep.get("mimeType")
                    if not content_type:
                        raise ValueError("No content type value could be found")
                    content_type = content_type.split("/")[0]

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

                    supplements = rep.findall("SupplementalProperty") + adaptation_set.findall("SupplementalProperty")

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
                        url=(self.url, rep, adaptation_set, period),
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
                                (
                                    rep.find("SegmentBase").get("timescale") if
                                    rep.find("SegmentBase") is not None else None
                                )
                            )
                        ) if track_type is Video else dict(
                            bitrate=rep.get("bandwidth"),
                            channels=next(iter(
                                rep.xpath("AudioChannelConfiguration/@value")
                                or adaptation_set.xpath("AudioChannelConfiguration/@value")
                            ), None),
                            joc=joc,
                            descriptive=descriptive
                        ) if track_type is Audio else dict(
                            forced=forced,
                            cc=cc
                        ) if track_type is Subtitle else {})
                    ))

            # only get tracks from the first main-content period
            break

        return tracks

    @staticmethod
    def download_track(
        track: AnyTrack,
        save_path: Path,
        save_dir: Path,
        stop_event: Event,
        progress: partial,
        session: Optional[Session] = None,
        proxy: Optional[str] = None,
        license_widevine: Optional[Callable] = None
    ):
        if not session:
            session = Session()
        elif not isinstance(session, Session):
            raise TypeError(f"Expected session to be a {Session}, not {session!r}")

        if not track.needs_proxy and proxy:
            proxy = None

        if proxy:
            session.proxies.update({
                "all": proxy
            })

        log = logging.getLogger("DASH")

        manifest_url, representation, adaptation_set, period = track.url

        drm = DASH.get_drm(
            representation.findall("ContentProtection") +
            adaptation_set.findall("ContentProtection")
        )
        if drm:
            track.drm = drm
            drm = drm[0]  # just use the first supported DRM system for now
            if isinstance(drm, Widevine):
                # license and grab content keys
                if not license_widevine:
                    raise ValueError("license_widevine func must be supplied to use Widevine DRM")
                license_widevine(drm)
        else:
            drm = None

        manifest = load_xml(session.get(manifest_url).text)
        manifest_url_query = urlparse(manifest_url).query

        period_base_url = period.findtext("BaseURL") or manifest.findtext("BaseURL")
        if not period_base_url or not re.match("^https?://", period_base_url, re.IGNORECASE):
            period_base_url = urljoin(manifest_url, period_base_url)
        period_duration = period.get("duration") or manifest.get("mediaPresentationDuration")

        init_data: Optional[bytes] = None
        base_url = representation.findtext("BaseURL") or period_base_url

        segment_template = representation.find("SegmentTemplate")
        if segment_template is None:
            segment_template = adaptation_set.find("SegmentTemplate")

        segment_list = representation.find("SegmentList")
        if segment_list is None:
            segment_list = adaptation_set.find("SegmentList")

        if segment_template is None and segment_list is None and base_url:
            # If there's no SegmentTemplate and no SegmentList, then SegmentBase is used or just BaseURL
            # Regardless which of the two is used, we can just directly grab the BaseURL
            # Players would normally calculate segments via Byte-Ranges, but we don't care
            track.url = urljoin(period_base_url, base_url)
            track.descriptor = track.Descriptor.URL
        else:
            segments: list[tuple[str, Optional[str]]] = []

            if segment_template is not None:
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
                base_media_url = urljoin(period_base_url, base_url)

                init_data = None
                initialization = segment_list.find("Initialization")
                if initialization:
                    source_url = initialization.get("sourceURL")
                    if source_url is None:
                        source_url = base_media_url

                    res = session.get(source_url)
                    res.raise_for_status()
                    init_data = res.content

                segment_urls = segment_list.findall("SegmentURL")
                for segment_url in segment_urls:
                    media_url = segment_url.get("media")
                    if media_url is None:
                        media_url = base_media_url

                    segments.append((
                        media_url,
                        segment_url.get("mediaRange")
                    ))
            else:
                log.error("Could not find a way to get segments from this MPD manifest.")
                log.debug(manifest_url)
                sys.exit(1)

            if not drm and isinstance(track, (Video, Audio)):
                try:
                    drm = Widevine.from_init_data(init_data)
                except Widevine.Exceptions.PSSHNotFound:
                    # it might not have Widevine DRM, or might not have found the PSSH
                    log.warning("No Widevine PSSH was found for this track, is it DRM free?")
                else:
                    track.drm = [drm]
                    # license and grab content keys
                    if not license_widevine:
                        raise ValueError("license_widevine func must be supplied to use Widevine DRM")
                    license_widevine(drm)

            def download_segment(filename: str, segment: tuple[str, Optional[str]]) -> int:
                if stop_event.is_set():
                    # the track already started downloading, but another failed or was stopped
                    raise KeyboardInterrupt()

                segment_save_path = (save_dir / filename).with_suffix(".mp4")

                segment_uri, segment_range = segment

                if segment_range:
                    # aria2(c) doesn't support byte ranges, let's use python-requests (likely slower)
                    r = session.get(
                        url=segment_uri,
                        headers={
                            "Range": f"bytes={segment_range}"
                        }
                    )
                    r.raise_for_status()
                    segment_save_path.parent.mkdir(parents=True, exist_ok=True)
                    segment_save_path.write_bytes(res.content)
                else:
                    asyncio.run(aria2c(
                        uri=segment_uri,
                        out=segment_save_path,
                        headers=session.headers,
                        proxy=proxy,
                        segmented=True
                    ))

                data_size = segment_save_path.stat().st_size

                if isinstance(track, Audio) or init_data:
                    with open(segment_save_path, "rb+") as f:
                        segment_data = f.read()
                        if isinstance(track, Audio):
                            # fix audio decryption on ATVP by fixing the sample description index
                            # TODO: Is this in mpeg data, or init data?
                            segment_data = re.sub(
                                b"(tfhd\x00\x02\x00\x1a\x00\x00\x00\x01\x00\x00\x00)\x02",
                                b"\\g<1>\x01",
                                segment_data
                            )
                        # prepend the init data to be able to decrypt
                        if init_data:
                            f.seek(0)
                            f.write(init_data)
                            f.write(segment_data)

                if drm:
                    # TODO: What if the manifest does not mention DRM, but has DRM
                    drm.decrypt(segment_save_path)
                    track.drm = None
                    if callable(track.OnDecrypted):
                        track.OnDecrypted(track)

                return data_size

            progress(total=len(segments))

            finished_threads = 0
            download_sizes = []
            last_speed_refresh = time.time()

            with ThreadPoolExecutor(max_workers=16) as pool:
                for download in futures.as_completed((
                    pool.submit(
                        download_segment,
                        filename=str(i).zfill(len(str(len(segments)))),
                        segment=segment
                    )
                    for i, segment in enumerate(segments)
                )):
                    finished_threads += 1

                    try:
                        download_size = download.result()
                    except KeyboardInterrupt:
                        stop_event.set()  # skip pending track downloads
                        progress(downloaded="[yellow]STOPPING")
                        pool.shutdown(wait=True, cancel_futures=True)
                        progress(downloaded="[yellow]STOPPED")
                        # tell dl that it was cancelled
                        # the pool is already shut down, so exiting loop is fine
                        raise
                    except Exception as e:
                        stop_event.set()  # skip pending track downloads
                        progress(downloaded="[red]FAILING")
                        pool.shutdown(wait=True, cancel_futures=True)
                        progress(downloaded="[red]FAILED")
                        # tell dl that it failed
                        # the pool is already shut down, so exiting loop is fine
                        raise e
                    else:
                        # it successfully downloaded, and it was not cancelled
                        progress(advance=1)

                        now = time.time()
                        time_since = now - last_speed_refresh

                        if download_size:  # no size == skipped dl
                            download_sizes.append(download_size)

                        if download_sizes and (time_since > 5 or finished_threads == len(segments)):
                            data_size = sum(download_sizes)
                            download_speed = data_size / time_since
                            progress(downloaded=f"DASH {filesize.decimal(download_speed)}/s")
                            last_speed_refresh = now
                            download_sizes.clear()

            with open(save_path, "wb") as f:
                for segment_file in sorted(save_dir.iterdir()):
                    f.write(segment_file.read_bytes())
                    segment_file.unlink()

            track.path = save_path
            save_dir.rmdir()

    @staticmethod
    def get_language(*options: Any) -> Optional[Language]:
        for option in options:
            option = (str(option) or "").strip()
            if not tag_is_valid(option) or option.startswith("und"):
                continue
            return Language.get(option)

    @staticmethod
    def get_drm(protections) -> list[Widevine]:
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


__ALL__ = (DASH,)
