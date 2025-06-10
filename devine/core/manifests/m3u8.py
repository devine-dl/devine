"""Utility functions for parsing M3U8 playlists."""

from __future__ import annotations

from typing import Optional, Union

import m3u8
from pyplayready.cdm import Cdm as PlayReadyCdm
from pyplayready.system.pssh import PSSH as PR_PSSH
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.pssh import PSSH as WV_PSSH
from requests import Session

from devine.core.drm import PlayReady, Widevine
from devine.core.manifests.hls import HLS
from devine.core.tracks import Tracks


def parse(
    master: m3u8.M3U8,
    language: str,
    *,
    session: Optional[Union[Session]] = None,
) -> Tracks:
    """Parse a variant playlist to ``Tracks`` with DRM information."""
    tracks = HLS(master, session=session).to_tracks(language)

    need_wv = not any(
        isinstance(d, Widevine) for t in tracks for d in (t.drm or [])
    )
    need_pr = not any(
        isinstance(d, PlayReady) for t in tracks for d in (t.drm or [])
    )

    if (need_wv or need_pr) and tracks.videos:
        if not session:
            session = Session()

        session_keys = list(master.session_keys or [])
        session_keys.extend(HLS.parse_session_data_keys(master, session))

        for drm_obj in HLS.get_all_drm(session_keys):
            if need_wv and isinstance(drm_obj, Widevine):
                for t in tracks.videos + tracks.audio:
                    t.drm = [d for d in (t.drm or []) if not isinstance(d, Widevine)] + [drm_obj]
                need_wv = False
            elif need_pr and isinstance(drm_obj, PlayReady):
                for t in tracks.videos + tracks.audio:
                    t.drm = [d for d in (t.drm or []) if not isinstance(d, PlayReady)] + [drm_obj]
                need_pr = False
            if not need_wv and not need_pr:
                break

    if (need_wv or need_pr) and tracks.videos:
        first_video = tracks.videos[0]
        playlist = m3u8.load(first_video.url)
        for key in playlist.keys or []:
            if not key or not key.keyformat:
                continue
            fmt = key.keyformat.lower()
            if need_wv and fmt == WidevineCdm.urn:
                pssh_b64 = key.uri.split(",")[-1]
                drm = Widevine(pssh=WV_PSSH(pssh_b64))
                for t in tracks.videos + tracks.audio:
                    t.drm = [d for d in (t.drm or []) if not isinstance(d, Widevine)] + [drm]
                need_wv = False
            elif need_pr and (
                fmt == PlayReadyCdm or "com.microsoft.playready" in fmt
            ):
                pssh_b64 = key.uri.split(",")[-1]
                drm = PlayReady(pssh=PR_PSSH(pssh_b64), pssh_b64=pssh_b64)
                for t in tracks.videos + tracks.audio:
                    t.drm = [d for d in (t.drm or []) if not isinstance(d, PlayReady)] + [drm]
                need_pr = False
            if not need_wv and not need_pr:
                break

    return tracks

__all__ = ["parse"]
