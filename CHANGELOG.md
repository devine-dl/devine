# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions [3.0.0] and older use a format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
but versions thereafter use a custom changelog format using [git-cliff](https://git-cliff.org).

## [3.3.1] - 2024-04-05

### Features

- *dl*: Add *new* --workers to set download threads/workers

### Bug Fixes

- *Chapter*: Cast values to int prior to formatting
- *requests*: Fix multithreaded downloads
- *Events*: Dereference subscription store from ephemeral store

### Changes

- *dl*: Change --workers to --downloads

### New Contributors

- [knowhere01](https://github.com/knowhere01)

## [3.3.0] - 2024-04-02

### Features

- Add support for MKV Attachments via Attachment class
- *dl*: Automatically attach fonts used within SSAv4 subs
- *dl*: Try find SSAv4 fonts in System OS fonts folder
- *Basic*: Allow single string URIs for countries
- *Basic*: Allow proxy selection by index (one-indexed)
- *Events*: Add new global Event Observer API

### Bug Fixes

- *curl-impersonate*: Set Cert-Authority Bundle for HTTPS Proxies
- *Basic*: Make query case-insensitive
- *WVD*: Ensure WVDs dir exists before moving WVD file
- *WVD*: Fix empty path to WVDs folder check
- *WVD*: Move log out of loop to save performance
- *WVD*: Move log with path before Device load
- *WVD*: Add exists/empty checks to WVD folder dumps
- *Basic*: Fix variable typo regression

### Changes

- *Basic*: Improve proxy format checks
- *WVD*: Print error if path to parse doesn't exist
- *WVD*: Seperate logs in loop for visual clarity
- *Track*: Move from OnXyz callables to Event observer

## [3.2.0] - 2024-03-25

### Features

- *ClearKey*: Pass session not proxy str in from_m3u_key method
- *Track*: Allow Track to choose downloader to use
- *search*: New Search command, Service method, SearchResult Class

### Bug Fixes

- *dl*: Include chapters when muxing
- *aria2c*: Support aria2(c) 1.37.0 by handling upstream regression
- *MultipleChoice*: Simplify super() call and value types
- *dl*: Add single mux job if there's no video tracks
- *Track*: Compute Track ID from the `this` variable, not `self`
- *DASH/HLS*: Don't merge folders, skip final merge if only 1 segment
- *dl*: Use click.command() instead of click.group()
- *HLS*: Remove save dir even if final merge wasn't needed
- *Track*: Fix order of operation mistake in get_track_name
- *requests*: Set HTTP pool connections/maxsize to max workers
- *Video*: Delete original file after using change_color_range()
- *Video*: Delete original file after using remove_eia_cc()
- *requests*: Manually compute default max_workers or pool size is None
- *requests*: Block until connection freed if too many connections
- *HLS*: Delete subtitle segments as they are merged
- *HLS*: Delete video/audio segments after FFmpeg merge

### Changes

- *ClearKey*: Only use User-Agent if none set in from_m3u_key
- *Track*: Remove TERRITORY_MAP constant, trim SAR China manually
- *Track*: Default the track name to it's lang's script/territory
- *Service*: Go back to the default pool_maxsize in Session

## [3.1.0] - 2024-03-05

### Features

- *cli*: Implement MultipleChoice click param based on Choice param
- *dl*: Skip video lang filter if --v-lang unused & only 1 video lang
- *dl*: Change --vcodec default to None, use any codec
- *dl*: Support multiple -r/--range and mux ranges separately
- *Subtitle*: Convert from fTTML->TTML & fVTT->WebVTT post-download
- *Track*: Make ID optional, Automatically compute one if not provided
- *Track*: Add a name property to use for the Track Name

### Bug Fixes

- *dl*: Have --sub-format default to None to keep original sub format
- *HLS*: Use filtered out segment key info
- *Track*: Don't modify lang when getting name
- *Track*: Don't use fallback values "Zzzz"/"ZZ" for track name
- *version*: The `__version__` variable forgot to be updated

### Changes

- Move dl command's download_track() to Track.download()
- *dl*: Remove unused `get_profiles()` method
- *DASH*: Move data values from track url to track data property
- *DASH*: Change how Video FPS is gotten to remove FutureWarning log
- *Track*: Add type checks, improve typing
- *Track*: Remove swap() method and it's uses
- *Track*: Remove unused DRM enum
- *Track*: Rename Descriptor's M3U & MPD to HLS & DASH
- *Track*: Remove unnecessary bool casting
- *Track*: Move the path class instance variable with the rest
- *Track*: Return new path on move(), raise exceptions on errors
- *Track*: Move delete and move methods near start of Class
- *Track*: Rename extra to data, enforce type as dict

### Builds

- Explicitly use marisa-trie==1.1.0 for Python 3.12 wheels

## [3.0.0] - 2024-03-01

### Added

- Support for Python 3.12.
- Audio track's Codec Enum now has [FLAC](https://en.wikipedia.org/wiki/FLAC) defined.
- The Downloader to use can now be set in the config under the [downloader key](CONFIG.md#downloader-str).
- New Multi-Threaded Downloader, `requests`, that makes HTTP(S) calls using [Python-requests](https://requests.readthedocs.io).
- New Multi-Threaded Downloader, `curl_impersonate`, that makes HTTP(S) calls using [Curl-Impersonate](https://github.com/yifeikong/curl-impersonate) via [Curl_CFFI](https://github.com/yifeikong/curl_cffi).
- HLS manifests specifying a Byte range value without starting offsets are now supported.
- HLS segments that use `EXT-X-DISCONTINUITY` are now supported.
- DASH manifests with SegmentBase or only BaseURL are now supported.
- Subtitle tracks from DASH manifests now automatically marked as SDH if `urn:tva:metadata:cs:AudioPurposeCS:2007 = 2`.
- The `--audio-only/--subs-only/--chapters-only` flags can now be used simultaneously. For example, `--subs-only`
  with `--chapters-only` will get just Subtitles and Chapters.
- Added `--video-only` flag, which can also still be simultaneously used with the only "only" flags. Using all four
  of these flags will have the same effect as not using any of them.
- Added `--no-proxy` flag, disabling all uses of proxies, even if `--proxy` is set.
- Added `--sub-format` option, which sets the wanted output subtitle format, defaulting to SubRip (SRT).
- Added `Subtitle.reverse_rtl()` method to use SubtitleEdit's `/ReverseRtlStartEnd` functionality.
- Added `Subtitle.convert()` method to convert the loaded Subtitle to another format. Note that you cannot convert to
  fTTML or fVTT, but you can convert from them. SubtitleEdit will be used in precedence over pycaption if available.
  Converting to SubStationAlphav4 requires SubtitleEdit, but you may want to manually alter the Canvas resolution after
  the download.
- Added support for SubRip (SRT) format subtitles in `Subtitle.parse()` via pycaption.
- Added `API` Vault Client aiming for a RESTful like API.
- Added `Chapters` Class to hold the new reworked `Chapter` objects, automatically handling stuff like order of the
  Chapters, Chapter numbers, loading from a chapter file or string, and saving to a chapter file or string.
- Added new `chapter_fallback_name` config option allowing you to set a Chapter Name Template used when muxing Chapters
  into an MKV Container with MKVMerge. Do note, it defaults to no Chapter Fallback Name at all, but MKVMerge will force
  `Chapter {i:02}` at least for me on Windows with the program language set to English. You may want to instead use
  `Chapter {j:02}` which will do `Chapter 01, Intro, Chapter 02` instead of `Chapter 01, Intro, Chapter 03` (an Intro
  is not a Chapter of story, but it is the 2nd Chapter marker, so It's up to you how you want to interpret it).
- Added new `Track.OnSegmentDownloaded` Event, called any time one of the Track's segments were downloaded.
- Added new `Subtitle.OnConverted` Event, called any time that Subtitle is converted.
- Implemented `__add__` method to `Tracks` class, allowing you to add to the first Tracks object. For example, making
  it handy to merge HLS video tracks with DASH tracks, `tracks = dash_tracks + hls_tracks.videos`, or for iterating:
  `for track in dash.videos + hls.videos: ...`.
- Added new utility `get_free_port()` to get a free local port to use, though it may be taken by the time it's used.

### Changed

- Moved from my forked release of pymp4 (`rlaphoenix-pymp4`) back to the original `pymp4` release as it is
  now up-to-date with some of my needed fixes.
- The DASH manifest is now stored in the Track `url` property to be reused by `DASH.download_track()`.
- Encrypted DASH streams are now downloaded in full and then decrypted, instead of downloading and decrypting
  each individual segment. Unlike HLS, DASH cannot dynamically switch out the DRM/Protection information.
  This brings both CPU and Disk IOPS improvements, as well as fixing rare weird decryption anomalies like broken
  or odd timestamps, decryption failures, or broken a/v continuity.
- When a track is being decrypted, it now displays "Decrypting" and afterward "Decrypted" in place of the download
  speed.
- When a track finishes downloaded, it now displays "Downloaded" in place of the download speed.
- When licensing is needed and fails, the track will display "FAILED" in place of the download speed. The track
  download will cancel and all other track downloads will be skipped/cancelled; downloading will end.
- The fancy smart quotes (`“` and `”`) are now stripped from filenames.
- All available services are now listed if you provide an invalid service tag/alias.
- If a WVD file fails to load and looks to be in the older unsupported v1 format, then instructions on migrating to
  v2 will be displayed.
- If Shaka-Packager prints an error (i.e., `:ERROR:` log message) it will now raise a `subprocess.CalledProcessError`
  exception, even if the process return code is 0.
- The Video classes' Primaries, Transfer, and Matrix classes had changes to their enum names to better represent their
  values and uses. See the changed names in the [commit](https://github.com/devine-dl/devine/commit/c159672181ee3bd07b06612f256fa8590d61795c).
- SubRip (SRT) Subtitles no longer have the `MULTI-LANGUAGE SRT` header forcefully removed. The root cause of the error
  was identified and fixed in this release.
- Since `Range.Transfer.SDR_BT_601_625 = 5` has been removed, `Range.from_cicp()` now internally remaps CICP transfer
  values of `5` to `6` (which is now `Range.Transfer.BT_601 = 6`).
- Referer and User-Agent Header values passed to the aria2(c) downloader is now set via the dedicated `--referer` and
  `--user-agent` options respectively, instead of `--header`.
- The aria2(c) `-j`, `-x`, and `-s` option values can now be set by the config under the `aria2c` key in the options'
  full names.
- The aria2(c) `-x`, and `-s` option values now use aria2(c)'s own default values for them instead of `16`. The `j`
  option value defaults to ThreadPoolExecutor's algorithm of `min(32,(cpu_count+4))`.
- The download progress bar now states `LICENSING` on the speed text when licensing DRM, and `LICENSED` once finished.
- The download progress bar now states `CANCELLING`/`CANCELLED` on the speed text when cancelling downloads. This is to
  make it more clear that it didn't just stop, but stopped as it was cancelled.
- The download cancel/skip events were moved to `constants.py` so it can be used across the codebase easier without
  argument drilling. `DL_POOL_STOP` was renamed to `DOWNLOAD_CANCELLED` and `DL_POOL_SKIP` to `DOWNLOAD_LICENCE_ONLY`.
- The Cookie header is now calculated for each URL passed to the aria2(c) downloader based on the URL. Instead of
  passing every single cookie, which could have two cookies with the same name aimed for different host names, we now
  pass only cookies intended for the URL.
- The aria2(c) process no longer prints output to the terminal directly. Devine now only prints contents of the
  captured log messages to the terminal. This allows filtering out of errors and warnings that isn't a problem.
- DASH and HLS no longer download segments silencing errors on all but the last retry as the downloader rework makes
  this unnecessary. The errors will only be printed on the final retry regardless.
- `Track.repackage()` now saves as `{name}_repack.{ext}` instead of `{name}.repack.{ext}`.
- `Video.change_color_range()` now saves as `{name}_{limited|full}_range.{ext}` instead of `{name}.range{0|1}.{ext}`.
- `Widevine.decrypt()` now saves as `{name}_decrypted.{ext}` instead of `{name}.decrypted.{ext}`.
- Files starting with the save path's name and using the save path's extension, but not the save path, are no longer
  deleted on download finish/stop/failure.
- The output container format is now explicitly specified as `MP4` when calling `shaka-packager`.
- The default downloader is now `requests` instead of `aria2c` to reduce required external dependencies.
- Reworked the `Chapter` class to only hold a timestamp and name value with an ID automatically generated as a CRC32 of
  the Chapter representation.
- The `--group` option has been renamed to `--tag`.
- The config file is now read from three more locations in the following order:
  1) The Devine Namespace Folder (e.g., `%appdata%/Python/Python311/site-packages/devine/devine.yaml`).
  2) The Parent Folder to the Devine Namespace Folder (e.g., `%appdata%/Python/Python311/site-packages/devine.yaml`).
  3) The AppDirs User Config Folder (e.g., `%localappdata%/devine/devine.yaml`).
  Location 2 allows having a config at the root of a portable folder.
- An empty config file is no longer created when no config file is found.
- You can now set a default cookie file for a Service, [see README](README.md#cookies--credentials).
- You can now set a default credential for a Service, [see config](CONFIG.md#credentials-dictstr-strlistdict).
- Services are now auth-less by default and the error for not having at least a cookie or credential is removed.
  Cookies/Credentials will only be loaded if a default one for the service is available, or if you use `-p/--profile`
  and the profile exists.
- Subtitles when converting to SubRip (SRT) via SubtitleEdit will now use the `/ConvertColorsToDialog` option.
- HLS segments are now merged by discontinuity instead of all at once. The merged discontinuities are then finally
  merged to one file using `ffmpeg`. Doing the final merge by byte concatenation did not work for some playlists.
- The Track is no longer passed through Event Callables. If you are able to set a function on an Even Callable, then
  you should have access to the track reference to call it directly if needed.
- The Track.OnDecrypted event callable is now passed the DRM and Segment objects used to Decrypt. The segment object is
  only passed from HLS downloads.
- The Track.OnDownloaded event callable is now called BEFORE decryption, right after downloading, not after decryption.
- All generated Track ID values across the codebase has moved from md5 to crc32 values as code processors complain
  about its use surrounding security, and it's length is too large for our use case anyway.
- HLS segments are now downloaded multi-threaded first and then processed in sequence thereafter.
- HLS segments are no longer decrypted one-by-one, requiring a lot of shaka-packager processes to run and close.
  They now merged and decrypt in groups based on their EXT-X-KEY, before being merged per discontinuity.
- The DASH and HLS downloaders now pass multiple URLs to the downloader instead of one-by-one, heavily increasing speed
  and reliability as connections are kept alive and re-used.
- Downloaders now yield back progress information in the same convention used by `rich`'s `Progress.update()` method.
  DASH and HLS now pass the yielded information to their progress callable instead of passing the progress callable to
  the downloader.
- The aria2(c) downloader now uses the aria2(c) JSON-RPC interface to query for download progress updates instead of
  parsing the stdout data in an extremely hacky way.
- The aria2(c) downloader now re-routes non-HTTP proxies via `pproxy` by a subprocess instead of the now-removed
  `start_pproxy` utility. This way has proven to be easier, more reliable, and prevents pproxy from messing with rich's
  terminal output in strange ways.
- All downloader function's have an altered signature but ultimately similar. `uri` to `urls`, `out` (path) was removed,
  we now calculate the save path by passing an `output_dir` and `filename`. The `silent`, `segmented`, and `progress`
  parameters were completely removed.
- All downloader `urls` can now be a string or a dictionary containing extra URL-specific options to use like
  URL-specific headers. It can also be a list of the two types of URLs to downloading multi-threaded.
- All downloader `filenames` can be a static string, or a filename string template with a few variables to use. The
  template system used is f-string, e.g., `"file_{i:03}{ext}"` (ext starts with `.` if there's an extension).
- DASH now updates the progress bar when merging segments.
- The `Widevine.decrypt()` method now also searches for shaka-packager as just `packager` as it is the default build
  name. (#74)

### Removed

- The `devine auth` command and sub-commands due to lack of support, risk of data, and general quirks with it.
- Removed `profiles` config, you must now specify which profile you wish to use each time with `-p/--profile`. If you
  use a specific profile a lot more than others, you should make it the default.
- The `saldl` downloader has been removed as their binary distribution is whack and development has seemed to stall.
  It was only used as an alternative to what was at the time the only downloader, aria2(c), as it did not support any
  form of Byte Range, but `saldl` did, which was crucial for resuming extremely large downloads or complex playlists.
  However, now we have the requests downloader which does support the Range header.
- The `Track.needs_proxy` property was removed for a few design architectural reasons.
  1) Design-wise it isn't valid to have --proxy (or via config/otherwise) set a proxy, then unpredictably have it
     bypassed or disabled. If I specify `--proxy 127.0.0.1:8080`, I would expect it to use that proxy for all
     communication indefinitely, not switch in and out depending on the track or service.
  2) With reason 1, it's also a security problem. The only reason I implemented it in the first place was so I could
     download faster on my home connection. This means I would authenticate and call APIs under a proxy, then suddenly
     download manifests and segments e.t.c under my home connection. A competent service could see that as an indicator
     of bad play and flag you.
  3) Maintaining this setup across the codebase is extremely annoying, especially because of how proxies are setup/used
     by Requests in the Session. There's no way to tell a request session to temporarily disable the proxy and turn it
     back on later, without having to get the proxy from the session (in an annoying way) store it, then remove it,
     make the calls, then assuming your still in the same function you can add it back. If you're not in the same
     function, well, time for some spaghetti code.
- The `Range.Transfer.SDR_BT_601_625 = 5` key and value has been removed as I cannot find any official source to verify
  it as the correct use. However, usually a `transfer` value of `5` would be PAL SD material so it better matches `6`,
  which is (now named) `Range.Transfer.BT_601 = 6`. If you have something specifying transfer=5, just remap it to 6.
- The warning log `There's no ... Audio Tracks, likely part of an invariant playlist, continuing...` message has been
  removed. So long as your playlist is expecting no audio tracks, or the audio is part of the video transport, then
  this wouldn't be a problem whatsoever. Therefore, having it log this annoying warning all the time is pointless.
- The `--min-split-size` argument to the aria2(c) downloader as it was only used to disable splitting on
  segmented downloads, but the newer downloader system wouldn't really need or want this to be done. If aria2 has
  decided based on its other settings to have split a segment file, then it likely would benefit from doing so.
- The `--remote-time` argument from the aria2(c) downloader as it may need to do a GET and a HEAD request to
  get the remote time information, slowing the download down. We don't need this information anyway as it will likely
  be repacked with `ffmpeg` or multiplexed with `mkvmerge`, discarding/losing that information.
- DASH and HLS's 5-attempt retry loop as the downloaders will retry for us.
- The `start_pproxy` utility has been removed as all uses of it now call `pproxy` via subprocess instead.
- The `LANGUAGE_MUX_MAP` constant and it's usage has been removed as it is no longer necessary as of MKVToolNix v54.

### Fixed

- Uses of `__ALL__` with Class objects have been correct to `__all__` with string objects, following PEP8.
- Fixed value of URL passed to `Track.get_key_id()` as it was a tuple rather than the URL string.
- The `--skip-dl` flag now works again after breaking in v[1.3.0].
- Move WVD file to correct location on new installations in the `wvd add` command.
- Cookie data is now passed to downloaders and use URLs based on the URI it will be used for, just like a browser.
- Failure to get FPS in DASH when SegmentBase isn't used.
- An error message is now returned if a WVD file fails to load instead of raising an exception.
- Track language information within M3U playlists are now validated with langcodes before use. Some manifests use the
  property for arbitrary data that their apps/players use for their own purposes.
- Attempt to fix non-UTF-8 and mixed-encoding Subtitle downloads by automatically converting to UTF-8. (#43)
  Decoding is attempted in the following order: UTF-8, CP-1252, then finally chardet detection. If it's neither UTF-8
  nor CP-1252 and chardet could not detect the encoding, then it is left as-is. Conversion is done per-segment if the
  Subtitle is segmented, unless it's the fVTT or fTTML formats which are binary.
- Chapter Character Encoding is now explicitly set to UTF-8 when muxing to an MKV container as Windows seems to default
  to latin1 or something, breaking Chapter names with any sort of special character within.
- Subtitle passed through SubtitleEdit now explicitly use UTF-8 character encoding as it usually defaulted to UTF-8
  with Byte Order Marks (aka UTF-8-SIG/UTF-8-BOM).
- Subtitles passed through SubtitleEdit now use the same output format as the subtitle being processed instead of SRT.
- Fixed rare infinite loop when the Server hosting the init/header data/segment file responds with a `Content-Length`
  header with a value of `0` or smaller.
- Removed empty caption lists/languages when parsing Subtitles with `Subtitle.parse()`. This stopped conversions to SRT
  containing the `MULTI-LANGUAGE SRT` header when there was multiple caption lists, even though only one of them
  actually contained captions.
- Text-based Subtitle formats now try to automatically convert to UTF-8 when run through `Subtitle.parse()`.
- Text-based Subtitle formats now have `&lrm;` and `&rlm;` HTML entities unescaped post-download as some rendering
  libraries seems to not decode them for us. SubtitleEdit also has problems with `/ReverseRtlStartEnd` unless it's
  already decoded.
- Fixed two concatenation errors surrounding DASH's BaseURL, sourceURL, and media values that start with or use `../`.
- Fixed the number values in the `Newly added to x/y Vaults` log, which now states `Cached n Key(s) to x/y Vaults`.
- File write handler now flushes after appending a new segment to the final save path or checkpoint file, reducing
  memory usage by quite a bit in some scenarios.

### New Contributors

- [Shivelight](https://github.com/Shivelight)

## [2.2.0] - 2023-04-23

### Breaking Changes

Since `-q/--quality` has been reworked to support specifying multiple qualities, the type of this value is
no longer `None|int`. It is now `list[int]` and the list may be empty. It is no longer ever a `None` value.

Please make sure any Service code that uses `quality` via `ctx.parent.params` reflects this change. You may
need to go from an `if quality: ...` to `for res in quality: ...`, or such. You may still use `if quality`
to check if it has 1 or more resolution specified, but make sure that the code within that if tree supports
more than 1 value in the `quality` variable, which is now a list. Note that the list will always be in
descending order regardless of how the user specified them.

### Added

- Added the ability to specify and download multiple resolutions with `-q/--quality`. E.g., `-q 1080p,720p`.
- Added support for DASH manifests that use SegmentList with range values on the Initialization definition (#47).
- Added a check for `uuid` mp4 boxes containing `tenc` box data when getting the Track's Key ID to improve
  chances of finding a Key ID.

### Changed

- The download path is no longer printed after each download. The simple reason is it felt unnecessary.
  It filled up a fair amount of vertical space for information you should already know.
- The logs after a download finishes has been split into two logs. One after the actual downloading process
  and the other after the multiplexing process. The downloading process has its own timer as well, so you can
  see how long the downloads itself took.
- I've switched from using the official pymp4 (for now) with my fork. At the time this change was made the
  original bearypig pymp4 repo was stagnant and the PyPI releases were old. I forked it, added some fixes
  by TrueDread and released my own update to PyPI, so it's no longer outdated. This was needed for some
  mp4 box parsing fixes. Since then the original repo is no longer stagnant, and a new release was made on
  PyPI. However, my repo still has some of TrueDread's fixes that is not yet on the original repository nor
  on PyPI.

### Removed

- Removed the `with_resolution` method in the Tracks class. It has been replaced with `by_resolutions`. The
  new replacement method supports getting all or n amount of tracks by resolution instead of the original
  always getting all tracks by resolution.
- Removed the `select_per_language` method in the Tracks class. It has been replaced with `by_language`. The
  new replacement method supports getting all or n amount of tracks by language instead of the original only
  able to get one track by language. It now defaults to getting all tracks by language.

### Fixed

- Prevented some duplicate Widevine tree logs under specific edge-cases.
- The Subtitle parse method no longer absorbs the syntax error message.
- Replaced all negative size values with 0 on TTML subtitles as a negative value would cause syntax errors.
- Fixed crash during decryption when shaka-packager skips decryption of a segment as it had no actual data and
  was just headers.
- Fixed CCExtractor crash in some scenarios by repacking the video stream prior to extraction.
- Fixed rare crash when calculating download speed of DASH and HLS downloads where a segment immediately finished
  after the previous segment. This seemed to only happen on the very last segment in rare situations.
- Fixed some failures parsing `tenc` mp4 boxes when obtaining the track's Key ID by using my own fork of pymp4
  with up-to-date code and further fixes.
- Fixed crashes when parsing some `tenc` mp4 boxes by simply skipping `tenc` boxes that fail to parse. This happens
  because some services seem to mix up the data of the `tenc` box with that of another type of box.
- Fixed using invalid `tenc` boxes by skipping ones with a version number greater than 1.

## [2.1.0] - 2023-03-16

### Added

- The Track get_init_segment method has been re-written to be more controllable. A specific Byte-range, URL, and
  maximum size can now be specified. A manually specified URL will override the Track's current URL. The Byte-range
  will override the fallback value of `0-20000` (where 20000 is the default `maximum_size`). It now also checks if the
  server supports Byte-range, or it will otherwise stream the response. It also tries to get the file size length and
  uses that instead of `maximum_size` unless it's bigger than `maximum_size`.
- Added new `get_key_id` method to Track to probe the track for a track-specific Encryption Key ID. This is similar to
  Widevine's `from_track` method but ignores all `pssh` boxes and manifest information as the information within those
  could be for a wider range of tracks or not for that track at all.
- Added a 5-attempt retry system to DASH and HLS downloads. URL downloads only uses aria2(c)'s built in retry system
  which has the same amount of tries and same delay between attempts. Any errors emitted when downloading segments will
  not be printed to console unless it occurred on the last attempt.
- Added a fallback way to obtain language information by taking it from the representation ID value, which may have the
  language code within it. E.g., `audio_en=128000` would be an English audio track at 128kb/s. We now take the `en`
  from that ID where possible.
- Added support for 13-char JS-style timestamp values to the Cacher system.
- Improved Forced Subtitle recognition by checking for both `forced-subtitle` and `forced_subtitle` (#43).

### Changed

- The `*` symbol is no longer spaced after the Widevine `KID:KEY` when denoting that it is for this specific PSSH.
  This reduces wasted vertical space.
- The "aria2 will resume download if the transfer is restarted" logs that occur when aria2(c) handles the CTRL+C break,
  and "If there are any errors, then see the log file" logs are now ignored and no longer logged to the console.
- DASH tracks will no longer prepare and license DRM unless it's just about to download. This is to reduce unnecessary
  preparation of DRM if the track had been converted to a URL download.
- For a fix listed below, we now use a fork of https://github.com/globocom/m3u8 that fixes a glaring problem with the
  EXT-X-KEY parsing system. See <https://github.com/globocom/m3u8/pull/313>.
- The return code when mkvmerge returns an error is now logged with the error message.
- SubtitleEdit has been silenced when using it for SDH stripping.

### Fixed

- Fixed URL joining and Base URL calculations on DASH manifests that use multiple Base URL values.
- URL downloads will now store the chosen DRM before preparing and licensing with the DRM.
- URL downloads will now prepare and license with the DRM if the Track has pre-existing DRM information. Previously it
  would only prepare and license DRM if it did not pre-emptively have DRM information before downloading.
- The `*` symbol that indicates that the KID:KEY is for the track being downloaded now uses the new `get_key_id` method
  of the track for a more accurate reading.
- License check now ensures if a KEY was returned for the Track instead of all KIDs of the Track's PSSH. This prevents
  an issue where the PSSH may have Key IDs for a 720p and 1080p track, yet only a KEY for the 720p track was returned.
  It would have then raised an error and stopped the download, even though you are downloading the 720p track and not
  the 1080p track, therefore the error was irrelevant.
- Unnecessary duplicate license calls are now prevented in some scenarios where `--cdm-only` is used.
- Fixed accuracy and speed of preparing and licensing DRM on HLS manifests where multiple EXT-X-KEY definitions appear
  in the manifest throughout the file. Using <https://github.com/globocom/m3u8/pull/313> we can now accurately get a
  list of EXT-X-KEYs mapped to each segment. This is a game changer for HLS manifests that use unique keys for every
  single (or most) segments as it would have otherwised needed to initialize (and possibly do network requests) for
  100s of EXT-X-KEY information, per segment. This caused downloads of HLS manifests that used a unique key per segment
  to slow to a binding crawl, and still not even decrypt correctly as it wouldn't be able to map the correct initialized
  key to the correct segment.
- Fixed a regression that incorrectly implemented the OnMultiplex event for Audio and Subtitle tracks causing them to
  never trigger. It would instead accidentally have trigger the last Video track's OnMultiplex event instead of the
  Audio or Subtitle's event.
- The above fix also fixed the automatic SDH stripping subtitle. Any automatically created SDH->non-SDH subtitle from
  prior downloads would not have actually had SDH captions stripped, it would instead be a duplicate subtitle.

### New Contributors

- [Hollander-1908](https://github.com/Hollander-1908)

## [2.0.1] - 2023-03-07

### Added

- Re-added logging support for shaka-packager on errors and warnings. Do note that INFO logs and the 'Insufficient bits
  in bitstream for given AVC profile' warning logs are ignored and never printed.
- Added new exceptions to the Widevine DRM class, `CEKNotFound` and `EmptyLicense`.
- Added support for Byte-ranges on HLS init maps.

### Changed

- Now lists the full 'Episode #' text when listing episode titles without an episode name.
- Subprocess exceptions from a download worker no longer prints a traceback. It now only logs the return code. This is
  because all subprocess errors during a download is now logged, therefore the full traceback is no longer necessary.
- Aria2(c) no longer pre-allocates file space if segmented. This is to reduce generally unnecessary upfront I/O usage.
- The Widevine DRM class's `get_content_keys` method now raises the new `CEKNotFound` and `EmptyLicense` exceptions not
  `ValueError` exceptions.
- The prepare_drm code now raises exceptions where needed instead of `sys.exit(1)`. Callees do not need to make any
  changes. The exception should continue to go up the call stack and get handled by the `dl` command.

### Fixed

- Fixed regression that broke support for pproxy. Do note that while pproxy has wheel's for Python 3.11+, it seems to
  be broken. I recommend using Python 3.10 or older for now. See <https://github.com/qwj/python-proxy/issues/161>.
- Fixed regression and now store the chosen DRM object back to the track.drm field. Please note that using the track
  DRM field in Service code is not recommended, but for some services it's simply required.
- Fixed regression since v1.4.0 where the byte-range calculation was actually slightly off one on the right-side range.
  This was a one-indexed vs. zero-indexed problem. Please note that this could have affected the integrity of HLS
  downloads if they used EXT-X-BYTERANGE.
- Fixed possible soft-lock in HLS if the Queue for previous segment key and init data gets stuck in an empty state over
  an exception in a download thread. E.g., if a thread takes the previous segment key, throws an exception, and did not
  get the chance to give it back for the next thread.
- The prepare_drm function now handles unexpected exceptions raised in the Service's license method. This code would of
  otherwise been absorbed and the download would have soft-locked.
- Prevented a double-licensing call race-condition on HLS tracks by using a threading lock when preparing DRM
  information. This is not required in DASH, as it prepares DRM on the main thread, once, not per-segment.
- Fixed printing of aria2(c) logs when redirecting progress information to rich progress bars.
- Explicitly mark DASH and HLS aria2(c) downloads as segmented.
- Fixed listing of episode titles without an episode name.
- Fixed centering of the project URL in the ASCII banner.
- Removed the accidental double-newline after the ASCII banner.

## [2.0.0] - 2023-03-01

This release brings a huge change to the fundamentals of Devine's logging, UI, and UX.

### Added

- Add new dependency [rich](https://github.com/Textualize/rich) for advanced color and logging capabilities.
- Set rich console output color scheme to the [Catppuccin Mocha](https://github.com/catppuccin/palette) theme.
- Add full download cancellation support by using CTRL+C. Track downloads will now be marked as STOPPED if you press
  CTRL+C to stop the download, or FAILED if any unexpected exception occurs during a download. The track will be marked
  as SKIPPED if the download stopped or failed before it got a chance to begin. It will print a download cancelled
  message if downloading was stopped, or a download error message if downloading failed. It will print the first
  download error traceback with rich before stopping.
- Downloads will now automatically cancel if any track or segment download fails.
- Implement sub-commands `add` and `delete` to the `wvd` command for adding and deleting WVD (Widevine Device) files to
  and from the configured WVDs directory (#31).
- Add new config option to disable the forced background color. You may want to disable the purple background if you're
  terminal isn't able to apply it correctly, or you prefer to use your own terminal's background color.
- Create `ComfyConsole`, `ComfyLogRenderer`, and `ComfyRichHandler`. These are hacky classes to implement padding to
  the left and right of all rich console output. This gives devine a comfortable and freeing look-and-feel.
- An ASCII banner is now displayed at the start of software execution with the version number.
- Add rich status output to various parts of the download process. It's also used when checking GEOFENCE within the
  base Service class. I encourage you to follow similar procedures where possible in Service code. This will result in
  cleaner log output, and overall less logs being made when finished.
- Add three rich horizontal rules to separate logs during the download process. The Service used, the Title received
  from `get_titles()`, and then the Title being downloaded. This helps identify which logs are part of which process.
- Add new `tree` methods to `Series`, `Movies`, and `Album` classes to list items within the objects with Rich Tree.
  This allows for more rich console output when displaying E.g., Seasons and Episodes within a Series, or Songs within
  an Album.
- Add new `tree` method to the `Tracks` class to list the tracks received from `get_tracks()` with Rich Tree. Similar
  to the change just above, this allows for more rich console output. It has replaced the `Tracks.print()` method.
- Add a rich progress bar to the track multiplexing operation.
- Add a log when a download finishes, how long it took, and where the final muxed file was moved to.
- Add a new track event, `OnMultiplex`. This event is run prior to multiplexing the finalized track data together. Use
  this to run code once a track has finished downloading and all the post-download operations.
- Add support for mapping Netflix profiles beginning with `h264` to AVC. E.g., the new -QC profiles.
- Download progress bars now display the download speed. It displays in decimal (^1024) size. E.g., MB/s.
- If a download stops or fails, any residual file that may have been downloaded in an incomplete OR complete state will
  now be deleted. Download continuation is not yet supported, and this will help to reduce leftover stale files.

### Changed

- The logging base config now has `ComfyRichHandler` as its log handler for automatic rich console output when using
  the logging system.
- The standard `traceback` module has been overridden with `rich.traceback` for styled traceback output.
- Only the rich console output is now saved when using `--log`.
- All `tqdm` progress bars have been replaced with rich progress bars. The rich progress bars are now displayed under
  each track tree.
- The titles are now only listed if `--list-titles` is used. Otherwise, only a brief explanation of what it received
  from `get_titles()` will be returned. E.g., for Series it will list how many seasons and episodes were received.
- Similarly, all available tracks are now only listed if `--list` is used. This is to reduce unnecessary prints, and to
  separate confusion between listings of available tracks, and listings of tracks that are going to be downloaded.
- Listing all available tracks with `--list` no longer continues execution. It now stops after the first list. If you
  want to list available tracks for a specific title, use `-w` in combination with `--list`.
- The available tracks are now printed in a rich panel with a header denoting the tracks as such.
- The `Series`, `Movies`, and `Album` classes now have a much more simplified string representation. They now simply
  state the overarching content within them. E.g., Series says the title and year of the TV Show.
- The final log when all titles are processed is now a rich log and states how long the entire process took.
- Widevine DRM license information is now printed below the tracks as a rich tree.
- The CCExtractor process, Subtitle Conversion process, and FFmpeg Repacking process were all moved out of the track
  download function (and therefore the thread) to be done on the main thread after downloading. This improves download
  speed as the threads can close and be freed quicker for the next track to begin.
- The CCExtractor process is now optional and will be skipped if the binary could not be found. An error is still
  logged in the cases where it would have run.
- The execution point of the `OnDownloaded` event has been moved to directly run after the stream has been downloaded.
  It used to run after all the post-download operations finished like CCExtractor, FFmpeg Repacking, and Subtitle
  Conversion.
- The automatic SDH-stripped subtitle track now uses the new `OnMultiplex` event instead of `OnDownloaded`. This is to
  account for the previous change as it requires the subtitle to be first converted to SubRip to support SDH-stripping.
- Logs during downloads now appear before the downloading track list. This way it isn't constantly interrupting view of
  the progress.
- Now running aria2(c) with normal subprocess instead of through asyncio. This removes the creation of yet another
  thread which is unnecessary as these calls would have already been under a non-main thread.
- Moved Widevine DRM licensing calls before the download process for normal URL track downloads.
- Segment Merging code for DASH and HLS downloads have been moved from the `dl` class to the HLS and DASH class.

### Removed

- Remove explicit dependency on `coloredlogs` and `colorama` as they are no longer used by devine itself.
- Remove dependency `tqdm` as it was replaced with rich progress bars.
- Remove now-unused logging constants like the custom log formats.
- Remove `Tracks.print()` function as it was replaced with the new `Tracks.tree()` function.
- Remove unnecessary sleep calls at the start of threads. This was believed to help with the download stop event check
  but that was not the case. It instead added an artificial delay with downloads.

### Fixed

- Fix another crash when using devine without a config file. It now creates the directory of the config file before
  making a new config file.
- Set the default aria2(c) file-allocation to `prealloc` like stated in the config documentation. It uses `prealloc` as
  the default, as `falloc` is generally unsupported in most scenarios, so it's not a good default.
- Correct the config documentation in regard to `proxies` now being called `proxy_providers`, and `basic` actually
  being a `dict` of lists, and not a `dict` of strings.

## [1.4.0] - 2023-02-25

### Added

- Add support for byte-ranged HLS and DASH segments, i.e., HLS EXT-X-BYTERANGE and DASH SegmentBase. Byte-ranged
  segments will be downloaded using python-requests as aria2(c) does not support byte ranges.
- Added support for data URI scheme in ClearKey DRM, including support for the base64 extension.

### Changed

- Increase the urllib3 connection pool max size from the default 10 to 16 * 2. This is to accommodate up to 16
  byte-ranged segment downloads while still giving enough room for a few other connections.
- The urllib3 connection pool now blocks and waits if it's full. This removes the Connection Pool Limit warnings when
  downloading more than one byte-ranged segmented track at a time.
- Moved `--log` from the `dl` command to the entry command to allow logging of more than just the download command.
  With this change, the logs now include the initial root logs, including the version number.
- Disable the urllib3 InsecureRequestWarnings as these seem to occur when using HTTP+S proxies when connecting to an
  HTTPS URL. While not ideal, we can't solve this problem, and the warning logs are quite annoying.

### Removed

- Remove the `byte_range` parameter from the aria2(c) downloader that was added in v1.3.0 as it turns out it doesn't
  actually work. Theoretically it should, but it seems aria2(c) doesn't honor the Range header correctly and fails.

### Fixed

- Fix the JOC check on HLS playlists to check if audio channels are defined first.
- Fix decryption of AES-encrypted segments that are not pre-padded to AES-CBC boundary size (16 bytes).
- Fix the order of segment merging on Linux machines. On Windows, the `pathlib.iterdir()` function is always in order.
  However, on Linux, or at least some machines, this was not the case.
- Fix printing of the traceback when a download worker raises an unexpected exception.
- Fix initial creation of the config file if none was created yet.

## [1.3.1] - 2023-02-23

### Fixed

- Fixed a regression where the `track.path` was only updated for `Descriptor.URL` downloads if it had DRM. This caused
  downloads of subtitles or DRM-free tracks using the `URL` descriptor to be broken (#33).
- Fixed a regression where `title` and `track` were not passed to the Service's functions for getting Widevine Service
  Certificates and Widevine Licenses.
- Corrected the Cookie Path that was logged when adding cookies with `devine auth add`.
- The Config data is now defaulted to an empty dictionary when completely empty or non-existent. This fixes a crash if
  you try to use `devine auth add` without a config file.

## [1.3.0] - 2023-02-22

## Deprecated

- Support for Python 3.8 has been dropped. Support for Windows 7 ended in January 2020.
- Although Python 3.8 is the last version with support for Windows 7, the decision was made to drop support because
  the number of affected users would be low.
- You may be interested in <https://github.com/adang1345/PythonWin7>, which has newer installers with patched support.

### Added

- Segmented HLS and DASH downloads now provide useful progress information using TQDM. Previously, aria2c would print
  progress information, but it was not very useful for segmented downloads due to how the information was presented.
- Segmented HLS and DASH downloads are now manually multi-threaded in a similar way to aria2c's `--j=16`.
- A class-function was added to the Widevine DRM class to obtain PSSH and KID information from init data by looking for
  PSSH and TENC boxes. This is an alternative to the from_track class-function when you only have the init data and not
  a track object.
- Aria2c now has the ability to silence progress output and provide extra arguments.

### Changed

- The downloading system for HLS and DASH has been completely reworked. It no longer downloads segments, merges them,
  and then decrypts. Instead, it now downloads and decrypts each individual segment. It dynamically switches DRM and
  Init Data per-segment where needed, fully supporting multiple EXT-X-KEY, EXT-X-MAP, and EXT-X-DISCONTINUITY tags in
  HLS. You can now download DRM-encrypted and DRM-free segments from within the same manifest, as well as manifests
  with unique DRM per-segment. None of this was possible with the old method of downloading.
- If a HLS manifest or segment uses an EXT-X-KEY with the method of NONE, it is assumed that the manifest or segment is
  DRM-free. This behavior applies even if the manifest or segment has other EXT-X-KEY methods specified, as that would
  be a mistake in the manifest.
- HLS now uses the proxy when loading AES-128 DRM as ClearKey objects, which is required for some services. It will
  only be used if `Track.needs_proxy` is True.
- The Widevine and ClearKey DRM classes decrypt functions no longer ask for a track. Instead, they ask for an input
  file path to which it will decrypt. It will automatically delete the input file and put the decrypted data in its
  place.

### Removed

- The AtomicSQL utility was removed because it did not actually assist in making the SQL connections thread-safe. It
  helped, but in an almost backwards and over-thought approach.

### Fixed

- The Cacher expiration check now uses your local datetime timestamp over the UTC timestamp, which seems to have fixed
  early or late expiration if you are not at exactly UTC+00:00.
- The cookies file path is now checked to exist if supplied with the `--cookies` argument (#30).
- An error is now logged, and execution will end if none of the DRM for a HLS manifest or segment is supported.
- HLS now only loads AES-128 EXT-X-KEY methods as ClearKey DRM because it currently only supports AES-128.
- AtomicSQL was replaced with connection factory systems using thread-safe storage for SQL connections. All Vault SQL
  calls are now fully thread-safe.

## [1.2.0] - 2023-02-13

### Deprecation Warning

- This release marks the end of support for Python 3.8.x.
- Although version 1.0.0 was intended to support Python 3.8.x, PyCharm failed to warn about a specific type annotation
  incompatibility. As a result, I was not aware that the support was not properly implemented.
- This release adds full support for Python 3.8.x, but it will be the only release with such support.

### Added

- The `dl` command CLI now includes Bitrate Selection options: `-vb/--vbitrate` and `-ab/--abitrate`.
- The `dl` command CLI now includes an Audio Channels Selection option: `-c/--channels`.
- If a download worker fails abruptly, a full traceback will now be printed.
- The aria2c downloader has a new parameter for downloading a specific byte range.

### Changed

- The usage of `Path.with_stem` with `Path.with_suffix` has been simplified to `Path.with_name`.
- When printing audio track information, the assumption that the audio is `2.0ch` has been removed.
- If audio channels were previously set as an integer value, they are no longer transformed as e.g., `6ch` and now
  follow the normal behavior of being defined as a float value, e.g., `6.0`.
- Audio channels are now explicitly parsed as float values, therefore parsing of values such as `16/JOC` (HLS) is no
  longer supported. The HLS manifest parser now assumes the track to be `5.1ch` if the channels value is set to
  `.../JOC`.

### Fixed

- Support for Python `>=3.8.6,<3.9.0` has been fixed.
- The final fallback FPS value is now only obtained from the SegmentBase's timescale value if it exists.
- The FutureWarning that occurred when getting Segment URLs from SegmentTemplate DASH manifests has been removed.
- The HLS manifest parser now correctly sets the audio track's `joc` parameter.
- Some Segmented WEBVTT streams may have included the WEBVTT header data when converting to SubRip SRT. This issue has
  been fixed by separating the header from any previous caption before conversion.
- The DASH manifest parser now uses the final redirected URL as the manifest URI (#25).
- File move operations from or to different drives (e.g., importing a cookie from another drive in `auth add`) (#27).

### New Contributors

- [Arias800](https://github.com/Arias800)
- [varyg1001](https://github.com/varyg1001)

## [1.1.0] - 2023-02-07

### Added

- Added utility to change the video range flag between full(pc) and limited(tv).
- Added utility to test decoding of video and audio streams using FFmpeg.
- Added CHANGELOG.md

### Changed

- The services and profiles listed by `auth list` are now sorted alphabetically.
- An explicit error is now logged when adding a Cookie to a Service under a duplicate name.

### Fixed

- Corrected the organization name across the project from `devine` to `devine-dl` as `devine` was taken.
- Fixed startup crash if the config was not yet created or was blank.
- Fixed crash when using the `cfg` command to set a config option on new empty config files.
- Fixed crash when loading key vaults during the `dl` command.
- Fixed crash when using the `auth list` command when you do not have a `Cookies` data directory.
- Fixed crash when adding a Cookie using `auth add` to a Service that has no directory yet.
- Fixed crash when adding a Credential using `auth add` when it's the first ever credential, or first for the Service.

## [1.0.0] - 2023-02-06

Initial public release under the name Devine.

[3.3.1]: https://github.com/devine-dl/devine/releases/tag/v3.3.1
[3.3.0]: https://github.com/devine-dl/devine/releases/tag/v3.3.0
[3.2.0]: https://github.com/devine-dl/devine/releases/tag/v3.2.0
[3.1.0]: https://github.com/devine-dl/devine/releases/tag/v3.1.0
[3.0.0]: https://github.com/devine-dl/devine/releases/tag/v3.0.0
[2.2.0]: https://github.com/devine-dl/devine/releases/tag/v2.2.0
[2.1.0]: https://github.com/devine-dl/devine/releases/tag/v2.1.0
[2.0.1]: https://github.com/devine-dl/devine/releases/tag/v2.0.1
[2.0.0]: https://github.com/devine-dl/devine/releases/tag/v2.0.0
[1.4.0]: https://github.com/devine-dl/devine/releases/tag/v1.4.0
[1.3.1]: https://github.com/devine-dl/devine/releases/tag/v1.3.1
[1.3.0]: https://github.com/devine-dl/devine/releases/tag/v1.3.0
[1.2.0]: https://github.com/devine-dl/devine/releases/tag/v1.2.0
[1.1.0]: https://github.com/devine-dl/devine/releases/tag/v1.1.0
[1.0.0]: https://github.com/devine-dl/devine/releases/tag/v1.0.0
