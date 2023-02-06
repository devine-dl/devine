from __future__ import annotations

import re
from hashlib import md5
from typing import Union, Any, Optional

import m3u8
import requests
from langcodes import Language
from m3u8 import M3U8
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH
from requests import Session

from devine.core.drm import ClearKey, Widevine, DRM_T
from devine.core.tracks import Tracks, Video, Audio, Subtitle
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

    def to_tracks(self, language: Union[str, Language], **args: Any) -> Tracks:
        """
        Convert a Variant Playlist M3U(8) document to Video, Audio and Subtitle Track objects.

        Parameters:
            language: Language you expect the Primary Track to be in.
            args: You may pass any arbitrary named header to be passed to all requests made within
                this method.

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

            if session_drm:
                drm = session_drm
            else:
                # keys may be in the invariant playlist instead, annoying...
                res = self.session.get(url, **args)
                if not res.ok:
                    raise requests.ConnectionError(
                        "Failed to request an invariant M3U(8) document.",
                        response=res
                    )

                invariant_playlist = m3u8.loads(res.text, url)
                drm = HLS.get_drm(invariant_playlist.keys)

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
                drm=drm,
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

            if media.type == "AUDIO":
                if session_drm:
                    drm = session_drm
                else:
                    # keys may be in the invariant playlist instead, annoying...
                    res = self.session.get(url, **args)
                    if not res.ok:
                        raise requests.ConnectionError(
                            "Failed to request an invariant M3U(8) document.",
                            response=res
                        )

                    invariant_playlist = m3u8.loads(res.text, url)
                    drm = HLS.get_drm(invariant_playlist.keys)
            else:
                drm = None

            if media.type == "AUDIO":
                track_type = Audio
                codec = audio_codecs_by_group_id.get(media.group_id)
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
                drm=drm,
                extra=media,
                # audio track args
                **(dict(
                    bitrate=0,  # TODO: M3U doesn't seem to state bitrate?
                    channels=media.channels,
                    descriptive="public.accessibility.describes-video" in (media.characteristics or ""),
                ) if track_type is Audio else dict(
                    forced=media.forced == "YES",
                    sdh="public.accessibility.describes-music-and-sound" in (media.characteristics or ""),
                ) if track_type is Subtitle else {})
            ))

        return tracks

    @staticmethod
    def get_drm(keys: list[Union[m3u8.model.SessionKey, m3u8.model.Key]]) -> list[DRM_T]:
        drm = []

        for key in keys:
            if not key:
                continue
            # TODO: Add checks for Merlin, FairPlay, PlayReady, maybe more.
            if key.method.startswith("AES"):
                drm.append(ClearKey.from_m3u_key(key))
            elif key.method == "ISO-23001-7":
                drm.append(Widevine(PSSH.new(key_ids=[key.uri.split(",")[-1]], system_id=PSSH.SystemId.Widevine)))
            elif key.keyformat and key.keyformat.lower() == WidevineCdm.urn:
                drm.append(Widevine(
                    pssh=PSSH(key.uri.split(",")[-1]),
                    **key._extra_params  # noqa
                ))

        return drm


__ALL__ = (HLS,)
