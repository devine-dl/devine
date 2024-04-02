from __future__ import annotations

import html
import logging
import math
import random
import re
import shutil
import subprocess
import sys
import time
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import partial
from http.cookiejar import CookieJar, MozillaCookieJar
from itertools import product
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional
from uuid import UUID

import click
import jsonpickle
import yaml
from construct import ConstError
from pymediainfo import MediaInfo
from pywidevine.cdm import Cdm as WidevineCdm
from pywidevine.device import Device
from pywidevine.remotecdm import RemoteCdm
from rich.console import Group
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeRemainingColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from devine.core.config import config
from devine.core.console import console
from devine.core.constants import DOWNLOAD_LICENCE_ONLY, AnyTrack, context_settings
from devine.core.credential import Credential
from devine.core.drm import DRM_T, Widevine
from devine.core.events import events
from devine.core.proxies import Basic, Hola, NordVPN
from devine.core.service import Service
from devine.core.services import Services
from devine.core.titles import Movie, Song, Title_T
from devine.core.titles.episode import Episode
from devine.core.tracks import Audio, Subtitle, Tracks, Video
from devine.core.tracks.attachment import Attachment
from devine.core.utilities import get_binary_path, get_system_fonts, is_close_match, time_elapsed_since
from devine.core.utils.click_types import LANGUAGE_RANGE, QUALITY_LIST, SEASON_RANGE, ContextData, MultipleChoice
from devine.core.utils.collections import merge_dict
from devine.core.utils.subprocess import ffprobe
from devine.core.vaults import Vaults


