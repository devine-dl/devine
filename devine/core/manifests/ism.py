from __future__ import annotations

import base64
import hashlib
import html
import urllib.parse
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional, Union

import requests
from langcodes import Language, tag_is_valid
from lxml.etree import Element
from pyplayready.system.pssh import PSSH as PR_PSSH
from pywidevine.pssh import PSSH
from requests import Session

from devine.core.constants import DOWNLOAD_CANCELLED, DOWNLOAD_LICENCE_ONLY, AnyTrack
from devine.core.drm import DRM_T, PlayReady, Widevine
from devine.core.events import events
from devine.core.tracks import Audio, Subtitle, Track, Tracks, Video
from devine.core.utilities import try_ensure_utf8
from devine.core.utils.xml import load_xml


class ISM:
    def __init__(self, manifest: Element, url: str) -> None:
        if manifest.tag != "SmoothStreamingMedia":
            raise TypeError(
                f"Expected 'SmoothStreamingMedia' document, got '{manifest.tag}'"
            )
        if not url:
            raise requests.URLRequired(
                "ISM manifest URL must be provided for relative paths"
            )
        self.manifest = manifest
        self.url = url

    @classmethod
    def from_url(
        cls, url: str, session: Optional[Session] = None, **kwargs: Any
    ) -> "ISM":
        if not url:
            raise requests.URLRequired("ISM manifest URL must be provided")
        if not session:
            session = Session()
        res = session.get(url, **kwargs)
        if res.url != url:
            url = res.url
        res.raise_for_status()
        return cls(load_xml(res.content), url)

    @classmethod
    def from_text(cls, text: str, url: str) -> "ISM":
        if not text:
            raise ValueError("ISM manifest text must be provided")
        if not url:
            raise requests.URLRequired(
                "ISM manifest URL must be provided for relative paths"
            )
        return cls(load_xml(text), url)

    @staticmethod
    def _get_drm(headers: list[Element]) -> list[DRM_T]:
        drm: list[DRM_T] = []
        for header in headers:
            system_id = (
                header.get("SystemID") or header.get("SystemId") or ""
            ).lower()
            data = "".join(header.itertext()).strip()
            if not data:
                continue
            if system_id == "edef8ba9-79d6-4ace-a3c8-27dcd51d21ed":
                try:
                    pssh = PSSH(base64.b64decode(data))
                except Exception:
                    continue
                kid = next(iter(pssh.key_ids), None)
                drm.append(Widevine(pssh=pssh, kid=kid))
            elif system_id == "9a04f079-9840-4286-ab92-e65be0885f95":
                try:
                    pr_pssh = PR_PSSH(data)
                except Exception:
                    continue
                drm.append(PlayReady(pssh=pr_pssh, pssh_b64=data))
        return drm

    def to_tracks(self, language: Optional[Union[str, Language]] = None) -> Tracks:
        tracks = Tracks()
        base_url = self.url
        duration = int(self.manifest.get("Duration") or 0)
        drm = self._get_drm(self.manifest.xpath(".//ProtectionHeader"))

        for stream_index in self.manifest.findall("StreamIndex"):
            content_type = stream_index.get("Type")
            if not content_type:
                raise ValueError("No content type value could be found")
            for ql in stream_index.findall("QualityLevel"):
                codec = ql.get("FourCC")
                if codec == "TTML":
                    codec = "STPP"
                track_lang = None
                lang = (stream_index.get("Language") or "").strip()
                if lang and tag_is_valid(lang) and not lang.startswith("und"):
                    track_lang = Language.get(lang)

                track_urls: list[str] = []
                fragment_time = 0
                fragments = stream_index.findall("c")
                for idx, frag in enumerate(fragments):
                    fragment_time = int(frag.get("t", fragment_time))
                    repeat = int(frag.get("r", 1))
                    duration_frag = int(frag.get("d") or 0)
                    if not duration_frag:
                        try:
                            next_time = int(fragments[idx + 1].get("t"))
                        except (IndexError, AttributeError):
                            next_time = duration
                        duration_frag = (next_time - fragment_time) / repeat
                    for _ in range(repeat):
                        track_urls.append(
                            urllib.parse.urljoin(
                                base_url,
                                stream_index.get("Url").format_map({
                                    "bitrate": ql.get("Bitrate"),
                                    "start time": str(fragment_time),
                                }),
                            )
                        )
                        fragment_time += duration_frag

                track_id = hashlib.md5(
                    f"{codec}-{track_lang}-{ql.get('Bitrate') or 0}-{ql.get('Index') or 0}".encode()
                ).hexdigest()

                data = {
                    "ism": {
                        "manifest": self.manifest,
                        "stream_index": stream_index,
                        "quality_level": ql,
                        "segments": track_urls,
                    }
                }

                if content_type == "video":
                    try:
                        vcodec = Video.Codec.from_mime(codec) if codec else None
                    except ValueError:
                        vcodec = None
                    tracks.add(
                        Video(
                            id_=track_id,
                            url=self.url,
                            codec=vcodec,
                            language=track_lang or language,
                            is_original_lang=language and track_lang and str(track_lang) == str(language),
                            bitrate=ql.get("Bitrate"),
                            width=int(ql.get("MaxWidth") or 0) or int(stream_index.get("MaxWidth") or 0),
                            height=int(ql.get("MaxHeight") or 0) or int(stream_index.get("MaxHeight") or 0),
                            descriptor=Video.Descriptor.ISM,
                            drm=drm,
                            data=data,
                        )
                    )
                elif content_type == "audio":
                    try:
                        acodec = Audio.Codec.from_mime(codec) if codec else None
                    except ValueError:
                        acodec = None
                    tracks.add(
                        Audio(
                            id_=track_id,
                            url=self.url,
                            codec=acodec,
                            language=track_lang or language,
                            is_original_lang=language and track_lang and str(track_lang) == str(language),
                            bitrate=ql.get("Bitrate"),
                            channels=ql.get("Channels"),
                            descriptor=Track.Descriptor.ISM,
                            drm=drm,
                            data=data,
                        )
                    )
                else:
                    try:
                        scodec = Subtitle.Codec.from_mime(codec) if codec else None
                    except ValueError:
                        scodec = None
                    tracks.add(
                        Subtitle(
                            id_=track_id,
                            url=self.url,
                            codec=scodec,
                            language=track_lang or language,
                            is_original_lang=language and track_lang and str(track_lang) == str(language),
                            descriptor=Track.Descriptor.ISM,
                            drm=drm,
                            data=data,
                        )
                    )
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
        license_widevine: Optional[Callable] = None,
        *,
        cdm: Optional[object] = None,
    ) -> None:
        if not session:
            session = Session()
        elif not isinstance(session, Session):
            raise TypeError(f"Expected session to be a {Session}, not {session!r}")

        if proxy:
            session.proxies.update({"all": proxy})

        segments: list[str] = track.data["ism"]["segments"]

        session_drm = None
        if track.drm:
            session_drm = track.get_drm_for_cdm(cdm)
            if isinstance(session_drm, Widevine):
                try:
                    if not license_widevine:
                        raise ValueError("license_widevine func must be supplied to use Widevine DRM")
                    progress(downloaded="LICENSING")
                    license_widevine(session_drm)
                    progress(downloaded="[yellow]LICENSED")
                except Exception:
                    DOWNLOAD_CANCELLED.set()
                    progress(downloaded="[red]FAILED")
                    raise

        if DOWNLOAD_LICENCE_ONLY.is_set():
            progress(downloaded="[yellow]SKIPPED")
            return

        progress(total=len(segments))

        downloader = track.downloader
        downloader_args = dict(
            urls=[{"url": url} for url in segments],
            output_dir=save_dir,
            filename="{i:0%d}.mp4" % len(str(len(segments))),
            headers=session.headers,
            cookies=session.cookies,
            proxy=proxy,
            max_workers=max_workers,
        )

        if downloader.__name__ == "n_m3u8dl_re":
            downloader_args.update(
                {
                    "filename": track.id,
                    "track": track,
                    "content_keys": session_drm.content_keys if session_drm else None,
                }
            )

        for status_update in downloader(**downloader_args):
            file_downloaded = status_update.get("file_downloaded")
            if file_downloaded:
                events.emit(events.Types.SEGMENT_DOWNLOADED, track=track, segment=file_downloaded)
            else:
                downloaded = status_update.get("downloaded")
                if downloaded and downloaded.endswith("/s"):
                    status_update["downloaded"] = f"ISM {downloaded}"
                progress(**status_update)

        for control_file in save_dir.glob("*.aria2__temp"):
            control_file.unlink()

        segments_to_merge = [x for x in sorted(save_dir.iterdir()) if x.is_file()]
        with open(save_path, "wb") as f:
            for segment_file in segments_to_merge:
                segment_data = segment_file.read_bytes()
                if (
                    not session_drm
                    and isinstance(track, Subtitle)
                    and track.codec not in (Subtitle.Codec.fVTT, Subtitle.Codec.fTTML)
                ):
                    segment_data = try_ensure_utf8(segment_data)
                    segment_data = (
                        segment_data.decode("utf8")
                        .replace("&lrm;", html.unescape("&lrm;"))
                        .replace("&rlm;", html.unescape("&rlm;"))
                        .encode("utf8")
                    )
                f.write(segment_data)
                f.flush()
                segment_file.unlink()
                progress(advance=1)

        track.path = save_path
        events.emit(events.Types.TRACK_DOWNLOADED, track=track)

        if session_drm:
            progress(downloaded="Decrypting", completed=0, total=100)
            session_drm.decrypt(save_path)
            track.drm = None
            events.emit(events.Types.TRACK_DECRYPTED, track=track, drm=session_drm, segment=None)
            progress(downloaded="Decrypting", advance=100)

        save_dir.rmdir()
        progress(downloaded="Downloaded")


__all__ = ("ISM",)
