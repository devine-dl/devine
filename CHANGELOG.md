# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.3.1]: https://github.com/devine-dl/devine/releases/tag/v1.3.1
[1.3.0]: https://github.com/devine-dl/devine/releases/tag/v1.3.0
[1.2.0]: https://github.com/devine-dl/devine/releases/tag/v1.2.0
[1.1.0]: https://github.com/devine-dl/devine/releases/tag/v1.1.0
[1.0.0]: https://github.com/devine-dl/devine/releases/tag/v1.0.0
