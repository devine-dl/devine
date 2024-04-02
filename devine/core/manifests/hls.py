from __future__ import annotations

import html
import logging
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional, Union
from urllib.parse import urljoin
from zlib import crc32

import m3u8
import requests
from langcodes import Language, tag_is_valid
from m3u8 import M3U8
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session

from devine.core.constants import DOWNLOAD_CANCELLED, DOWNLOAD_LICENCE_ONLY, AnyTrack
from devine.core.downloaders import requests as requests_downloader
from devine.core.drm import DRM_T, ClearKey, Widevine
from devine.core.events import events
from devine.core.tracks import Audio, Subtitle, Tracks, Video
from devine.core.utilities import get_binary_path, get_extension, is_close_match, try_ensure_utf8


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
        session_drm = HLS.get_all_drm(self.manifest.session_keys)

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
                id_=hex(crc32(str(playlist).encode()))[2:],
                url=urljoin(playlist.base_uri, playlist.uri),
                codec=primary_track_type.Codec.from_codecs(playlist.stream_info.codecs),
                language=language,  # HLS manifests do not seem to have language info
                is_original_lang=True,  # TODO: All we can do is assume Yes
                bitrate=playlist.stream_info.average_bandwidth or playlist.stream_info.bandwidth,
                descriptor=Video.Descriptor.HLS,
                drm=session_drm,
                data={
                    "hls": {
                        "playlist": playlist
                    }
                },
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
                id_=hex(crc32(str(media).encode()))[2:],
                url=urljoin(media.base_uri, media.uri),
                codec=codec,
                language=track_lang,  # HLS media may not have language info, fallback if needed
                is_original_lang=language and is_close_match(track_lang, [language]),
                descriptor=Audio.Descriptor.HLS,
                drm=session_drm if media.type == "AUDIO" else None,
                data={
                    "hls": {
                        "media": media
                    }
                },
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
        max_workers: Optional[int] = None,
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

        unwanted_segments = [
            segment for segment in master.segments
            if callable(track.OnSegmentFilter) and track.OnSegmentFilter(segment)
        ]

        total_segments = len(master.segments) - len(unwanted_segments)
        progress(total=total_segments)

        downloader = track.downloader

        urls: list[dict[str, Any]] = []
        range_offset = 0
        for segment in master.segments:
            if segment in unwanted_segments:
                continue

            if segment.byterange:
                if downloader.__name__ == "aria2c":
                    # aria2(c) is shit and doesn't support the Range header, fallback to the requests downloader
                    downloader = requests_downloader
                byte_range = HLS.calculate_byte_range(segment.byterange, range_offset)
                range_offset = byte_range.split("-")[0]
            else:
                byte_range = None

            urls.append({
                "url": urljoin(segment.base_uri, segment.uri),
                "headers": {
                    "Range": f"bytes={byte_range}"
                } if byte_range else {}
            })

        segment_save_dir = save_dir / "segments"

        for status_update in downloader(
            urls=urls,
            output_dir=segment_save_dir,
            filename="{i:0%d}{ext}" % len(str(len(urls))),
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
                    status_update["downloaded"] = f"HLS {downloaded}"
                progress(**status_update)

        # see https://github.com/devine-dl/devine/issues/71
        for control_file in segment_save_dir.glob("*.aria2__temp"):
            control_file.unlink()

        progress(total=total_segments, completed=0, downloaded="Merging")

        name_len = len(str(total_segments))
        discon_i = 0
        range_offset = 0
        map_data: Optional[tuple[m3u8.model.InitializationSection, bytes]] = None
        if session_drm:
            encryption_data: Optional[tuple[Optional[m3u8.Key], DRM_T]] = (None, session_drm)
        else:
            encryption_data: Optional[tuple[Optional[m3u8.Key], DRM_T]] = None

        i = -1
        for real_i, segment in enumerate(master.segments):
            if segment not in unwanted_segments:
                i += 1

            is_last_segment = (real_i + 1) == len(master.segments)

            def merge(to: Path, via: list[Path], delete: bool = False, include_map_data: bool = False):
                """
                Merge all files to a given path, optionally including map data.

                Parameters:
                    to: The output file with all merged data.
                    via: List of files to merge, in sequence.
                    delete: Delete the file once it's been merged.
                    include_map_data: Whether to include the init map data.
                """
                with open(to, "wb") as x:
                    if include_map_data and map_data and map_data[1]:
                        x.write(map_data[1])
                    for file in via:
                        x.write(file.read_bytes())
                        x.flush()
                        if delete:
                            file.unlink()

            def decrypt(include_this_segment: bool) -> Path:
                """
                Decrypt all segments that uses the currently set DRM.

                All segments that will be decrypted with this DRM will be merged together
                in sequence, prefixed with the init data (if any), and then deleted. Once
                merged they will be decrypted. The merged and decrypted file names state
                the range of segments that were used.

                Parameters:
                    include_this_segment: Whether to include the current segment in the
                        list of segments to merge and decrypt. This should be False if
                        decrypting on EXT-X-KEY changes, or True when decrypting on the
                        last segment.

                Returns the decrypted path.
                """
                drm = encryption_data[1]
                first_segment_i = next(
                    int(file.stem)
                    for file in sorted(segment_save_dir.iterdir())
                    if file.stem.isdigit()
                )
                last_segment_i = max(0, i - int(not include_this_segment))
                range_len = (last_segment_i - first_segment_i) + 1

                segment_range = f"{str(first_segment_i).zfill(name_len)}-{str(last_segment_i).zfill(name_len)}"
                merged_path = segment_save_dir / f"{segment_range}{get_extension(master.segments[last_segment_i].uri)}"
                decrypted_path = segment_save_dir / f"{merged_path.stem}_decrypted{merged_path.suffix}"

                files = [
                    file
                    for file in sorted(segment_save_dir.iterdir())
                    if file.stem.isdigit() and first_segment_i <= int(file.stem) <= last_segment_i
                ]
                if not files:
                    raise ValueError(f"None of the segment files for {segment_range} exist...")
                elif len(files) != range_len:
                    raise ValueError(f"Missing {range_len - len(files)} segment files for {segment_range}...")

                merge(
                    to=merged_path,
                    via=files,
                    delete=True,
                    include_map_data=True
                )

                drm.decrypt(merged_path)
                merged_path.rename(decrypted_path)

                events.emit(
                    events.Types.TRACK_DECRYPTED,
                    track=track,
                    drm=drm,
                    segment=decrypted_path
                )

                return decrypted_path

            def merge_discontinuity(include_this_segment: bool, include_map_data: bool = True):
                """
                Merge all segments of the discontinuity.

                All segment files for this discontinuity must already be downloaded and
                already decrypted (if it needs to be decrypted).

                Parameters:
                    include_this_segment: Whether to include the current segment in the
                        list of segments to merge and decrypt. This should be False if
                        decrypting on EXT-X-KEY changes, or True when decrypting on the
                        last segment.
                    include_map_data: Whether to prepend the init map data before the
                        segment files when merging.
                """
                last_segment_i = max(0, i - int(not include_this_segment))

                files = [
                    file
                    for file in sorted(segment_save_dir.iterdir())
                    if int(file.stem.replace("_decrypted", "").split("-")[-1]) <= last_segment_i
                ]
                if files:
                    to_dir = segment_save_dir.parent
                    to_path = to_dir / f"{str(discon_i).zfill(name_len)}{files[-1].suffix}"
                    merge(
                        to=to_path,
                        via=files,
                        delete=True,
                        include_map_data=include_map_data
                    )

            if segment not in unwanted_segments:
                if isinstance(track, Subtitle):
                    segment_file_ext = get_extension(segment.uri)
                    segment_file_path = segment_save_dir / f"{str(i).zfill(name_len)}{segment_file_ext}"
                    segment_data = try_ensure_utf8(segment_file_path.read_bytes())
                    if track.codec not in (Subtitle.Codec.fVTT, Subtitle.Codec.fTTML):
                        segment_data = segment_data.decode("utf8"). \
                            replace("&lrm;", html.unescape("&lrm;")). \
                            replace("&rlm;", html.unescape("&rlm;")). \
                            encode("utf8")
                    segment_file_path.write_bytes(segment_data)

                if segment.discontinuity and i != 0:
                    if encryption_data:
                        decrypt(include_this_segment=False)
                    merge_discontinuity(
                        include_this_segment=False,
                        include_map_data=not encryption_data or not encryption_data[1]
                    )

                    discon_i += 1
                    range_offset = 0  # TODO: Should this be reset or not?
                    map_data = None
                    if encryption_data:
                        encryption_data = (encryption_data[0], encryption_data[1])

                if segment.init_section and (not map_data or segment.init_section != map_data[0]):
                    if segment.init_section.byterange:
                        init_byte_range = HLS.calculate_byte_range(
                            segment.init_section.byterange,
                            range_offset
                        )
                        range_offset = init_byte_range.split("-")[0]
                        init_range_header = {
                            "Range": f"bytes={init_byte_range}"
                        }
                    else:
                        init_range_header = {}

                    res = session.get(
                        url=urljoin(segment.init_section.base_uri, segment.init_section.uri),
                        headers=init_range_header
                    )
                    res.raise_for_status()
                    map_data = (segment.init_section, res.content)

            if segment.keys:
                key = HLS.get_supported_key(segment.keys)
                if encryption_data and encryption_data[0] != key and i != 0 and segment not in unwanted_segments:
                    decrypt(include_this_segment=False)

                if key is None:
                    encryption_data = None
                elif not encryption_data or encryption_data[0] != key:
                    drm = HLS.get_drm(key, session)
                    if isinstance(drm, Widevine):
                        try:
                            if map_data:
                                track_kid = track.get_key_id(map_data[1])
                            else:
                                track_kid = None
                            progress(downloaded="LICENSING")
                            license_widevine(drm, track_kid=track_kid)
                            progress(downloaded="[yellow]LICENSED")
                        except Exception:  # noqa
                            DOWNLOAD_CANCELLED.set()  # skip pending track downloads
                            progress(downloaded="[red]FAILED")
                            raise
                    encryption_data = (key, drm)

            # TODO: This wont work as we already downloaded
            if DOWNLOAD_LICENCE_ONLY.is_set():
                continue

            if is_last_segment:
                # required as it won't end with EXT-X-DISCONTINUITY nor a new key
                if encryption_data:
                    decrypt(include_this_segment=True)
                merge_discontinuity(
                    include_this_segment=True,
                    include_map_data=not encryption_data or not encryption_data[1]
                )

            progress(advance=1)

        # TODO: Again still wont work, we've already downloaded
        if DOWNLOAD_LICENCE_ONLY.is_set():
            return

        segment_save_dir.rmdir()

        # finally merge all the discontinuity save files together to the final path
        segments_to_merge = [
            x
            for x in sorted(save_dir.iterdir())
            if x.is_file()
        ]
        if len(segments_to_merge) == 1:
            shutil.move(segments_to_merge[0], save_path)
        else:
            progress(downloaded="Merging")
            if isinstance(track, (Video, Audio)):
                HLS.merge_segments(
                    segments=segments_to_merge,
                    save_path=save_path
                )
            else:
                with open(save_path, "wb") as f:
                    for discontinuity_file in segments_to_merge:
                        discontinuity_data = discontinuity_file.read_bytes()
                        f.write(discontinuity_data)
                        f.flush()
                        discontinuity_file.unlink()

        save_dir.rmdir()

        progress(downloaded="Downloaded")

        track.path = save_path
        events.emit(events.Types.TRACK_DOWNLOADED, track=track)

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

        for segment in segments:
            segment.unlink()

        return save_path.stat().st_size

    @staticmethod
    def get_supported_key(keys: list[Union[m3u8.model.SessionKey, m3u8.model.Key]]) -> Optional[m3u8.Key]:
        """
        Get a support Key System from a list of Key systems.

        Note that the key systems are chosen in an opinionated order.

        Returns None if one of the key systems is method=NONE, which means all segments
        from hence forth should be treated as plain text until another key system is
        encountered, unless it's also method=NONE.

        Raises NotImplementedError if none of the key systems are supported.
        """
        if any(key.method == "NONE" for key in keys):
            return None

        unsupported_systems = []
        for key in keys:
            if not key:
                continue
            # TODO: Add a way to specify which supported key system to use
            # TODO: Add support for 'SAMPLE-AES', 'AES-CTR', 'AES-CBC', 'ClearKey'
            elif key.method == "AES-128":
                return key
            elif key.method == "ISO-23001-7":
                return key
            elif key.keyformat and key.keyformat.lower() == WidevineCdm.urn:
                return key
            else:
                unsupported_systems.append(key.method + (f" ({key.keyformat})" if key.keyformat else ""))
        else:
            raise NotImplementedError(f"None of the key systems are supported: {', '.join(unsupported_systems)}")

    @staticmethod
    def get_drm(
        key: Union[m3u8.model.SessionKey, m3u8.model.Key],
        session: Optional[requests.Session] = None
    ) -> DRM_T:
        """
        Convert HLS EXT-X-KEY data to an initialized DRM object.

        Parameters:
            key: m3u8 key system (EXT-X-KEY) object.
            session: Optional session used to request AES-128 URIs.
                Useful to set headers, proxies, cookies, and so forth.

        Raises a NotImplementedError if the key system is not supported.
        """
        if not isinstance(session, (Session, type(None))):
            raise TypeError(f"Expected session to be a {Session}, not {type(session)}")
        if not session:
            session = Session()

        # TODO: Add support for 'SAMPLE-AES', 'AES-CTR', 'AES-CBC', 'ClearKey'
        if key.method == "AES-128":
            drm = ClearKey.from_m3u_key(key, session)
        elif key.method == "ISO-23001-7":
            drm = Widevine(
                pssh=PSSH.new(
                    key_ids=[key.uri.split(",")[-1]],
                    system_id=PSSH.SystemId.Widevine
                )
            )
        elif key.keyformat and key.keyformat.lower() == WidevineCdm.urn:
            drm = Widevine(
                pssh=PSSH(key.uri.split(",")[-1]),
                **key._extra_params  # noqa
            )
        else:
            raise NotImplementedError(f"The key system is not supported: {key}")

        return drm

    @staticmethod
    def get_all_drm(
        keys: list[Union[m3u8.model.SessionKey, m3u8.model.Key]],
        proxy: Optional[str] = None
    ) -> list[DRM_T]:
        """
        Convert HLS EXT-X-KEY data to initialized DRM objects.

        Parameters:
            keys: m3u8 key system (EXT-X-KEY) objects.
            proxy: Optional proxy string used for requesting AES-128 URIs.

        Raises a NotImplementedError if none of the key systems are supported.
        """
        unsupported_keys: list[m3u8.Key] = []
        drm_objects: list[DRM_T] = []

        if any(key.method == "NONE" for key in keys):
            return []

        for key in keys:
            try:
                drm = HLS.get_drm(key, proxy)
                drm_objects.append(drm)
            except NotImplementedError:
                unsupported_keys.append(key)

        if not drm_objects and unsupported_keys:
            raise NotImplementedError(f"None of the key systems are supported: {unsupported_keys}")

        return drm_objects

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
