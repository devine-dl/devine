<p align="center">
    <img src="https://user-images.githubusercontent.com/17136956/216880837-478f3ec7-6af6-4cca-8eef-5c98ff02104c.png">
    <a href="https://github.com/devine-dl/devine">Devine</a>
    <br/>
    <sup><em>Modular Movie, TV, and Music Archival Software</em></sup>
    <br/>
    <a href="https://discord.gg/34K2MGDrBN">
        <img src="https://img.shields.io/discord/841055398240059422?label=&logo=discord&logoColor=ffffff&color=7289DA&labelColor=7289DA" alt="Discord">
    </a>
</p>

<p align="center">
    <a href="https://github.com/devine-dl/devine/actions/workflows/ci.yml">
        <img src="https://github.com/devine-dl/devine/actions/workflows/ci.yml/badge.svg" alt="Build status">
    </a>
    <a href="https://python.org">
        <img src="https://img.shields.io/badge/python-3.9.0%2B-informational" alt="Python version">
    </a>
    <a href="https://deepsource.io/gh/devine-dl/devine/?ref=repository-badge">
        <img src="https://deepsource.io/gh/devine-dl/devine.svg/?label=active+issues&token=1ADCbjJ3FPiGT_s0Y0rlugGU" alt="DeepSource">
    </a>
    <br/>
    <a href="https://github.com/astral-sh/ruff">
        <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Linter: Ruff">
    </a>
    <a href="https://python-poetry.org">
        <img src="https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json" alt="Dependency management: Poetry">
    </a>
</p>

## Features