class dl:
    @click.command(
        short_help="Download, Decrypt, and Mux tracks for titles from a Service.",
        cls=Services,
        context_settings=dict(
            **context_settings,
            default_map=config.dl,
            token_normalize_func=Services.get_tag
        ))
    @click.option("-p", "--profile", type=str, default=None,
                  help="Profile to use for Credentials and Cookies (if available).")
    @click.option("-q", "--quality", type=QUALITY_LIST, default=[],
                  help="Download Resolution(s), defaults to the best available resolution.")
    @click.option("-v", "--vcodec", type=click.Choice(Video.Codec, case_sensitive=False),
                  default=None,
                  help="Video Codec to download, defaults to any codec.")
    @click.option("-a", "--acodec", type=click.Choice(Audio.Codec, case_sensitive=False),
                  default=None,
                  help="Audio Codec to download, defaults to any codec.")
    @click.option("-vb", "--vbitrate", type=int,
                  default=None,
                  help="Video Bitrate to download (in kbps), defaults to highest available.")
    @click.option("-ab", "--abitrate", type=int,
                  default=None,
                  help="Audio Bitrate to download (in kbps), defaults to highest available.")
    @click.option("-r", "--range", "range_", type=MultipleChoice(Video.Range, case_sensitive=False),
                  default=[Video.Range.SDR],
                  help="Video Color Range(s) to download, defaults to SDR.")
    @click.option("-c", "--channels", type=float,
                  default=None,
                  help="Audio Channel(s) to download. Matches sub-channel layouts like 5.1 with 6.0 implicitly.")
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
    @click.option("--tag", type=str, default=None,
                  help="Set the Group Tag to be used, overriding the one in config if any.")
    @click.option("--sub-format", type=click.Choice(Subtitle.Codec, case_sensitive=False),
                  default=None,
                  help="Set Output Subtitle Format, only converting if necessary.")
    @click.option("-V", "--video-only", is_flag=True, default=False,
                  help="Only download video tracks.")
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
    @click.option("--workers", type=int, default=None,
                  help="Max workers/threads to download with per-track. Default depends on the downloader.")
    @click.option("--downloads", type=int, default=1,
                  help="Amount of tracks to download concurrently.")
    @click.pass_context
    def cli(ctx: click.Context, **kwargs: Any) -> dl:
        return dl(ctx, **kwargs)

    DRM_TABLE_LOCK = Lock()

    def __init__(
        self,
        ctx: click.Context,
        no_proxy: bool,
        profile: Optional[str] = None,
        proxy: Optional[str] = None,
        tag: Optional[str] = None,
        *_: Any,
        **__: Any
    ):
        if not ctx.invoked_subcommand:
            raise ValueError("A subcommand to invoke was not specified, the main code cannot continue.")

        self.log = logging.getLogger("download")

        self.service = Services.get_tag(ctx.invoked_subcommand)
        self.profile = profile

        if self.profile:
            self.log.info(f"Using profile: '{self.profile}'")

        with console.status("Loading Service Config...", spinner="dots"):
            service_config_path = Services.get_path(self.service) / config.filenames.config
            if service_config_path.exists():
                self.service_config = yaml.safe_load(service_config_path.read_text(encoding="utf8"))
                self.log.info("Service Config loaded")
            else:
                self.service_config = {}
            merge_dict(config.services.get(self.service), self.service_config)

        with console.status("Loading Widevine CDM...", spinner="dots"):
            try:
                self.cdm = self.get_cdm(self.service, self.profile)
            except ValueError as e:
                self.log.error(f"Failed to load Widevine CDM, {e}")
                sys.exit(1)
            self.log.info(
                f"Loaded {self.cdm.__class__.__name__} Widevine CDM: {self.cdm.system_id} (L{self.cdm.security_level})"
            )

        with console.status("Loading Key Vaults...", spinner="dots"):
            self.vaults = Vaults(self.service)
            for vault in config.key_vaults:
                vault_type = vault["type"]
                del vault["type"]
                self.vaults.load(vault_type, **vault)
            self.log.info(f"Loaded {len(self.vaults)} Vaults")

        self.proxy_providers = []
        if no_proxy:
            ctx.params["proxy"] = None
        else:
            with console.status("Loading Proxy Providers...", spinner="dots"):
                if config.proxy_providers.get("basic"):
                    self.proxy_providers.append(Basic(**config.proxy_providers["basic"]))
                if config.proxy_providers.get("nordvpn"):
                    self.proxy_providers.append(NordVPN(**config.proxy_providers["nordvpn"]))
                if get_binary_path("hola-proxy"):
                    self.proxy_providers.append(Hola())
                for proxy_provider in self.proxy_providers:
                    self.log.info(f"Loaded {proxy_provider.__class__.__name__}: {proxy_provider}")

            if proxy:
                requested_provider = None
                if re.match(r"^[a-z]+:.+$", proxy, re.IGNORECASE):
                    # requesting proxy from a specific proxy provider
                    requested_provider, proxy = proxy.split(":", maxsplit=1)
                if re.match(r"^[a-z]{2}(?:\d+)?$", proxy, re.IGNORECASE):
                    proxy = proxy.lower()
                    with console.status(f"Getting a Proxy to {proxy}...", spinner="dots"):
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
                            self.log.info(f"Using {proxy_provider.__class__.__name__} Proxy: {proxy}")
                        else:
                            for proxy_provider in self.proxy_providers:
                                proxy_uri = proxy_provider.get_proxy(proxy)
                                if proxy_uri:
                                    proxy = ctx.params["proxy"] = proxy_uri
                                    self.log.info(f"Using {proxy_provider.__class__.__name__} Proxy: {proxy}")
                                    break
                else:
                    self.log.info(f"Using explicit Proxy: {proxy}")

        ctx.obj = ContextData(
            config=self.service_config,
            cdm=self.cdm,
            proxy_providers=self.proxy_providers,
            profile=self.profile
        )

        if tag:
            config.tag = tag

        # needs to be added this way instead of @cli.result_callback to be
        # able to keep `self` as the first positional
        self.cli._result_callback = self.result

    def result(
        self,
        service: Service,
        quality: list[int],
        vcodec: Optional[Video.Codec],
        acodec: Optional[Audio.Codec],
        vbitrate: int,
        abitrate: int,
        range_: list[Video.Range],
        channels: float,
        wanted: list[str],
        lang: list[str],
        v_lang: list[str],
        s_lang: list[str],
        sub_format: Optional[Subtitle.Codec],
        video_only: bool,
        audio_only: bool,
        subs_only: bool,
        chapters_only: bool,
        slow: bool, list_: bool,
        list_titles: bool,
        skip_dl: bool,
        export: Optional[Path],
        cdm_only: Optional[bool],
        no_proxy: bool,
        no_folder: bool,
        no_source: bool,
        workers: Optional[int],
        downloads: int,
        *_: Any,
        **__: Any
    ) -> None:
        start_time = time.time()

        if cdm_only is None:
            vaults_only = None
        else:
            vaults_only = not cdm_only

        with console.status("Authenticating with Service...", spinner="dots"):
            cookies = self.get_cookie_jar(self.service, self.profile)
            credential = self.get_credentials(self.service, self.profile)
            service.authenticate(cookies, credential)
            if cookies or credential:
                self.log.info("Authenticated with Service")

        with console.status("Fetching Title Metadata...", spinner="dots"):
            titles = service.get_titles()
            if not titles:
                self.log.error("No titles returned, nothing to download...")
                sys.exit(1)

        console.print(Padding(
            Rule(f"[rule.text]{titles.__class__.__name__}: {titles}"),
            (1, 2)
        ))

        console.print(Padding(
            titles.tree(verbose=list_titles),
            (0, 5)
        ))
        if list_titles:
            return

        for i, title in enumerate(titles):
            if isinstance(title, Episode) and wanted and f"{title.season}x{title.number}" not in wanted:
                continue

            console.print(Padding(
                Rule(f"[rule.text]{title}"),
                (1, 2)
            ))

            if slow and i != 0:
                delay = random.randint(60, 120)
                with console.status(f"Delaying by {delay} seconds..."):
                    time.sleep(delay)

            with console.status("Subscribing to events...", spinner="dots"):
                events.reset()
                events.subscribe(events.Types.SEGMENT_DOWNLOADED, service.on_segment_downloaded)
                events.subscribe(events.Types.TRACK_DOWNLOADED, service.on_track_downloaded)
                events.subscribe(events.Types.TRACK_DECRYPTED, service.on_track_decrypted)
                events.subscribe(events.Types.TRACK_REPACKED, service.on_track_repacked)
                events.subscribe(events.Types.TRACK_MULTIPLEX, service.on_track_multiplex)

            with console.status("Getting tracks...", spinner="dots"):
                title.tracks.add(service.get_tracks(title), warn_only=True)
                title.tracks.chapters = service.get_chapters(title)

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
                    title.tracks.add(non_sdh_sub)
                    events.subscribe(
                        events.Types.TRACK_MULTIPLEX,
                        lambda track: (
                            track.strip_hearing_impaired()
                        ) if track.id == non_sdh_sub.id else None
                    )

            with console.status("Sorting tracks by language and bitrate...", spinner="dots"):
                title.tracks.sort_videos(by_language=v_lang or lang)
                title.tracks.sort_audio(by_language=lang)
                title.tracks.sort_subtitles(by_language=s_lang)

            if list_:
                available_tracks, _ = title.tracks.tree()
                console.print(Padding(
                    Panel(available_tracks, title="Available Tracks"),
                    (0, 5)
                ))
                continue

            with console.status("Selecting tracks...", spinner="dots"):
                if isinstance(title, (Movie, Episode)):
                    # filter video tracks
                    if vcodec:
                        title.tracks.select_video(lambda x: x.codec == vcodec)
                        if not title.tracks.videos:
                            self.log.error(f"There's no {vcodec.name} Video Track...")
                            sys.exit(1)

                    if range_:
                        title.tracks.select_video(lambda x: x.range in range_)
                        for color_range in range_:
                            if not any(x.range == color_range for x in title.tracks.videos):
                                self.log.error(f"There's no {color_range.name} Video Tracks...")
                                sys.exit(1)

                    if vbitrate:
                        title.tracks.select_video(lambda x: x.bitrate and x.bitrate // 1000 == vbitrate)
                        if not title.tracks.videos:
                            self.log.error(f"There's no {vbitrate}kbps Video Track...")
                            sys.exit(1)

                    video_languages = v_lang or lang
                    if video_languages and "all" not in video_languages:
                        title.tracks.videos = title.tracks.by_language(title.tracks.videos, video_languages)
                        if not title.tracks.videos:
                            self.log.error(f"There's no {video_languages} Video Track...")
                            sys.exit(1)

                    if quality:
                        title.tracks.by_resolutions(quality)
                        missing_resolutions = []
                        for resolution in quality:
                            if any(video.height == resolution for video in title.tracks.videos):
                                continue
                            if any(int(video.width * (9 / 16)) == resolution for video in title.tracks.videos):
                                continue
                            missing_resolutions.append(resolution)
                        if missing_resolutions:
                            res_list = ""
                            if len(missing_resolutions) > 1:
                                res_list = (", ".join([f"{x}p" for x in missing_resolutions[:-1]])) + " or "
                            res_list = f"{res_list}{missing_resolutions[-1]}p"
                            plural = "s" if len(missing_resolutions) > 1 else ""
                            self.log.error(f"There's no {res_list} Video Track{plural}...")
                            sys.exit(1)

                    # choose best track by range and quality
                    title.tracks.videos = [
                        track
                        for resolution, color_range in product(
                            quality or [None],
                            range_ or [None]
                        )
                        for track in [next(
                            t
                            for t in title.tracks.videos
                            if (not resolution and not color_range) or
                            (
                                (not resolution or (
                                   (t.height == resolution) or
                                   (int(t.width * (9 / 16)) == resolution)
                                ))
                                and (not color_range or t.range == color_range)
                            )
                        )]
                    ]

                    # filter subtitle tracks
                    if s_lang and "all" not in s_lang:
                        title.tracks.select_subtitles(lambda x: is_close_match(x.language, s_lang))
                        if not title.tracks.subtitles:
                            self.log.error(f"There's no {s_lang} Subtitle Track...")
                            sys.exit(1)

                    title.tracks.select_subtitles(lambda x: not x.forced or is_close_match(x.language, lang))

                # filter audio tracks
                # might have no audio tracks if part of the video, e.g. transport stream hls
                if len(title.tracks.audio) > 0:
                    title.tracks.select_audio(lambda x: not x.descriptive)  # exclude descriptive audio
                    if acodec:
                        title.tracks.select_audio(lambda x: x.codec == acodec)
                        if not title.tracks.audio:
                            self.log.error(f"There's no {acodec.name} Audio Tracks...")
                            sys.exit(1)
                    if abitrate:
                        title.tracks.select_audio(lambda x: x.bitrate and x.bitrate // 1000 == abitrate)
                        if not title.tracks.audio:
                            self.log.error(f"There's no {abitrate}kbps Audio Track...")
                            sys.exit(1)
                    if channels:
                        title.tracks.select_audio(lambda x: math.ceil(x.channels) == math.ceil(channels))
                        if not title.tracks.audio:
                            self.log.error(f"There's no {channels} Audio Track...")
                            sys.exit(1)
                    if lang and "all" not in lang:
                        title.tracks.audio = title.tracks.by_language(title.tracks.audio, lang, per_language=1)
                        if not title.tracks.audio:
                            self.log.error(f"There's no {lang} Audio Track, cannot continue...")
                            sys.exit(1)

                if video_only or audio_only or subs_only or chapters_only:
                    kept_tracks = []
                    if video_only:
                        kept_tracks.extend(title.tracks.videos)
                    if audio_only:
                        kept_tracks.extend(title.tracks.audio)
                    if subs_only:
                        kept_tracks.extend(title.tracks.subtitles)
                    if chapters_only:
                        kept_tracks.extend(title.tracks.chapters)
                    title.tracks = Tracks(kept_tracks)

            selected_tracks, tracks_progress_callables = title.tracks.tree(add_progress=True)

            download_table = Table.grid()
            download_table.add_row(selected_tracks)

            dl_start_time = time.time()

            if skip_dl:
                DOWNLOAD_LICENCE_ONLY.set()

            try:
                with Live(
                    Padding(
                        download_table,
                        (1, 5)
                    ),
                    console=console,
                    refresh_per_second=5
                ):
                    with ThreadPoolExecutor(downloads) as pool:
                        for download in futures.as_completed((
                            pool.submit(
                                track.download,
                                session=service.session,
                                prepare_drm=partial(
                                    partial(
                                        self.prepare_drm,
                                        table=download_table
                                    ),
                                    track=track,
                                    title=title,
                                    certificate=partial(
                                        service.get_widevine_service_certificate,
                                        title=title,
                                        track=track
                                    ),
                                    licence=partial(
                                        service.get_widevine_license,
                                        title=title,
                                        track=track
                                    ),
                                    cdm_only=cdm_only,
                                    vaults_only=vaults_only,
                                    export=export
                                ),
                                max_workers=workers,
                                progress=tracks_progress_callables[i]
                            )
                            for i, track in enumerate(title.tracks)
                        )):
                            download.result()
            except KeyboardInterrupt:
                console.print(Padding(
                    ":x: Download Cancelled...",
                    (0, 5, 1, 5)
                ))
                return
            except Exception as e:  # noqa
                error_messages = [
                    ":x: Download Failed...",
                    "   One of the track downloads had an error!",
                    "   See the error trace above for more information."
                ]
                if isinstance(e, subprocess.CalledProcessError):
                    # ignore process exceptions as proper error logs are already shown
                    error_messages.append(f"   Process exit code: {e.returncode}")
                else:
                    console.print_exception()
                console.print(Padding(
                    Group(*error_messages),
                    (1, 5)
                ))
                return

            if skip_dl:
                console.log("Skipped downloads as --skip-dl was used...")
            else:
                dl_time = time_elapsed_since(dl_start_time)
                console.print(Padding(
                    f"Track downloads finished in [progress.elapsed]{dl_time}[/]",
                    (0, 5)
                ))

                video_track_n = 0

                while (
                    not title.tracks.subtitles and
                    len(title.tracks.videos) > video_track_n and
                    any(
                        x.get("codec_name", "").startswith("eia_")
                        for x in ffprobe(title.tracks.videos[video_track_n].path).get("streams", [])
                    )
                ):
                    with console.status(f"Checking Video track {video_track_n + 1} for Closed Captions..."):
                        try:
                            # TODO: Figure out the real language, it might be different
                            #       EIA-CC tracks sadly don't carry language information :(
                            # TODO: Figure out if the CC language is original lang or not.
                            #       Will need to figure out above first to do so.
                            video_track = title.tracks.videos[video_track_n]
                            track_id = f"ccextractor-{video_track.id}"
                            cc_lang = title.language or video_track.language
                            cc = video_track.ccextractor(
                                track_id=track_id,
                                out_path=config.directories.temp / config.filenames.subtitle.format(
                                    id=track_id,
                                    language=cc_lang
                                ),
                                language=cc_lang,
                                original=False
                            )
                            if cc:
                                # will not appear in track listings as it's added after all times it lists
                                title.tracks.add(cc)
                                self.log.info(f"Extracted a Closed Caption from Video track {video_track_n + 1}")
                            else:
                                self.log.info(f"No Closed Captions were found in Video track {video_track_n + 1}")
                        except EnvironmentError:
                            self.log.error(
                                "Cannot extract Closed Captions as the ccextractor executable was not found..."
                            )
                            break
                    video_track_n += 1

                if sub_format:
                    with console.status(f"Converting Subtitles to {sub_format.name}..."):
                        for subtitle in title.tracks.subtitles:
                            if subtitle.codec != sub_format:
                                subtitle.convert(sub_format)

                with console.status("Checking Subtitles for Fonts..."):
                    font_names = []
                    for subtitle in title.tracks.subtitles:
                        if subtitle.codec == Subtitle.Codec.SubStationAlphav4:
                            for line in subtitle.path.read_text("utf8").splitlines():
                                if line.startswith("Style: "):
                                    font_names.append(line.removesuffix("Style: ").split(",")[1])

                    font_count = 0
                    system_fonts = get_system_fonts()
                    for font_name in set(font_names):
                        family_dir = Path(config.directories.fonts, font_name)
                        fonts_from_system = [
                            file
                            for name, file in system_fonts.items()
                            if name.startswith(font_name)
                        ]
                        if family_dir.exists():
                            fonts = family_dir.glob("*.*tf")
                            for font in fonts:
                                title.tracks.add(Attachment(font, f"{font_name} ({font.stem})"))
                                font_count += 1
                        elif fonts_from_system:
                            for font in fonts_from_system:
                                title.tracks.add(Attachment(font, f"{font_name} ({font.stem})"))
                                font_count += 1
                        else:
                            self.log.warning(f"Subtitle uses font [text2]{font_name}[/] but it could not be found...")

                    if font_count:
                        self.log.info(f"Attached {font_count} fonts for the Subtitles")

                with console.status("Repackaging tracks with FFMPEG..."):
                    has_repacked = False
                    for track in title.tracks:
                        if track.needs_repack:
                            track.repackage()
                            has_repacked = True
                            events.emit(events.Types.TRACK_REPACKED, track=track)
                    if has_repacked:
                        # we don't want to fill up the log with "Repacked x track"
                        self.log.info("Repacked one or more tracks with FFMPEG")

                muxed_paths = []

                if isinstance(title, (Movie, Episode)):
                    progress = Progress(
                        TextColumn("[progress.description]{task.description}"),
                        SpinnerColumn(finished_text=""),
                        BarColumn(),
                        "•",
                        TimeRemainingColumn(compact=True, elapsed_when_finished=True),
                        console=console
                    )

                    multiplex_tasks: list[tuple[TaskID, Tracks]] = []
                    for video_track in title.tracks.videos or [None]:
                        task_description = "Multiplexing"
                        if video_track:
                            if len(quality) > 1:
                                task_description += f" {video_track.height}p"
                            if len(range_) > 1:
                                task_description += f" {video_track.range.name}"

                        task_id = progress.add_task(f"{task_description}...", total=None, start=False)

                        task_tracks = Tracks(title.tracks) + title.tracks.chapters + title.tracks.attachments
                        if video_track:
                            task_tracks.videos = [video_track]

                        multiplex_tasks.append((task_id, task_tracks))

                    with Live(
                        Padding(progress, (0, 5, 1, 5)),
                        console=console
                    ):
                        for task_id, task_tracks in multiplex_tasks:
                            progress.start_task(task_id)  # TODO: Needed?
                            muxed_path, return_code = task_tracks.mux(
                                str(title),
                                progress=partial(progress.update, task_id=task_id),
                                delete=False
                            )
                            muxed_paths.append(muxed_path)
                            if return_code == 1:
                                self.log.warning("mkvmerge had at least one warning, will continue anyway...")
                            elif return_code >= 2:
                                self.log.error(f"Failed to Mux video to Matroska file ({return_code})")
                                sys.exit(1)
                            for video_track in task_tracks.videos:
                                video_track.delete()
                        for track in title.tracks:
                            track.delete()
                else:
                    # dont mux
                    muxed_paths.append(title.tracks.audio[0].path)

                for muxed_path in muxed_paths:
                    media_info = MediaInfo.parse(muxed_path)
                    final_dir = config.directories.downloads
                    final_filename = title.get_filename(media_info, show_service=not no_source)

                    if not no_folder and isinstance(title, (Episode, Song)):
                        final_dir /= title.get_filename(media_info, show_service=not no_source, folder=True)

                    final_dir.mkdir(parents=True, exist_ok=True)
                    final_path = final_dir / f"{final_filename}{muxed_path.suffix}"

                    shutil.move(muxed_path, final_path)

                title_dl_time = time_elapsed_since(dl_start_time)
                console.print(Padding(
                    f":tada: Title downloaded in [progress.elapsed]{title_dl_time}[/]!",
                    (0, 5, 1, 5)
                ))

            # update cookies
            cookie_file = self.get_cookie_path(self.service, self.profile)
            if cookie_file:
                self.save_cookies(cookie_file, service.session.cookies)

        dl_time = time_elapsed_since(start_time)

        console.print(Padding(
            f"Processed all titles in [progress.elapsed]{dl_time}",
            (0, 5, 1, 5)
        ))

    def prepare_drm(
        self,
        drm: DRM_T,
        track: AnyTrack,
        title: Title_T,
        certificate: Callable,
        licence: Callable,
        track_kid: Optional[UUID] = None,
        table: Table = None,
        cdm_only: bool = False,
        vaults_only: bool = False,
        export: Optional[Path] = None
    ) -> None:
        """
        Prepare the DRM by getting decryption data like KIDs, Keys, and such.
        The DRM object should be ready for decryption once this function ends.
        """
        if not drm:
            return

        if isinstance(drm, Widevine):
            with self.DRM_TABLE_LOCK:
                cek_tree = Tree(Text.assemble(
                    ("Widevine", "cyan"),
                    (f"({drm.pssh.dumps()})", "text"),
                    overflow="fold"
                ))
                pre_existing_tree = next((
                    x
                    for x in table.columns[0].cells
                    if isinstance(x, Tree) and x.label == cek_tree.label
                ), None)
                if pre_existing_tree:
                    cek_tree = pre_existing_tree

                for kid in drm.kids:
                    if kid in drm.content_keys:
                        continue

                    is_track_kid = ["", "*"][kid == track_kid]

                    if not cdm_only:
                        content_key, vault_used = self.vaults.get_key(kid)
                        if content_key:
                            drm.content_keys[kid] = content_key
                            label = f"[text2]{kid.hex}:{content_key}{is_track_kid} from {vault_used}"
                            if not any(f"{kid.hex}:{content_key}" in x.label for x in cek_tree.children):
                                cek_tree.add(label)
                            self.vaults.add_key(kid, content_key, excluding=vault_used)
                        elif vaults_only:
                            msg = f"No Vault has a Key for {kid.hex} and --vaults-only was used"
                            cek_tree.add(f"[logging.level.error]{msg}")
                            if not pre_existing_tree:
                                table.add_row(cek_tree)
                            raise Widevine.Exceptions.CEKNotFound(msg)

                    if kid not in drm.content_keys and not vaults_only:
                        from_vaults = drm.content_keys.copy()

                        try:
                            drm.get_content_keys(
                                cdm=self.cdm,
                                licence=licence,
                                certificate=certificate
                            )
                        except Exception as e:
                            if isinstance(e, (Widevine.Exceptions.EmptyLicense, Widevine.Exceptions.CEKNotFound)):
                                msg = str(e)
                            else:
                                msg = f"An exception occurred in the Service's license function: {e}"
                            cek_tree.add(f"[logging.level.error]{msg}")
                            if not pre_existing_tree:
                                table.add_row(cek_tree)
                            raise e

                        for kid_, key in drm.content_keys.items():
                            if key == "0" * 32:
                                key = f"[red]{key}[/]"
                            label = f"[text2]{kid_.hex}:{key}{is_track_kid}"
                            if not any(f"{kid_.hex}:{key}" in x.label for x in cek_tree.children):
                                cek_tree.add(label)

                        drm.content_keys = {
                            kid_: key
                            for kid_, key in drm.content_keys.items()
                            if key and key.count("0") != len(key)
                        }

                        # The CDM keys may have returned blank content keys for KIDs we got from vaults.
                        # So we re-add the keys from vaults earlier overwriting blanks or removed KIDs data.
                        drm.content_keys.update(from_vaults)

                        successful_caches = self.vaults.add_keys(drm.content_keys)
                        self.log.info(
                            f"Cached {len(drm.content_keys)} Key{'' if len(drm.content_keys) == 1 else 's'} to "
                            f"{successful_caches}/{len(self.vaults)} Vaults"
                        )
                        break  # licensing twice will be unnecessary

                if track_kid and track_kid not in drm.content_keys:
                    msg = f"No Content Key for KID {track_kid.hex} was returned in the License"
                    cek_tree.add(f"[logging.level.error]{msg}")
                    if not pre_existing_tree:
                        table.add_row(cek_tree)
                    raise Widevine.Exceptions.CEKNotFound(msg)

                if cek_tree.children and not pre_existing_tree:
                    table.add_row()
                    table.add_row(cek_tree)

                if export:
                    keys = {}
                    if export.is_file():
                        keys = jsonpickle.loads(export.read_text(encoding="utf8"))
                    if str(title) not in keys:
                        keys[str(title)] = {}
                    if str(track) not in keys[str(title)]:
                        keys[str(title)][str(track)] = {}
                    keys[str(title)][str(track)].update(drm.content_keys)
                    export.write_text(jsonpickle.dumps(keys, indent=4), encoding="utf8")

    @staticmethod
    def get_cookie_path(service: str, profile: Optional[str]) -> Optional[Path]:
        """Get Service Cookie File Path for Profile."""
        direct_cookie_file = config.directories.cookies / f"{service}.txt"
        profile_cookie_file = config.directories.cookies / service / f"{profile}.txt"
        default_cookie_file = config.directories.cookies / service / "default.txt"

        if direct_cookie_file.exists():
            return direct_cookie_file
        elif profile_cookie_file.exists():
            return profile_cookie_file
        elif default_cookie_file.exists():
            return default_cookie_file

    @staticmethod
    def get_cookie_jar(service: str, profile: Optional[str]) -> Optional[MozillaCookieJar]:
        """Get Service Cookies for Profile."""
        cookie_file = dl.get_cookie_path(service, profile)
        if cookie_file:
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

    @staticmethod
    def save_cookies(path: Path, cookies: CookieJar):
        cookie_jar = MozillaCookieJar(path)
        cookie_jar.load()
        for cookie in cookies:
            cookie_jar.set_cookie(cookie)
        cookie_jar.save(ignore_discard=True)

    @staticmethod
    def get_credentials(service: str, profile: Optional[str]) -> Optional[Credential]:
        """Get Service Credentials for Profile."""
        credentials = config.credentials.get(service)
        if credentials:
            if isinstance(credentials, dict):
                if profile:
                    credentials = credentials.get(profile) or credentials.get("default")
                else:
                    credentials = credentials.get("default")
            if credentials:
                if isinstance(credentials, list):
                    return Credential(*credentials)
                return Credential.loads(credentials)  # type: ignore

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

        try:
            device = Device.load(cdm_path)
        except ConstError as e:
            if "expected 2 but parsed 1" in str(e):
                raise ValueError(
                    f"{cdm_name}.wvd seems to be a v1 WVD file, use `pywidevine migrate --help` to migrate it to v2."
                )
            raise ValueError(f"{cdm_name}.wvd is an invalid or corrupt Widevine Device file, {e}")

        return WidevineCdm.from_device(device)
