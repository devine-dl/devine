# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.1.0]: https://github.com/devine-dl/devine/releases/tag/v1.1.0
[1.0.0]: https://github.com/devine-dl/devine/releases/tag/v1.0.0
