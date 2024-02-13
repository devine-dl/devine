from __future__ import annotations

import html
import logging
import re
import shutil
import subprocess
import sys
import time
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from hashlib import md5
from pathlib import Path
from queue import Queue
from threading import Lock
from typing import Any, Callable, Optional, Union
from urllib.parse import urljoin

import m3u8
import requests
from langcodes import Language, tag_is_valid
from m3u8 import M3U8
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session
from rich import filesize

from devine.core.constants import DOWNLOAD_CANCELLED, DOWNLOAD_LICENCE_ONLY, AnyTrack
from devine.core.downloaders import downloader
from devine.core.downloaders import requests as requests_downloader
from devine.core.drm import DRM_T, ClearKey, Widevine
from devine.core.tracks import Audio, Subtitle, Tracks, Video
from devine.core.utilities import get_binary_path, is_close_match, try_ensure_utf8


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
                url=urljoin(playlist.base_uri, playlist.uri),
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
            if not media.uri:
                continue

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

            track_lang = next((
                Language.get(option)
                for x in (media.language, language)
                for option in [(str(x) or "").strip()]
                if tag_is_valid(option) and not option.startswith("und")
            ), None)
            if not track_lang:
                msg = "Language information could not be derived for a media."
                if language is None:
                    msg += " No fallback language was provided when calling HLS.to_tracks()."
                elif not tag_is_valid((str(language) or "").strip()) or str(language).startswith("und"):
                    msg += f" The fallback language provided is also invalid: {language}"
                raise ValueError(msg)

            tracks.add(track_type(
                id_=md5(str(media).encode()).hexdigest()[0:6],  # 6 chars only for filename length
                url=urljoin(media.base_uri, media.uri),
                codec=codec,
                language=track_lang,  # HLS media may not have language info, fallback if needed
                is_original_lang=language and is_close_match(track_lang, [language]),
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
        progress: partial,
        session: Optional[Session] = None,
        proxy: Optional[str] = None,
        license_widevine: Optional[Callable] = None
    ) -> None:
        if not session:
            session = Session()
        elif not isinstance(session, Session):
            raise TypeError(f"Expected session to be a {Session}, not {session!r}")

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

        if track.drm:
            # TODO: What if we don't want to use the first DRM system?
            session_drm = track.drm[0]
            if isinstance(session_drm, Widevine):
                # license and grab content keys
                try:
                    if not license_widevine:
                        raise ValueError("license_widevine func must be supplied to use Widevine DRM")
                    progress(downloaded="LICENSING")
                    license_widevine(session_drm)
                    progress(downloaded="[yellow]LICENSED")
                except Exception:  # noqa
                    DOWNLOAD_CANCELLED.set()  # skip pending track downloads
                    progress(downloaded="[red]FAILED")
                    raise
        else:
            session_drm = None

        progress(total=len(master.segments))

        download_sizes = []
        download_speed_window = 5
        last_speed_refresh = time.time()

        segment_key = Queue(maxsize=1)
        segment_key.put((session_drm, None))
        init_data = Queue(maxsize=1)
        init_data.put(None)
        range_offset = Queue(maxsize=1)
        range_offset.put(0)
        drm_lock = Lock()

        discontinuities: list[list[segment]] = []
        discontinuity_index = -1
        for i, segment in enumerate(master.segments):
            if i == 0 or segment.discontinuity:
                discontinuity_index += 1
                discontinuities.append([])
            discontinuities[discontinuity_index].append(segment)

        for d_i, discontinuity in enumerate(discontinuities):
            # each discontinuity is a separate 'file'/encode and must be processed separately
            discontinuity_save_dir = save_dir / str(d_i).zfill(len(str(len(discontinuities))))
            discontinuity_save_path = discontinuity_save_dir.with_suffix(Path(discontinuity[0].uri).suffix)

            with ThreadPoolExecutor(max_workers=16) as pool:
                for i, download in enumerate(futures.as_completed((
                    pool.submit(
                        HLS.download_segment,
                        segment=segment,
                        out_path=(
                            discontinuity_save_dir /
                            str(s_i).zfill(len(str(len(discontinuity))))
                        ).with_suffix(Path(segment.uri).suffix),
                        track=track,
                        init_data=init_data,
                        segment_key=segment_key,
                        range_offset=range_offset,
                        drm_lock=drm_lock,
                        progress=progress,
                        license_widevine=license_widevine,
                        session=session,
                        proxy=proxy
                    )
                    for s_i, segment in enumerate(discontinuity)
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
                    except Exception as e:
                        DOWNLOAD_CANCELLED.set()  # skip pending track downloads
                        progress(downloaded="[red]FAILING")
                        pool.shutdown(wait=True, cancel_futures=True)
                        progress(downloaded="[red]FAILED")
                        # tell dl that it failed
                        # the pool is already shut down, so exiting loop is fine
                        raise e
                    else:
                        # it successfully downloaded, and it was not cancelled
                        progress(advance=1)

                        if download_size == -1:  # skipped for --skip-dl
                            progress(downloaded="[yellow]SKIPPING")
                            continue

                        now = time.time()
                        time_since = now - last_speed_refresh

                        if download_size:  # no size == skipped dl
                            download_sizes.append(download_size)

                        if download_sizes and (time_since > download_speed_window or i == len(master.segments)):
                            data_size = sum(download_sizes)
                            download_speed = data_size / (time_since or 1)
                            progress(downloaded=f"HLS {filesize.decimal(download_speed)}/s")
                            last_speed_refresh = now
                            download_sizes.clear()

            if discontinuity_save_dir.exists():
                with open(discontinuity_save_path, "wb") as f:
                    for segment_file in sorted(discontinuity_save_dir.iterdir()):
                        segment_data = segment_file.read_bytes()
                        if isinstance(track, Subtitle):
                            segment_data = try_ensure_utf8(segment_data)
                            if track.codec not in (Subtitle.Codec.fVTT, Subtitle.Codec.fTTML):
                                # decode text direction entities or SubtitleEdit's /ReverseRtlStartEnd won't work
                                segment_data = segment_data.decode("utf8"). \
                                    replace("&lrm;", html.unescape("&lrm;")). \
                                    replace("&rlm;", html.unescape("&rlm;")). \
                                    encode("utf8")
                        f.write(segment_data)
                        segment_file.unlink()
                    shutil.rmtree(discontinuity_save_dir)

        if DOWNLOAD_LICENCE_ONLY.is_set():
            return

        if isinstance(track, (Video, Audio)):
            progress(downloaded="Merging")
            HLS.merge_segments(
                segments=sorted(list(save_dir.iterdir())),
                save_path=save_path
            )
            shutil.rmtree(save_dir)
        else:
            with open(save_path, "wb") as f:
                for discontinuity_file in sorted(save_dir.iterdir()):
                    discontinuity_data = discontinuity_file.read_bytes()
                    f.write(discontinuity_data)
                    discontinuity_file.unlink()
            save_dir.rmdir()

        progress(downloaded="Downloaded")

        track.path = save_path
        if callable(track.OnDownloaded):
            track.OnDownloaded()

    @staticmethod
    def download_segment(
        segment: m3u8.Segment,
        out_path: Path,
        track: AnyTrack,
        init_data: Queue,
        segment_key: Queue,
        range_offset: Queue,
        drm_lock: Lock,
        progress: partial,
        license_widevine: Optional[Callable] = None,
        session: Optional[Session] = None,
        proxy: Optional[str] = None
    ) -> int:
        """
        Download (and Decrypt) an HLS Media Segment.

        Note: Make sure all Queue objects passed are appropriately initialized with
              a starting value or this function may get permanently stuck.

        Parameters:
            segment: The m3u8.Segment Object to Download.
            out_path: Path to save the downloaded Segment file to.
            track: The Track object of which this Segment is for. Currently used to fix an
                invalid value in the TFHD box of Audio Tracks, for the OnSegmentFilter, and
                for DRM-related operations like getting the Track ID and Decryption.
            init_data: Queue for saving and loading the most recent init section data.
            segment_key: Queue for saving and loading the most recent DRM object, and it's
                adjacent Segment.Key object.
            range_offset: Queue for saving and loading the most recent Segment Bytes Range.
            drm_lock: Prevent more than one Download from doing anything DRM-related at the
                same time. Make sure all calls to download_segment() use the same Lock object.
            progress: Rich Progress bar to provide progress updates to.
            license_widevine: Function used to license Widevine DRM objects. It must be passed
                if the Segment's DRM uses Widevine.
            proxy: Proxy URI to use when downloading the Segment file.
            session: Python-Requests Session used when requesting init data.

        Returns the file size of the downloaded Segment in bytes.
        """
        if DOWNLOAD_CANCELLED.is_set():
            raise KeyboardInterrupt()

        if callable(track.OnSegmentFilter) and track.OnSegmentFilter(segment):
            return 0

        # handle init section changes
        newest_init_data = init_data.get()
        try:
            if segment.init_section and (not newest_init_data or segment.discontinuity):
                # Only use the init data if there's no init data yet (e.g., start of file)
                # or if EXT-X-DISCONTINUITY is reached at the same time as EXT-X-MAP.
                # Even if a new EXT-X-MAP is supplied, it may just be duplicate and would
                # be unnecessary and slow to re-download the init data each time.
                if segment.init_section.byterange:
                    previous_range_offset = range_offset.get()
                    byte_range = HLS.calculate_byte_range(segment.init_section.byterange, previous_range_offset)
                    range_offset.put(byte_range.split("-")[0])
                    range_header = {
                        "Range": f"bytes={byte_range}"
                    }
                else:
                    range_header = {}
                res = session.get(
                    url=urljoin(segment.init_section.base_uri, segment.init_section.uri),
                    headers=range_header
                )
                res.raise_for_status()
                newest_init_data = res.content
        finally:
            init_data.put(newest_init_data)

        # handle segment key changes
        with drm_lock:
            newest_segment_key = segment_key.get()
            try:
                if segment.keys and newest_segment_key[1] != segment.keys:
                    drm = HLS.get_drm(
                        keys=segment.keys,
                        proxy=proxy
                    )
                    if drm:
                        track.drm = drm
                        # license and grab content keys
                        # TODO: What if we don't want to use the first DRM system?
                        drm = drm[0]
                        if isinstance(drm, Widevine):
                            track_kid = track.get_key_id(newest_init_data)
                            if not license_widevine:
                                raise ValueError("license_widevine func must be supplied to use Widevine DRM")
                            progress(downloaded="LICENSING")
                            license_widevine(drm, track_kid=track_kid)
                            progress(downloaded="[yellow]LICENSED")
                        newest_segment_key = (drm, segment.keys)
            finally:
                segment_key.put(newest_segment_key)

            if DOWNLOAD_LICENCE_ONLY.is_set():
                return -1

        headers_ = session.headers
        if segment.byterange:
            # aria2(c) doesn't support byte ranges, use python-requests
            downloader_ = requests_downloader
            previous_range_offset = range_offset.get()
            byte_range = HLS.calculate_byte_range(segment.byterange, previous_range_offset)
            range_offset.put(byte_range.split("-")[0])
            headers_["Range"] = f"bytes={byte_range}"
        else:
            downloader_ = downloader

        downloader_(
            uri=urljoin(segment.base_uri, segment.uri),
            out=out_path,
            headers=headers_,
            cookies=session.cookies,
            proxy=proxy,
            segmented=True
        )

        if callable(track.OnSegmentDownloaded):
            track.OnSegmentDownloaded(out_path)

        download_size = out_path.stat().st_size

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

        # prepend the init data to be able to decrypt
        if newest_init_data:
            with open(out_path, "rb+") as f:
                segment_data = f.read()
                f.seek(0)
                f.write(newest_init_data)
                f.write(segment_data)

        # decrypt segment if encrypted
        if newest_segment_key[0]:
            newest_segment_key[0].decrypt(out_path)
            track.drm = None
            if callable(track.OnDecrypted):
                track.OnDecrypted(newest_segment_key[0], segment)

        return download_size

    @staticmethod
    def merge_segments(segments: list[Path], save_path: Path) -> int:
        """
        Concatenate Segments by first demuxing with FFmpeg.

        Returns the file size of the merged file.
        """
        ffmpeg = get_binary_path("ffmpeg")
        if not ffmpeg:
            raise EnvironmentError("FFmpeg executable was not found but is required to merge HLS segments.")

        demuxer_file = segments[0].parent / "ffmpeg_concat_demuxer.txt"
        demuxer_file.write_text("\n".join([
            f"file '{segment}'"
            for segment in segments
        ]))

        subprocess.check_call([
            ffmpeg, "-hide_banner",
            "-loglevel", "panic",
            "-f", "concat",
            "-safe", "0",
            "-i", demuxer_file,
            "-map", "0",
            "-c", "copy",
            save_path
        ])
        demuxer_file.unlink()

        return save_path.stat().st_size

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


__all__ = ("HLS",)
