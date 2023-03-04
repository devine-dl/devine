from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from hashlib import md5
from pathlib import Path
from queue import Queue
from threading import Event, Lock
from typing import Any, Callable, Optional, Union

import m3u8
import requests
from langcodes import Language
from m3u8 import M3U8
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session
from rich import filesize

from devine.core.constants import AnyTrack
from devine.core.downloaders import aria2c
from devine.core.drm import DRM_T, ClearKey, Widevine
from devine.core.tracks import Audio, Subtitle, Tracks, Video
from devine.core.utilities import is_close_match


class HLS:
    def __init__(self, manifest: M3U8, session: Optional[Session] = None):
        if not manifest:
            raise ValueError("HLS manifest must be provided.")
        if not isinstance(manifest, M3U8):
            raise TypeError(f"Expected manifest to be a {M3U8}, not {manifest!r}")
        if not manifest.is_variant:
            raise ValueError("Expected the M3U(8) manifest to be a Variant Playlist.")

        self.manifest = manifest
        self.session = session or Session()

    @classmethod
    def from_url(cls, url: str, session: Optional[Session] = None, **args: Any) -> HLS:
        if not url:
            raise requests.URLRequired("HLS manifest URL must be provided.")
        if not isinstance(url, str):
            raise TypeError(f"Expected url to be a {str}, not {url!r}")

        if not session:
            session = Session()
        elif not isinstance(session, Session):
            raise TypeError(f"Expected session to be a {Session}, not {session!r}")

        res = session.get(url, **args)
        if not res.ok:
            raise requests.ConnectionError(
                "Failed to request the M3U(8) document.",
                response=res
            )

        master = m3u8.loads(res.text, uri=url)

        return cls(master, session)

    @classmethod
    def from_text(cls, text: str, url: str) -> HLS:
        if not text:
            raise ValueError("HLS manifest Text must be provided.")
        if not isinstance(text, str):
            raise TypeError(f"Expected text to be a {str}, not {text!r}")

        if not url:
            raise requests.URLRequired("HLS manifest URL must be provided for relative path computations.")
        if not isinstance(url, str):
            raise TypeError(f"Expected url to be a {str}, not {url!r}")

        master = m3u8.loads(text, uri=url)

        return cls(master)

    def to_tracks(self, language: Union[str, Language]) -> Tracks:
        """
        Convert a Variant Playlist M3U(8) document to Video, Audio and Subtitle Track objects.

        Parameters:
            language: Language you expect the Primary Track to be in.

        All Track objects' URL will be to another M3U(8) document. However, these documents
        will be Invariant Playlists and contain the list of segments URIs among other metadata.
        """
        session_drm = HLS.get_drm(self.manifest.session_keys)

        audio_codecs_by_group_id: dict[str, Audio.Codec] = {}
        tracks = Tracks()

        for playlist in self.manifest.playlists:
            url = playlist.uri
            if not re.match("^https?://", url):
                url = playlist.base_uri + url

            audio_group = playlist.stream_info.audio
            if audio_group:
                audio_codec = Audio.Codec.from_codecs(playlist.stream_info.codecs)
                audio_codecs_by_group_id[audio_group] = audio_codec

            try:
                # TODO: Any better way to figure out the primary track type?
                Video.Codec.from_codecs(playlist.stream_info.codecs)
            except ValueError:
                primary_track_type = Audio
            else:
                primary_track_type = Video

            tracks.add(primary_track_type(
                id_=md5(str(playlist).encode()).hexdigest()[0:7],  # 7 chars only for filename length
                url=url,
                codec=primary_track_type.Codec.from_codecs(playlist.stream_info.codecs),
                language=language,  # HLS manifests do not seem to have language info
                is_original_lang=True,  # TODO: All we can do is assume Yes
                bitrate=playlist.stream_info.average_bandwidth or playlist.stream_info.bandwidth,
                descriptor=Video.Descriptor.M3U,
                drm=session_drm,
                extra=playlist,
                # video track args
                **(dict(
                    range_=Video.Range.DV if any(
                        codec.split(".")[0] in ("dva1", "dvav", "dvhe", "dvh1")
                        for codec in playlist.stream_info.codecs.lower().split(",")
                    ) else Video.Range.from_m3u_range_tag(playlist.stream_info.video_range),
                    width=playlist.stream_info.resolution[0],
                    height=playlist.stream_info.resolution[1],
                    fps=playlist.stream_info.frame_rate
                ) if primary_track_type is Video else {})
            ))

        for media in self.manifest.media:
            url = media.uri
            if not url:
                continue

            if not re.match("^https?://", url):
                url = media.base_uri + url

            joc = 0
            if media.type == "AUDIO":
                track_type = Audio
                codec = audio_codecs_by_group_id.get(media.group_id)
                if media.channels and media.channels.endswith("/JOC"):
                    joc = int(media.channels.split("/JOC")[0])
                    media.channels = "5.1"
            else:
                track_type = Subtitle
                codec = Subtitle.Codec.WebVTT  # assuming WebVTT, codec info isn't shown

            tracks.add(track_type(
                id_=md5(str(media).encode()).hexdigest()[0:6],  # 6 chars only for filename length
                url=url,
                codec=codec,
                language=media.language or language,  # HLS media may not have language info, fallback if needed
                is_original_lang=language and is_close_match(media.language, [language]),
                descriptor=Audio.Descriptor.M3U,
                drm=session_drm if media.type == "AUDIO" else None,
                extra=media,
                # audio track args
                **(dict(
                    bitrate=0,  # TODO: M3U doesn't seem to state bitrate?
                    channels=media.channels,
                    joc=joc,
                    descriptive="public.accessibility.describes-video" in (media.characteristics or ""),
                ) if track_type is Audio else dict(
                    forced=media.forced == "YES",
                    sdh="public.accessibility.describes-music-and-sound" in (media.characteristics or ""),
                ) if track_type is Subtitle else {})
            ))

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
    ) -> None:
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

        log = logging.getLogger("HLS")

        master = m3u8.loads(
            # should be an invariant m3u8 playlist URI
            session.get(track.url).text,
            uri=track.url
        )

        if not master.segments:
            log.error("Track's HLS playlist has no segments, expecting an invariant M3U8 playlist.")
            sys.exit(1)

        drm_lock = Lock()

        def download_segment(filename: str, segment: m3u8.Segment, init_data: Queue, segment_key: Queue) -> int:
            if stop_event.is_set():
                # the track already started downloading, but another failed or was stopped
                raise KeyboardInterrupt()

            segment_save_path = (save_dir / filename).with_suffix(".mp4")

            with drm_lock:
                newest_segment_key = segment_key.get()
                try:
                    if segment.key and newest_segment_key[1] != segment.key:
                        try:
                            drm = HLS.get_drm(
                                # TODO: We append master.keys because m3u8 class only puts the last EXT-X-KEY
                                #       to the segment.key property, not supporting multi-drm scenarios.
                                #       By re-adding every single EXT-X-KEY found, we can at least try to get
                                #       a suitable key. However, it may not match the right segment/timeframe!
                                #       It will try to use the first key provided where possible.
                                keys=[segment.key] + master.keys,
                                proxy=proxy
                            )
                        except NotImplementedError as e:
                            log.error(str(e))
                            sys.exit(1)
                        else:
                            if drm:
                                track.drm = drm
                                drm = drm[0]  # just use the first supported DRM system for now
                                log.debug("Got segment key, %s", drm)
                                if isinstance(drm, Widevine):
                                    # license and grab content keys
                                    if not license_widevine:
                                        raise ValueError("license_widevine func must be supplied to use Widevine DRM")
                                    license_widevine(drm)
                                newest_segment_key = (drm, segment.key)
                finally:
                    segment_key.put(newest_segment_key)

            if callable(track.OnSegmentFilter) and track.OnSegmentFilter(segment):
                return 0

            newest_init_data = init_data.get()
            try:
                if segment.init_section and (not newest_init_data or segment.discontinuity):
                    # Only use the init data if there's no init data yet (e.g., start of file)
                    # or if EXT-X-DISCONTINUITY is reached at the same time as EXT-X-MAP.
                    # Even if a new EXT-X-MAP is supplied, it may just be duplicate and would
                    # be unnecessary and slow to re-download the init data each time.
                    if not segment.init_section.uri.startswith(segment.init_section.base_uri):
                        segment.init_section.uri = segment.init_section.base_uri + segment.init_section.uri

                    if segment.init_section.byterange:
                        byte_range = HLS.calculate_byte_range(segment.init_section.byterange)
                        _ = range_offset.get()
                        range_offset.put(byte_range.split("-")[0])
                        headers = {
                            "Range": f"bytes={byte_range}"
                        }
                    else:
                        headers = {}

                    log.debug("Got new init segment, %s", segment.init_section.uri)
                    res = session.get(segment.init_section.uri, headers=headers)
                    res.raise_for_status()
                    newest_init_data = res.content
            finally:
                init_data.put(newest_init_data)

            if not segment.uri.startswith(segment.base_uri):
                segment.uri = segment.base_uri + segment.uri

            if segment.byterange:
                # aria2(c) doesn't support byte ranges, let's use python-requests (likely slower)
                previous_range_offset = range_offset.get()
                byte_range = HLS.calculate_byte_range(segment.byterange, previous_range_offset)
                range_offset.put(byte_range.split("-")[0])

                res = session.get(
                    url=segment.uri,
                    headers={
                        "Range": f"bytes={byte_range}"
                    }
                )
                res.raise_for_status()

                segment_save_path.parent.mkdir(parents=True, exist_ok=True)
                segment_save_path.write_bytes(res.content)
            else:
                asyncio.run(aria2c(
                    uri=segment.uri,
                    out=segment_save_path,
                    headers=session.headers,
                    proxy=proxy,
                    segmented=True
                ))

            data_size = segment_save_path.stat().st_size

            if isinstance(track, Audio) or newest_init_data:
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
                    if newest_init_data:
                        f.seek(0)
                        f.write(newest_init_data)
                        f.write(segment_data)

            if newest_segment_key[0]:
                newest_segment_key[0].decrypt(segment_save_path)
                track.drm = None
                if callable(track.OnDecrypted):
                    track.OnDecrypted(track)

            return data_size

        segment_key = Queue(maxsize=1)
        init_data = Queue(maxsize=1)
        range_offset = Queue(maxsize=1)

        if track.drm:
            session_drm = track.drm[0]  # just use the first supported DRM system for now
            if isinstance(session_drm, Widevine):
                # license and grab content keys
                if not license_widevine:
                    raise ValueError("license_widevine func must be supplied to use Widevine DRM")
                license_widevine(session_drm)
        else:
            session_drm = None

        # have data to begin with, or it will be stuck waiting on the first pool forever
        segment_key.put((session_drm, None))
        init_data.put(None)
        range_offset.put(0)

        progress(total=len(master.segments))

        finished_threads = 0
        download_sizes = []
        last_speed_refresh = time.time()

        with ThreadPoolExecutor(max_workers=16) as pool:
            for download in futures.as_completed((
                pool.submit(
                    download_segment,
                    filename=str(i).zfill(len(str(len(master.segments)))),
                    segment=segment,
                    init_data=init_data,
                    segment_key=segment_key
                )
                for i, segment in enumerate(master.segments)
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

                    if download_sizes and (time_since > 5 or finished_threads == len(master.segments)):
                        data_size = sum(download_sizes)
                        download_speed = data_size / time_since
                        progress(downloaded=f"HLS {filesize.decimal(download_speed)}/s")
                        last_speed_refresh = now
                        download_sizes.clear()

        with open(save_path, "wb") as f:
            for segment_file in sorted(save_dir.iterdir()):
                f.write(segment_file.read_bytes())
                segment_file.unlink()

        track.path = save_path
        save_dir.rmdir()

    @staticmethod
    def get_drm(
        keys: list[Union[m3u8.model.SessionKey, m3u8.model.Key]],
        proxy: Optional[str] = None
    ) -> list[DRM_T]:
        """
        Convert HLS EXT-X-KEY data to initialized DRM objects.

        You can supply key data for a single segment or for the entire manifest.
        This lets you narrow the results down to each specific segment's DRM status.

        Returns an empty list if there were no supplied EXT-X-KEY data, or if all the
        EXT-X-KEY's were of blank data. An empty list signals a DRM-free stream or segment.

        Will raise a NotImplementedError if EXT-X-KEY data was supplied and none of them
        were supported. A DRM-free track will never raise NotImplementedError.
        """
        drm = []
        unsupported_systems = []

        for key in keys:
            if not key:
                continue
            # TODO: Add support for 'SAMPLE-AES', 'AES-CTR', 'AES-CBC', 'ClearKey'
            if key.method == "NONE":
                return []
            elif key.method == "AES-128":
                drm.append(ClearKey.from_m3u_key(key, proxy))
            elif key.method == "ISO-23001-7":
                drm.append(Widevine(
                    pssh=PSSH.new(
                        key_ids=[key.uri.split(",")[-1]],
                        system_id=PSSH.SystemId.Widevine
                    )
                ))
            elif key.keyformat and key.keyformat.lower() == WidevineCdm.urn:
                drm.append(Widevine(
                    pssh=PSSH(key.uri.split(",")[-1]),
                    **key._extra_params  # noqa
                ))
            else:
                unsupported_systems.append(key.method + (f" ({key.keyformat})" if key.keyformat else ""))

        if not drm and unsupported_systems:
            raise NotImplementedError(f"No support for any of the key systems: {', '.join(unsupported_systems)}")

        return drm

    @staticmethod
    def calculate_byte_range(m3u_range: str, fallback_offset: int = 0) -> str:
        """
        Convert a HLS EXT-X-BYTERANGE value to a more traditional range value.
        E.g., '1433@0' -> '0-1432', '357392@1433' -> '1433-358824'.
        """
        parts = [int(x) for x in m3u_range.split("@")]
        if len(parts) != 2:
            parts.append(fallback_offset)
        length, offset = parts
        return f"{offset}-{offset + length - 1}"


__ALL__ = (HLS,)
