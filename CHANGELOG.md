# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.2.0]: https://github.com/devine-dl/devine/releases/tag/v1.2.0
[1.1.0]: https://github.com/devine-dl/devine/releases/tag/v1.1.0
[1.0.0]: https://github.com/devine-dl/devine/releases/tag/v1.0.0
