# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[2.0.1]: https://github.com/devine-dl/devine/releases/tag/v2.0.1
[2.0.0]: https://github.com/devine-dl/devine/releases/tag/v2.0.0
[1.4.0]: https://github.com/devine-dl/devine/releases/tag/v1.4.0
[1.3.1]: https://github.com/devine-dl/devine/releases/tag/v1.3.1
[1.3.0]: https://github.com/devine-dl/devine/releases/tag/v1.3.0
[1.2.0]: https://github.com/devine-dl/devine/releases/tag/v1.2.0
[1.1.0]: https://github.com/devine-dl/devine/releases/tag/v1.1.0
[1.0.0]: https://github.com/devine-dl/devine/releases/tag/v1.0.0
