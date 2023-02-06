from __future__ import annotations

import html
import logging
import random
import re
import sys
import time
from collections import defaultdict
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from functools import partial
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from threading import Event
from typing import Any, Optional, Callable

import click
import jsonpickle
import yaml
from pymediainfo import MediaInfo
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.device import Device
from pywidevine.remotecdm import RemoteCdm
from tqdm import tqdm

from devine.core.config import config
from devine.core.constants import AnyTrack, context_settings, LOG_FORMATTER, DRM_SORT_MAP
from devine.core.drm import Widevine, DRM_T
from devine.core.proxies import Basic, NordVPN, Hola
from devine.core.service import Service
from devine.core.services import Services
from devine.core.titles import Title_T, Movie, Song
from devine.core.titles.episode import Episode
from devine.core.tracks import Audio, Video
from devine.core.utilities import is_close_match, get_binary_path
from devine.core.utils.click_types import LANGUAGE_RANGE, QUALITY, SEASON_RANGE, ContextData
from devine.core.utils.collections import merge_dict
from devine.core.credential import Credential
from devine.core.utils.subprocess import ffprobe
from devine.core.vaults import Vaults


class dl:
    @click.group(
        short_help="Download, Decrypt, and Mux tracks for titles from a Service.",
        cls=Services,
        context_settings=dict(
            **context_settings,
            default_map=config.dl,
            token_normalize_func=Services.get_tag
        ))
    @click.option("-p", "--profile", type=str, default=None,
                  help="Profile to use for Credentials and Cookies (if available). Overrides profile set by config.")
    @click.option("-q", "--quality", type=QUALITY, default=None,
                  help="Download Resolution, defaults to best available.")
    @click.option("-v", "--vcodec", type=click.Choice(Video.Codec, case_sensitive=False),
                  default=Video.Codec.AVC,
                  help="Video Codec to download, defaults to H.264.")
    @click.option("-a", "--acodec", type=click.Choice(Audio.Codec, case_sensitive=False),
                  default=None,
                  help="Audio Codec to download, defaults to any codec.")
    @click.option("-r", "--range", "range_", type=click.Choice(Video.Range, case_sensitive=False),
                  default=Video.Range.SDR,
                  help="Video Color Range, defaults to SDR.")
    @click.option("-w", "--wanted", type=SEASON_RANGE, default=None,
                  help="Wanted episodes, e.g. `S01-S05,S07`, `S01E01-S02E03`, `S02-S02E03`, e.t.c, defaults to all.")
    @click.option("-l", "--lang", type=LANGUAGE_RANGE, default="en",
                  help="Language wanted for Video and Audio.")
    @click.option("-vl", "--v-lang", type=LANGUAGE_RANGE, default=[],
                  help="Language wanted for Video, you would use this if the video language doesn't match the audio.")
    @click.option("-sl", "--s-lang", type=LANGUAGE_RANGE, default=["all"],
                  help="Language wanted for Subtitles.")
    @click.option("--proxy", type=str, default=None,
                  help="Proxy URI to use. If a 2-letter country is provided, it will try get a proxy from the config.")
    @click.option("--group", type=str, default=None,
                  help="Set the Group Tag to be used, overriding the one in config if any.")
    @click.option("-A", "--audio-only", is_flag=True, default=False,
                  help="Only download audio tracks.")
    @click.option("-S", "--subs-only", is_flag=True, default=False,
                  help="Only download subtitle tracks.")
    @click.option("-C", "--chapters-only", is_flag=True, default=False,
                  help="Only download chapters.")
    @click.option("--slow", is_flag=True, default=False,
                  help="Add a 60-120 second delay between each Title download to act more like a real device. "
                       "This is recommended if you are downloading high-risk titles or streams.")
    @click.option("--list", "list_", is_flag=True, default=False,
                  help="Skip downloading and list available tracks and what tracks would have been downloaded.")
    @click.option("--list-titles", is_flag=True, default=False,
                  help="Skip downloading, only list available titles that would have been downloaded.")
    @click.option("--skip-dl", is_flag=True, default=False,
                  help="Skip downloading while still retrieving the decryption keys.")
    @click.option("--export", type=Path,
                  help="Export Decryption Keys as you obtain them to a JSON file.")
    @click.option("--cdm-only/--vaults-only", is_flag=True, default=None,
                  help="Only use CDM, or only use Key Vaults for retrieval of Decryption Keys.")
    @click.option("--no-proxy", is_flag=True, default=False,
                  help="Force disable all proxy use.")
    @click.option("--no-folder", is_flag=True, default=False,
                  help="Disable folder creation for TV Shows.")
    @click.option("--no-source", is_flag=True, default=False,
                  help="Disable the source tag from the output file name and path.")
    @click.option("--workers", type=int, default=1,
                  help="Max concurrent workers to use throughout the code, particularly downloads.")
    @click.option("--log", "log_path", type=Path, default=config.directories.logs / config.filenames.log,
                  help="Log path (or filename). Path can contain the following f-string args: {name} {time}.")
    @click.pass_context
    def cli(ctx: click.Context, **kwargs: Any) -> dl:
        return dl(ctx, **kwargs)

    DL_POOL_STOP = Event()

    def __init__(
        self,
        ctx: click.Context,
        log_path: Path,
        profile: Optional[str] = None,
        proxy: Optional[str] = None,
        group: Optional[str] = None,
        *_: Any,
        **__: Any
    ):
        if not ctx.invoked_subcommand:
            raise ValueError("A subcommand to invoke was not specified, the main code cannot continue.")

        self.log = logging.getLogger("download")
        if log_path:
            new_log_path = self.rotate_log_file(log_path)
            fh = logging.FileHandler(new_log_path, encoding="utf8")
            fh.setFormatter(LOG_FORMATTER)
            self.log.addHandler(fh)

        self.service = Services.get_tag(ctx.invoked_subcommand)

        self.log.info(f"Loading Profile Data for {self.service}")
        if profile:
            self.profile = profile
            self.log.info(f" + Profile: {self.profile} (explicit)")
        else:
            self.profile = self.get_profile(self.service)
            self.log.info(f" + Profile: {self.profile} (from config)")

        self.log.info("Initializing Widevine CDM")
        try:
            self.cdm = self.get_cdm(self.service, self.profile)
        except ValueError as e:
            self.log.error(f" - {e}")
            sys.exit(1)
        self.log.info(
            f" + {self.cdm.__class__.__name__}: {self.cdm.system_id} (L{self.cdm.security_level})"
        )

        self.log.info("Loading Vaults")
        self.vaults = Vaults(self.service)
        for vault in config.key_vaults:
            vault_type = vault["type"]
            del vault["type"]
            self.vaults.load(vault_type, **vault)
        self.log.info(f" + {len(self.vaults)} Vaults")

        self.log.info("Getting Service Config")
        service_config_path = Services.get_path(self.service) / config.filenames.config
        if service_config_path.is_file():
            self.service_config = yaml.safe_load(service_config_path.read_text(encoding="utf8"))
            self.log.info(" + Got Service Config")
        else:
            self.service_config = {}
            self.log.info(" - No Service Config")
        merge_dict(config.services.get(self.service), self.service_config)

        self.log.info("Loading Proxy Providers")
        self.proxy_providers = []
        if config.proxy_providers.get("basic"):
            self.proxy_providers.append(Basic(**config.proxy_providers["basic"]))
        if config.proxy_providers.get("nordvpn"):
            self.proxy_providers.append(NordVPN(**config.proxy_providers["nordvpn"]))
        if get_binary_path("hola-proxy"):
            self.proxy_providers.append(Hola())
        for proxy_provider in self.proxy_providers:
            self.log.info(f" + {proxy_provider.__class__.__name__}: {repr(proxy_provider)}")

        if proxy:
            requested_provider = None
            if re.match(rf"^[a-z]+:.+$", proxy, re.IGNORECASE):
                # requesting proxy from a specific proxy provider
                requested_provider, proxy = proxy.split(":", maxsplit=1)
            if re.match(r"^[a-z]{2}(?:\d+)?$", proxy, re.IGNORECASE):
                proxy = proxy.lower()
                self.log.info(f"Getting a Proxy to '{proxy}'")
                if requested_provider:
                    proxy_provider = next((
                        x
                        for x in self.proxy_providers
                        if x.__class__.__name__.lower() == requested_provider
                    ), None)
                    if not proxy_provider:
                        self.log.error(f"The proxy provider '{requested_provider}' was not recognised.")
                        sys.exit(1)
                    proxy_uri = proxy_provider.get_proxy(proxy)
                    if not proxy_uri:
                        self.log.error(f"The proxy provider {requested_provider} had no proxy for {proxy}")
                        sys.exit(1)
                    proxy = ctx.params["proxy"] = proxy_uri
                    self.log.info(f" + {proxy} (from {proxy_provider.__class__.__name__})")
                else:
                    for proxy_provider in self.proxy_providers:
                        proxy_uri = proxy_provider.get_proxy(proxy)
                        if proxy_uri:
                            proxy = ctx.params["proxy"] = proxy_uri
                            self.log.info(f" + {proxy} (from {proxy_provider.__class__.__name__})")
                            break
            else:
                self.log.info(f"Proxy: {proxy} (from args)")

        ctx.obj = ContextData(
            config=self.service_config,
            cdm=self.cdm,
            proxy_providers=self.proxy_providers,
            profile=self.profile
        )

        if group:
            config.tag = group

        # needs to be added this way instead of @cli.result_callback to be
        # able to keep `self` as the first positional
        self.cli._result_callback = self.result

    def result(
        self, service: Service, quality: Optional[int], vcodec: Video.Codec,
        acodec: Optional[Audio.Codec], range_: Video.Range, wanted: list[str], lang: list[str], v_lang: list[str],
        s_lang: list[str], audio_only: bool, subs_only: bool, chapters_only: bool, slow: bool, list_: bool,
        list_titles: bool, skip_dl: bool, export: Optional[Path], cdm_only: Optional[bool], no_folder: bool,
        no_source: bool, workers: int, *_: Any, **__: Any
    ) -> None:
        if cdm_only is None:
            vaults_only = None
        else:
            vaults_only = not cdm_only

        if self.profile:
            cookies = self.get_cookie_jar(self.service, self.profile)
            credential = self.get_credentials(self.service, self.profile)
            if not cookies and not credential:
                self.log.error(f"The Profile '{self.profile}' has no Cookies or Credentials. Check for typos.")
                sys.exit(1)

            self.log.info(f"Authenticating with Profile '{self.profile}'")
            service.authenticate(cookies, credential)
            self.log.info(" + Authenticated")

        self.log.info("Retrieving Titles")
        titles = service.get_titles()
        if not titles:
            self.log.error(" - No titles returned!")
            sys.exit(1)

        for line in str(titles).splitlines(keepends=False):
            self.log.info(line)

        if list_titles:
            for title in titles:
                self.log.info(title)
            return

        for i, title in enumerate(titles):
            if isinstance(title, Episode) and wanted and f"{title.season}x{title.number}" not in wanted:
                continue

            self.log.info(f"Getting tracks for {title}")
            if slow and i != 0:
                delay = random.randint(60, 120)
                self.log.info(f" - Delaying by {delay} seconds due to --slow ...")
                time.sleep(delay)

            title.tracks.add(service.get_tracks(title), warn_only=True)
            title.tracks.add(service.get_chapters(title))

            # strip SDH subs to non-SDH if no equivalent same-lang non-SDH is available
            # uses a loose check, e.g, wont strip en-US SDH sub if a non-SDH en-GB is available
            for subtitle in title.tracks.subtitles:
                if subtitle.sdh and not any(
                    is_close_match(subtitle.language, [x.language])
                    for x in title.tracks.subtitles
                    if not x.sdh and not x.forced
                ):
                    non_sdh_sub = deepcopy(subtitle)
                    non_sdh_sub.id += "_stripped"
                    non_sdh_sub.sdh = False
                    non_sdh_sub.OnDownloaded = lambda x: x.strip_hearing_impaired()
                    title.tracks.add(non_sdh_sub)

            title.tracks.sort_videos(by_language=v_lang or lang)
            title.tracks.sort_audio(by_language=lang)
            title.tracks.sort_subtitles(by_language=s_lang)
            title.tracks.sort_chapters()

            self.log.info("> All Tracks:")
            title.tracks.print()

            self.log.info("> Selected Tracks:")  # log early so errors logs make sense

            if isinstance(title, (Movie, Episode)):
                # filter video tracks
                title.tracks.select_video(lambda x: x.codec == vcodec)
                title.tracks.select_video(lambda x: x.range == range_)
                if quality:
                    title.tracks.with_resolution(quality)
                if not title.tracks.videos:
                    self.log.error(f"There's no {quality}p {vcodec.name} ({range_.name}) Video Track...")
                    sys.exit(1)

                video_language = v_lang or lang
                if video_language and "all" not in video_language:
                    title.tracks.videos = title.tracks.select_per_language(title.tracks.videos, video_language)
                    if not title.tracks.videos:
                        self.log.error(f"There's no {video_language} Video Track...")
                        sys.exit(1)

                # filter subtitle tracks
                if s_lang and "all" not in s_lang:
                    title.tracks.select_subtitles(lambda x: is_close_match(x.language, s_lang))
                    if not title.tracks.subtitles:
                        self.log.error(f"There's no {s_lang} Subtitle Track...")
                        sys.exit(1)

                title.tracks.select_subtitles(lambda x: not x.forced or is_close_match(x.language, lang))

            # filter audio tracks
            title.tracks.select_audio(lambda x: not x.descriptive)  # exclude descriptive audio
            if acodec:
                title.tracks.select_audio(lambda x: x.codec == acodec)
                if not title.tracks.audio:
                    self.log.error(f"There's no {acodec.name} Audio Tracks...")
                    sys.exit(1)

            if lang and "all" not in lang:
                title.tracks.audio = title.tracks.select_per_language(title.tracks.audio, lang)
                if not title.tracks.audio:
                    if all(x.descriptor == Video.Descriptor.M3U for x in title.tracks.videos):
                        self.log.warning(f"There's no {lang} Audio Tracks, "
                                         f"likely part of an invariant playlist, continuing...")
                    else:
                        self.log.error(f"There's no {lang} Audio Track, cannot continue...")
                        sys.exit(1)

            if audio_only or subs_only or chapters_only:
                title.tracks.videos.clear()
                if audio_only:
                    if not subs_only:
                        title.tracks.subtitles.clear()
                    if not chapters_only:
                        title.tracks.chapters.clear()
                elif subs_only:
                    if not audio_only:
                        title.tracks.audio.clear()
                    if not chapters_only:
                        title.tracks.chapters.clear()
                elif chapters_only:
                    if not audio_only:
                        title.tracks.audio.clear()
                    if not subs_only:
                        title.tracks.subtitles.clear()

            title.tracks.print()

            if list_:
                continue  # only wanted to see what tracks were available and chosen

            # Prepare Track DRM (if any)
            for track in title.tracks:
                if not track.drm and isinstance(track, (Video, Audio)):
                    # service might not list DRM in manifest, get from stream data
                    try:
                        track.drm = [Widevine.from_track(track, service.session)]
                    except Widevine.Exceptions.PSSHNotFound:
                        # it might not have Widevine DRM, or might not have found the PSSH
                        self.log.warning("No Widevine PSSH was found for this track, is it DRM free?")
                if track.drm:
                    # choose first-available DRM in order of Enum value
                    track.drm = next(iter(sorted(track.drm, key=lambda x: DRM_SORT_MAP.index(x.__class__.__name__))))
                    if isinstance(track.drm, Widevine):
                        # Get Widevine Content Keys now, this must be done in main thread due to SQLite objects
                        self.log.info(f"Getting {track.drm.__class__.__name__} Keys for: {track}")
                        self.prepare_drm(
                            drm=track.drm,
                            licence=partial(
                                service.get_widevine_license,
                                title=title,
                                track=track
                            ),
                            certificate=partial(
                                service.get_widevine_service_certificate,
                                title=title,
                                track=track
                            ),
                            cdm_only=cdm_only,
                            vaults_only=vaults_only
                        )

                        if export:
                            keys = {}
                            if export.is_file():
                                keys = jsonpickle.loads(export.read_text(encoding="utf8"))
                            if str(title) not in keys:
                                keys[str(title)] = {}
                            keys[str(title)][str(track)] = {
                                kid: key
                                for kid, key in track.drm.content_keys.items()
                                if kid in track.drm.kids
                            }
                            export.write_text(jsonpickle.dumps(keys, indent=4), encoding="utf8")

            if skip_dl:
                self.log.info("Skipping Download...")
            else:
                with tqdm(total=len(title.tracks)) as pbar:
                    with ThreadPoolExecutor(workers) as pool:
                        try:
                            for download in futures.as_completed((
                                pool.submit(
                                    self.download_track,
                                    service=service,
                                    track=track,
                                    title=title
                                )
                                for track in title.tracks
                            )):
                                if download.cancelled():
                                    continue
                                e = download.exception()
                                if e:
                                    self.DL_POOL_STOP.set()
                                    pool.shutdown(wait=False, cancel_futures=True)
                                    self.log.error(f"Download worker threw an unhandled exception: {e!r}")
                                    return
                                else:
                                    pbar.update(1)
                        except KeyboardInterrupt:
                            self.DL_POOL_STOP.set()
                            pool.shutdown(wait=False, cancel_futures=True)
                            self.log.info("Received Keyboard Interrupt, stopping...")
                            return

            if not skip_dl:
                self.mux_tracks(title, not no_folder, not no_source)

            # update cookies
            cookie_file = config.directories.cookies / service.__class__.__name__ / f"{self.profile}.txt"
            if cookie_file.exists():
                cookie_jar = MozillaCookieJar(cookie_file)
                cookie_jar.load()
                for cookie in service.session.cookies:
                    cookie_jar.set_cookie(cookie)
                cookie_jar.save(ignore_discard=True)

        self.log.info("Processed all titles!")

    def download_track(
        self,
        service: Service,
        track: AnyTrack,
        title: Title_T
    ):
        time.sleep(1)
        if self.DL_POOL_STOP.is_set():
            return

        if track.needs_proxy:
            proxy = next(iter(service.session.proxies.values()), None)
        else:
            proxy = None

        self.log.info(f"Downloading: {track}")
        track.download(config.directories.temp, headers=service.session.headers, proxy=proxy)
        if callable(track.OnDownloaded):
            track.OnDownloaded(track)

        if track.drm:
            self.log.info(f"Decrypting file with {track.drm.__class__.__name__} DRM...")
            track.drm.decrypt(track)
            self.log.info(" + Decrypted")
            if callable(track.OnDecrypted):
                track.OnDecrypted(track)

        if track.needs_repack:
            self.log.info("Repackaging stream with FFMPEG (fix malformed streams)")
            track.repackage()
            self.log.info(" + Repackaged")
            if callable(track.OnRepacked):
                track.OnRepacked(track)

        if (
            isinstance(track, Video) and
            not title.tracks.subtitles and
            any(
                x.get("codec_name", "").startswith("eia_")
                for x in ffprobe(track.path).get("streams", [])
            )
        ):
            self.log.info("Checking for EIA-CC Captions")
            try:
                # TODO: Figure out the real language, it might be different
                #       EIA-CC tracks sadly don't carry language information :(
                # TODO: Figure out if the CC language is original lang or not.
                #       Will need to figure out above first to do so.
                track_id = f"ccextractor-{track.id}"
                cc_lang = track.language
                cc = track.ccextractor(
                    track_id=track_id,
                    out_path=config.directories.temp / config.filenames.subtitle.format(
                        id=track_id,
                        language=cc_lang
                    ),
                    language=cc_lang,
                    original=False
                )
                if cc:
                    title.tracks.add(cc)
                    self.log.info(" + Found & Extracted an EIA-CC Caption")
            except EnvironmentError:
                self.log.error(" - Track needs to have CC extracted, but ccextractor wasn't found")
                sys.exit(1)
            self.log.info(" + No EIA-CC Captions...")

    def prepare_drm(
        self,
        drm: DRM_T,
        certificate: Callable,
        licence: Callable,
        cdm_only: bool = False,
        vaults_only: bool = False
    ) -> None:
        """
        Prepare the DRM by getting decryption data like KIDs, Keys, and such.
        The DRM object should be ready for decryption once this function ends.
        """
        if not drm:
            return

        if isinstance(drm, Widevine):
            self.log.info(f"PSSH: {drm.pssh.dumps()}")
            self.log.info("KIDs:")
            for kid in drm.kids:
                self.log.info(f" + {kid.hex}")

            for kid in drm.kids:
                if kid in drm.content_keys:
                    continue

                if not cdm_only:
                    content_key, vault_used = self.vaults.get_key(kid)
                    if content_key:
                        drm.content_keys[kid] = content_key
                        self.log.info(f"Content Key: {kid.hex}:{content_key} ({vault_used})")
                        add_count = self.vaults.add_key(kid, content_key, excluding=vault_used)
                        self.log.info(f" + Cached to {add_count}/{len(self.vaults) - 1} Vaults")
                    elif vaults_only:
                        self.log.error(f" - No Content Key found in vaults for {kid.hex}")
                        sys.exit(1)

                if kid not in drm.content_keys and not vaults_only:
                    from_vaults = drm.content_keys.copy()

                    try:
                        drm.get_content_keys(
                            cdm=self.cdm,
                            licence=licence,
                            certificate=certificate
                        )
                    except ValueError as e:
                        self.log.error(str(e))
                        sys.exit(1)

                    self.log.info("Content Keys:")
                    for kid_, key in drm.content_keys.items():
                        msg = f" + {kid_.hex}:{key}"
                        if kid_ == kid:
                            msg += " *"
                        if key == "0" * 32:
                            msg += " [Unusable!]"
                        self.log.info(msg)

                    drm.content_keys = {
                        kid_: key
                        for kid_, key in drm.content_keys.items()
                        if key and key.count("0") != len(key)
                    }

                    # The CDM keys may have returned blank content keys for KIDs we got from vaults.
                    # So we re-add the keys from vaults earlier overwriting blanks or removed KIDs data.
                    drm.content_keys.update(from_vaults)

                    cached_keys = self.vaults.add_keys(drm.content_keys)
                    self.log.info(f" + Newly added to {cached_keys}/{len(drm.content_keys)} Vaults")

                    if kid not in drm.content_keys:
                        self.log.error(f" - No Content Key with the KID ({kid.hex}) was returned...")
                        sys.exit(1)

    def mux_tracks(self, title: Title_T, season_folder: bool = True, add_source: bool = True) -> None:
        """Mux Tracks, Delete Pre-Mux files, and move to the final location."""
        self.log.info("Muxing Tracks into a Matroska Container")

        if isinstance(title, (Movie, Episode)):
            muxed_path, return_code = title.tracks.mux(str(title))
            if return_code == 1:
                self.log.warning("mkvmerge had at least one warning, will continue anyway...")
            elif return_code >= 2:
                self.log.error(" - Failed to Mux video to Matroska file")
                sys.exit(1)
            self.log.info(f" + Muxed to {muxed_path}")
        else:
            # dont mux
            muxed_path = title.tracks.audio[0].path

        media_info = MediaInfo.parse(muxed_path)
        final_dir = config.directories.downloads
        final_filename = title.get_filename(media_info, show_service=add_source)

        if season_folder and isinstance(title, (Episode, Song)):
            final_dir /= title.get_filename(media_info, show_service=add_source, folder=True)

        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / f"{final_filename}{muxed_path.suffix}"

        muxed_path.rename(final_path)
        self.log.info(f" + Moved to {final_path}")

    @staticmethod
    def rotate_log_file(log_path: Path, keep: int = 20) -> Path:
        """
        Update Log Filename and delete old log files.
        It keeps only the 20 newest logs by default.
        """
        if not log_path:
            raise ValueError("A log path must be provided")

        try:
            log_path.relative_to(Path(""))  # file name only
        except ValueError:
            pass
        else:
            log_path = config.directories.logs / log_path

        log_path = log_path.parent / log_path.name.format_map(defaultdict(
            str,
            name="root",
            time=datetime.now().strftime("%Y%m%d-%H%M%S")
        ))

        if log_path.parent.exists():
            log_files = [x for x in log_path.parent.iterdir() if x.suffix == log_path.suffix]
            for log_file in log_files[::-1][keep-1:]:
                # keep n newest files and delete the rest
                log_file.unlink()

        log_path.parent.mkdir(parents=True, exist_ok=True)
        return log_path

    @staticmethod
    def get_profile(service: str) -> Optional[str]:
        """Get profile for Service from config."""
        profile = config.profiles.get(service)
        if profile is False:
            return None  # auth-less service if `false` in config
        if not profile:
            profile = config.profiles.get("default")
        if not profile:
            raise ValueError(f"No profile has been defined for '{service}' in the config.")
        return profile

    @staticmethod
    def get_cookie_jar(service: str, profile: str) -> Optional[MozillaCookieJar]:
        """Get Profile's Cookies as Mozilla Cookie Jar if available."""
        cookie_file = config.directories.cookies / service / f"{profile}.txt"
        if cookie_file.is_file():
            cookie_jar = MozillaCookieJar(cookie_file)
            cookie_data = html.unescape(cookie_file.read_text("utf8")).splitlines(keepends=False)
            for i, line in enumerate(cookie_data):
                if line and not line.startswith("#"):
                    line_data = line.lstrip().split("\t")
                    # Disable client-side expiry checks completely across everywhere
                    # Even though the cookies are loaded under ignore_expires=True, stuff
                    # like python-requests may not use them if they are expired
                    line_data[4] = ""
                    cookie_data[i] = "\t".join(line_data)
            cookie_data = "\n".join(cookie_data)
            cookie_file.write_text(cookie_data, "utf8")
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
            return cookie_jar
        return None

    @staticmethod
    def get_credentials(service: str, profile: str) -> Optional[Credential]:
        """Get Profile's Credential if available."""
        cred = config.credentials.get(service, {}).get(profile)
        if cred:
            if isinstance(cred, list):
                return Credential(*cred)
            return Credential.loads(cred)
        return None

    @staticmethod
    def get_cdm(service: str, profile: Optional[str] = None) -> WidevineCdm:
        """
        Get CDM for a specified service (either Local or Remote CDM).
        Raises a ValueError if there's a problem getting a CDM.
        """
        cdm_name = config.cdm.get(service) or config.cdm.get("default")
        if not cdm_name:
            raise ValueError("A CDM to use wasn't listed in the config")

        if isinstance(cdm_name, dict):
            if not profile:
                raise ValueError("CDM config is mapped for profiles, but no profile was chosen")
            cdm_name = cdm_name.get(profile) or config.cdm.get("default")
            if not cdm_name:
                raise ValueError(f"A CDM to use was not mapped for the profile {profile}")

        cdm_api = next(iter(x for x in config.remote_cdm if x["name"] == cdm_name), None)
        if cdm_api:
            del cdm_api["name"]
            return RemoteCdm(**cdm_api)

        cdm_path = config.directories.wvds / f"{cdm_name}.wvd"
        if not cdm_path.is_file():
            raise ValueError(f"{cdm_name} does not exist or is not a file")
        device = Device.load(cdm_path)
        return WidevineCdm.from_device(device)