- 🚀 Seamless Installation via [pip](#installation)
- 🎥 Movie, Episode, and Song Service Frameworks
- 🛠️ Built-in [DASH] and [HLS] Parsers
- 🔒 Widevine DRM integration via [pywidevine](https://github.com/devine-dl/pywidevine)
- 💾 Local & Remote DRM Key-vaults
- 🌍 Local & Remote Widevine CDMs
- 👥 Multi-profile Authentication per-service with Credentials and/or Cookies
- 🤖 Automatic P2P filename structure with Group Tag
- ⚙️ YAML for Configuration
- ❤️ Fully Open-Source! Pull Requests Welcome

  [DASH]: <devine/core/manifests/dash.py>
  [HLS]: <devine/core/manifests/hls.py>

## Installation

```shell
$ pip install devine
```

> [!NOTE]
> If pip gives you a warning about a path not being in your PATH environment variable then promptly add that path then
> close all open command prompt/terminal windows, or `devine` won't work as it will not be found.

Voilà 🎉 — You now have the `devine` package installed!  
A command-line interface is now available, try `devine --help`.

### Dependencies

The following is a list of programs that need to be installed by you manually.

- [CCExtractor] for extracting Closed Caption data like EIA-608 from video streams and converting as SRT.
- [FFmpeg] (and ffprobe) for repacking/remuxing streams on specific services, and evaluating stream data.
- [MKVToolNix] v54+ for muxing individual streams to an `.mkv` file.
- [shaka-packager] for decrypting CENC-CTR and CENC-CBCS video and audio streams.
- (optional) [aria2(c)] to use as a [downloader](CONFIG.md#downloader-str).

> [!TIP]
> You should install these from a Package Repository if you can; including winget/chocolatey on Windows. They will
> automatically add the binary's path to your `PATH` environment variable and will be easier to update in the future.

> [!IMPORTANT]
> Most of these dependencies are portable utilities and therefore do not use installers. If you do not install them
> from a package repository like winget/choco/pacman then make sure you put them in your current working directory, in
> Devine's installation directory, or the binary's path into your `PATH` environment variable. If you do not do this
> then Devine will not be able to find the binaries.

  [winget]: <https://winget.run>
  [chocolatey]: <https://chocolatey.org>
  [aria2(c)]: <https://aria2.github.io>
  [CCExtractor]: <https://github.com/CCExtractor/ccextractor>
  [FFmpeg]: <https://ffmpeg.org>
  [MKVToolNix]: <https://mkvtoolnix.download/downloads.html>
  [shaka-packager]: <https://github.com/google/shaka-packager/releases/latest>

## Usage

First, take a look at `devine --help` for a full help document, listing all commands available and giving you more
information on what can be done with Devine.

Here's a checklist on what I recommend getting started with, in no particular order,

- [ ] Add [Services](#services), these will be used in `devine dl`.
- [ ] Add [Profiles](#profiles-cookies--credentials), these are your cookies and credentials.
- [ ] Add [Widevine Provisions](#widevine-provisions), also known as CDMs, these are used for DRM-protected content.
- [ ] Set your Group Tag, the text at the end of the final filename, e.g., `devine cfg tag NOGRP` for `...-NOGRP`.
- [ ] Set Up a Local Key Vault, take a look at the [Key Vaults Config](CONFIG.md#keyvaults-listdict).

And here's some more advanced things you could take a look at,

- [ ] Setting default Headers that the Request Session uses.
- [ ] Setting default Profiles and CDM Provisions to use for services.
- [ ] NordVPN and Hola Proxy Providers for automatic proxies.
- [ ] Hosting and/or Using Remote Key Vaults.
- [ ] Serving and/or Using Remote CDM Provisions.

Documentation on the config is available in the [CONFIG.md](CONFIG.md) file, it has a lot of handy settings.  
If you start to get sick of putting something in your CLI call, then I recommend taking a look at it!

## Services

Unlike similar project's such as [youtube-dl], Devine does not currently come with any Services. You must develop your
own Services and only use Devine with Services you have the legal right to do so.

> [!NOTE]
> If you made a Service for Devine that does not use Widevine or any other DRM systems, feel free to make a Pull Request
> and make your service available to others. Any Service on [youtube-dl] (or [yt-dlp]) would be able to be added to the
> Devine repository as they both use the [Unlicense license] therefore direct reading and porting of their code would be
> legal.

  [youtube-dl]: <https://github.com/ytdl-org/youtube-dl>
  [yt-dlp]: <https://github.com/yt-dlp/yt-dlp>
  [Unlicense license]: <https://choosealicense.com/licenses/unlicense>

### Creating a Service

> [!WARNING]
> Only create or use Service Code with Services you have full legal right to do so.

A Service consists of a folder with an `__init__.py` file. The file must contain a class of the same name as the folder.
The class must inherit the [Service] class and implement all the abstracted methods. It must finally implement a new
method named `cli` where you define CLI arguments.

1. Make a new folder within `/devine/services`. The folder name you choose will be what's known as the [Service Tag].
   This "tag" is used in the final output filename of downloaded files, for various code-checks, lookup keys in
   key-vault databases, and more.
2. Within the new folder create an `__init__.py` file and write a class inheriting the [Service] class. It must be named
   the exact same as the folder. It is case-sensitive.
3. Implement all the methods of the Service class you are inheriting that are marked as abstract.
4. Define CLI arguments by implementing a `cli` method. This method must be static (i.e. `@staticmethod`). For example
   to implement the bare minimum to receive a Title ID of sorts:
   ```python
   @staticmethod
   @click.command(name="YT", short_help="https://youtube.com", help=__doc__)
   @click.argument("title", type=str)
   @click.pass_context
   def cli(ctx, **kwargs):
       return YT(ctx, **kwargs)
   ```
   You must implement this `cli` method, even if you do not want or need any CLI arguments. It is required for the core
   CLI functionality to be able to find and call the class.
5. Accept the CLI arguments by overriding the constructor (the `__init__()` method):
   ```python
   def __init__(self, ctx, title):
       self.title = title
       super().__init__(ctx)  # important
       # ... the title is now available across all methods by calling self.title
   ```

> [!NOTE]
> - All methods of your class inherited from `Service` marked as abstract (`@abstractmethod`) MUST be implemented by
>   your class.
> - When overriding any method (e.g., `__init__()` method) you MUST super call it, e.g., `super().__init__()` at the
>   top of the override. This does not apply to any abstract methods, as they are unimplemented.
> - If preparing your Requests Session with global headers or such, then you should override the `get_session` method,
>   then modify `self.session`. Do not manually make `self.session` from scratch.

> [!TIP]
> 1. To make web requests use the `self.session` class instance variable, e.g. `self.session.get(url)`.
> 2. If you make a `config.yaml` file next to your `__init__.py`, you can access it with `self.config`.
> 3. You can include any arbitrary file within your Service folder for use by your Service. For example TLS certificate
>    files, or other python files with helper functions and classes.

  [Service]: <devine/core/service.py>
  [Service Tag]: <#service-tags>

### Service Tags

Service tags generally follow these rules:

- Tag must be between 2-4 characters long, consisting of just `[A-Z0-9i]{2,4}`.
  - Lower-case `i` is only used for select services. Specifically BBC iPlayer and iTunes.
- If the Service's commercial name has a `+` or `Plus`, the last character should be a `P`.
  E.g., `ATVP` for `Apple TV+`, `DSCP` for `Discovery+`, `DSNP` for `Disney+`, and `PMTP` for `Paramount+`.

These rules are not exhaustive and should only be used as a guide. You don't strictly have to follow these rules, but
I recommend doing so for consistency.

### Sharing Services

Sending and receiving zipped Service folders is quite cumbersome. Let's explore alternative routes to collaborating on
Service Code.

> [!WARNING]
> Please be careful with who you trust and what you run. The users you collaborate with on Service
> code could update it with malicious code that you would run via devine on the next call.

#### Forking

If you are collaborating with a team on multiple services then forking the project is the best way to go.

1. Create a new Private GitHub Repository without README, .gitignore, or LICENSE files.
   Note: Do NOT use the GitHub Fork button, or you will not be able to make the repository private.
2. `git clone <your repo url here>` and then `cd` into it.
3. `git remote add upstream https://github.com/devine-dl/devine`
4. `git remote set-url --push upstream DISABLE`
5. `git fetch upstream`
6. `git pull upstream master`
7. (optionally) Hard reset to the latest stable version by tag. E.g., `git reset --hard v1.0.0`.

Now commit your Services or other changes to your forked repository.  
Once committed all your other team members can easily pull changes as well as push new changes.

When a new update comes out you can easily rebase your fork to that commit to update.

1. `git fetch upstream`
2. `git rebase upstream/master`

However, please make sure you look at changes between each version before rebasing and resolve any breaking changes and
deprecations when rebasing to a new version.

If you are new to `git` then take a look at [GitHub Desktop](https://desktop.github.com).

> [!TIP]
> A huge benefit with this method is that you can also sync dependencies by your own Services as well!
> Just use `poetry` to add or modify dependencies appropriately and commit the changed `poetry.lock`.
> However, if the core project also has dependency changes your `poetry.lock` changes will conflict and you
> will need to learn how to do conflict resolution/rebasing. It is worth it though!

#### Symlinking

This is a great option for those who wish to do something like the forking method, but may not care what changes
happened or when and just want changes synced across a team.

This also opens up the ways you can host or collaborate on Service code. As long as you can receive a directory that
updates with just the services within it, then you're good to go. Options could include an FTP server, Shared Google
Drive, a non-fork repository with just services, and more.

1. Use any Cloud Source that gives you a pseudo-directory to access the Service files like a normal drive. E.g., rclone,
   Google Drive Desktop (aka File Stream), Air Drive, CloudPool, etc.
2. Create a `services` directory somewhere in it and have all your services within it.
3. [Symlink](https://en.wikipedia.org/wiki/Symbolic_link) the `services` directory to the `/devine` folder. You should
   end up with `/devine/services` folder containing services, not `/devine/services/services`.

You have to make sure the original folder keeps receiving and downloading/streaming those changes. You must also make
sure that the version of devine you have locally is supported by the Service code.

> [!NOTE]
> If you're using a cloud source that downloads the file once it gets opened, you don't have to worry as those will
> automatically download. Python importing the files triggers the download to begin. However, it may cause a delay on
> startup.

## Cookies & Credentials

Devine can authenticate with Services using Cookies and/or Credentials. Credentials are stored in the config, and
Cookies are stored in the data directory which can be found by running `devine env info`.

To add a Credential to a Service, take a look at the [Credentials Config](CONFIG.md#credentials-dictstr-strlistdict)
for information on setting up one or more credentials per-service. You can add one or more Credential per-service and
use `-p/--profile` to choose which Credential to use.

To add a Cookie to a Service, use a Cookie file extension to make a `cookies.txt` file and move it into the Cookies
directory. You must rename the `cookies.txt` file to that of the Service tag (case-sensitive), e.g., `NF.txt`. You can
also place it in a Service Cookie folder, e.g., `/Cookies/NF/default.txt` or `/Cookies/NF/.txt`.

You can add multiple Cookies to the `/Cookies/NF/` folder with their own unique name and then use `-p/--profile` to
choose which one to use. E.g., `/Cookies/NF/sam.txt` and then use it with `--profile sam`. If you make a Service Cookie
folder without a `.txt` or `default.txt`, but with another file, then no Cookies will be loaded unless you use
`-p/--profile` like shown. This allows you to opt in to authentication at whim.

> [!TIP]
> - If your Service does not require Authentication, then do not define any Credential or Cookie for that Service.
> - You can use both Cookies and Credentials at the same time, so long as your Service takes and uses both.
> - If you are using profiles, then make sure you use the same name on the Credential name and Cookie file name when
>   using `-p/--profile`.

> [!WARNING]
> Profile names are case-sensitive and unique per-service. They have no arbitrary character or length limit, but for
> convenience sake I don't recommend using any special characters as your terminal may get confused.

### Cookie file format and Extensions

Cookies must be in the standard Netscape cookies file format.  
Recommended Cookie exporter extensions:

- Firefox: "[Export Cookies]" by `Rotem Dan`
- Chromium: "[Open Cookies.txt]" by `Ninh Pham`, ~~or "Get cookies.txt" by `Rahul Shaw`~~

  [Export Cookies]: <https://addons.mozilla.org/addon/export-cookies-txt>
  [Open Cookies.txt]: <https://chrome.google.com/webstore/detail/gdocmgbfkjnnpapoeobnolbbkoibbcif>

Any other extension that exports to the standard Netscape format should theoretically work.

> __Warning__ The Get cookies.txt extension by Rahul Shaw is essentially spyware. Do not use it. There are some safe
> versions floating around (usually just older versions of the extension), but since there are safe alternatives I'd
> just avoid it altogether. Source: https://reddit.com/r/youtubedl/comments/10ar7o7

## Widevine Provisions

A Widevine Provision is needed for acquiring licenses containing decryption keys for DRM-protected content.
They are not needed if you will be using devine on DRM-free services. Please do not ask for any Widevine Device Files,
Keys, or Provisions as they cannot be provided.

Devine only supports `.WVD` files (Widevine Device Files). However, if you have the Provision RSA Private Key and
Device Client Identification Blob as blob files (e.g., `device_private_key` and `device_client_id_blob`), then you can
convert them to a `.WVD` file by running `pywidevine create-device --help`.

Once you have `.WVD` files, place them in the WVDs directory which can be found by calling `devine env info`.
You can then set in your config which WVD (by filename only) to use by default with `devine cfg cdm.default wvd_name`.
From here you can then set which WVD to use for each specific service. It's best to use the lowest security-level
provision where possible.

An alternative would be using a pywidevine Serve-compliant CDM API. Of course, you would need to know someone who is
serving one, and they would need to give you access. Take a look at the [remote_cdm](CONFIG.md#remotecdm-listdict)
config option for setup information. For further information on it see the pywidevine repository.

## End User License Agreement

Devine and it's community pages should be treated with the same kindness as other projects.
Please refrain from spam or asking for questions that infringe upon a Service's End User License Agreement.

1. Do not use Devine for any purposes of which you do not have the rights to do so.
2. Do not share or request infringing content; this includes Widevine Provision Keys, Content Encryption Keys,
   or Service API Calls or Code.
3. The Core codebase is meant to stay Free and Open-Source while the Service code should be kept private.
4. Do not sell any part of this project, neither alone nor as part of a bundle.
   If you paid for this software or received it as part of a bundle following payment, you should demand your money
   back immediately.
5. Be kind to one another and do not single anyone out.

## Contributors

<a href="https://github.com/rlaphoenix"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/17136956?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="rlaphoenix"/></a>
<a href="https://github.com/mnmll"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/22942379?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="mnmll"/></a>
<a href="https://github.com/shirt-dev"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/2660574?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="shirt-dev"/></a>
<a href="https://github.com/nyuszika7h"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/482367?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="nyuszika7h"/></a>
<a href="https://github.com/bccornfo"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/98013276?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="bccornfo"/></a>
<a href="https://github.com/Arias800"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/24809312?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="Arias800"/></a>
<a href="https://github.com/varyg1001"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/88599103?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="varyg1001"/></a>
<a href="https://github.com/Hollander-1908"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/93162595?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="Hollander-1908"/></a>
<a href="https://github.com/Shivelight"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/20620780?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="Shivelight"/></a>
<a href="https://github.com/knowhere01"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/113712042?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt="knowhere01"/></a>

## Licensing

This software is licensed under the terms of [GNU General Public License, Version 3.0](LICENSE).  
You can find a copy of the license in the LICENSE file in the root folder.

* * *

© rlaphoenix 2019-2024
