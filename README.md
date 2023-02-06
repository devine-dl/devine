<p align="center">
    <img src="https://user-images.githubusercontent.com/17136956/216880837-478f3ec7-6af6-4cca-8eef-5c98ff02104c.png">
    <a href="https://github.com/devine-dl/devine">Devine</a>
    <br/>
    <sup><em>Open-Source Movie, TV, and Music Downloading Solution</em></sup>
</p>

<p align="center">
    <a href="https://github.com/devine-dl/devine/actions/workflows/ci.yml">
        <img src="https://github.com/devine-dl/devine/actions/workflows/ci.yml/badge.svg" alt="Build status">
    </a>
    <a href="https://python.org">
        <img src="https://img.shields.io/badge/python-3.8.6%2B-informational" alt="Python version">
    </a>
</p>

## Features

- 🎥 Supports Movies, TV shows, and Music
- 🧩 Easy installation via PIP/PyPI
- 👥 Multi-profile authentication per-service with credentials or cookies
- 🤖 Automatic P2P filename structure with Group Tag
- 🛠️ Flexible Service framework system
- 📦 Portable Installations
- 🗃️ Local and Remote SQL-based Key Vault database
- ⚙️ YAML for Configuration
- 🌍 Local and Remote Widevine CDMs
- ❤️ Fully Open-Source! Pull Requests Welcome

## Installation

```shell
$ pip install devine
```

> __Note__ If you see warnings about a path not being in your PATH environment variable, add it, or `devine` won't run.

Voilà 🎉! You now have the `devine` package installed and a `devine` executable is now available.  
Check it out with `devine --help`!

### Dependencies

The following is a list of programs that need to be installed manually. I recommend installing these with [winget],
[chocolatey] or such where possible as it automatically adds them to your `PATH` environment variable and will be
easier to update in the future.

- [aria2(c)] for downloading streams and large manifests.
- [CCExtractor] for extracting Closed Caption data like EIA-608 from video streams and converting as SRT.
- [FFmpeg] (and ffprobe) for repacking/remuxing streams on specific services, and evaluating stream data.
- [MKVToolNix] v54+ for muxing individual streams to an `.mkv` file.
- [shaka-packager] for decrypting CENC-CTR and CENC-CBCS video and audio streams.

For portable downloads, make sure you put them in your current working directory, in the installation directory,
or put the directory path in your `PATH` environment variable. If you do not do this then their binaries will not be
able to be found.

  [winget]: <https://winget.run>
  [chocolatey]: <https://chocolatey.org>
  [aria2(c)]: <https://aria2.github.io>
  [CCExtractor]: <https://github.com/CCExtractor/ccextractor>
  [FFmpeg]: <https://fmpeg.org>
  [MKVToolNix]: <https://mkvtoolnix.download/downloads.html>
  [shaka-packager]: <https://github.com/google/shaka-packager/releases/latest>

### Portable installation

1. Download a Python Embeddable Package of a supported Python version (the `.zip` download).  
   (make sure it's either x64/x86 and not ARM unless you're on an ARM device).
2. Extract the `.zip` and rename the folder, if you wish.
3. Open Terminal and `cd` to the extracted folder.
4. Run the following on Windows:
```
(Invoke-WebRequest -Uri https://gist.githubusercontent.com/rlaphoenix/5ef250e61ceeb123c6696c05ad4dee8b/raw -UseBasicParsing).Content | .\python -
```
or the following on Linux/macOS:
```
curl -sSL https://gist.githubusercontent.com/rlaphoenix/5ef250e61ceeb123c6696c05ad4dee8b/raw | ./python -
```
5. Run `.\python -m pip install devine`

You can now call `devine` by,

- running `./python -m devine --help`, or,
- running `./Scripts/devine.exe --help`, or,
- symlinking the `/Scripts/devine.exe` binary to the root of the folder, for `./devine --help`, or,
- zipping the entire folder to `devine.zip`, for `python devine.zip --help`.

The last method of calling devine, by archiving to a zip file, is incredibly useful for sharing and portability!  
I urge you to give it a try!

### Services

Devine does not come with any infringing Service code. You must develop your own Service code and place them in
the `/devine/services` directory. There are different ways the add services depending on your installation type.
In some cases you may use multiple of these methods to have separate copies.

Please refrain from making or using Service code unless you have full rights to do so. I also recommend ensuring that
you keep the Service code private and secure, i.e. a private repository or keeping it offline.

No matter which method you use, make sure that you install any further dependencies needed by the services. There's
currently no way to have these dependencies automatically install apart from within the Fork method.

> __Warning__ Please be careful with who you trust and what you run. The users you collaborate with on Service
> code could update it with malicious code that you would run via devine on the next call.

#### via Copy & Paste

If you have service code already and wish to just install and use it locally, then simply putting it into the Services
directory of your local pip installation will do the job. However, this method is the worst in terms of collaboration.

1. Get the installation directory by running the following in terminal,
   `python -c 'import os,devine.__main__ as a;print(os.path.dirname(a.__file__))'`
2. Head to the installation directory and create a `services` folder if one is not yet created.
3. Within that `services` folder you may install or create service code.

> __Warning__ Uninstalling Python or Devine may result in the Services you installed being deleted. Make sure you back
> up the services before uninstalling.

#### via a Forked Repository

If you are collaborating with a team on multiple services then forking the project is the best way to go. I recommend
forking the project then hard resetting to the latest stable update by tag. Once a new stable update comes out you can
easily rebase your fork to that commit to update.

However, please make sure you look at changes between each version before rebasing and resolve any breaking changes and
deprecations when rebasing to a new version.

1. Fork the project with `git` or GitHub [(fork)](https://github.com/devine-dl/devine/fork).
2. Head inside the root `devine` directory and create a `services` directory.
3. Within that `services` folder you may install or create service code.

You may now commit changes or additions within that services folder to your forked repository.  
Once committed all your other team members can easily sync and contribute changes.

> __Note__ You may add Service-specific Python dependencies using `poetry` that can install alongside the project.
> Just do note that this will complicate rebasing when even the `poetry.lock` gets updates in the upstream project.

#### via Cloud storage (symlink)

This is a great option for those who wish to do something like the forking method, but without the need of constantly
rebasing their fork to the latest version. Overall less knowledge on git would be required, but each user would need
to do a bit of symlinking compared to the fork method.

This also opens up the ways you can host or collaborate on Service code. As long as you can receive a directory that
updates with just the services within it, then you're good to go. Options could include an FTP server, Shared Google
Drive, a non-fork repository with just services, and more.

1. Follow the steps in the [Copy & Paste method](#via-copy--paste) to create the `services` folder.
2. Use any Cloud Source that gives you a pseudo-directory to access the Service files. E.g., rclone or google drive fs.
3. Symlink the services directory from your Cloud Source to the new services folder you made.
   (you may need to delete it first)

Of course, you have to make sure the original folder keeps receiving and downloading/streaming those changes, or that
you keep git pulling those changes. You must also make sure that the version of devine you have locally is supported by
the Services code.

> __Note__ If you're using a cloud source that downloads the file once it gets opened, you don't have to worry as those
> will automatically download. Python importing the files triggers the download to begin. However, it may cause a delay
> on startup.

### Profiles (Cookies & Credentials)

Just like a streaming service, devine associates both a cookie and/or credential as a Profile. You can associate up to
one cookie and one credential per-profile, depending on which (or both) are needed by the Service. This system allows
you to configure multiple accounts per-service and choose which to use at any time.

Credentials are stored in the config, and Cookies are stored in the data directory. You can find the location of these
by running `devine env info`. However, you can manage profiles with `devine auth --help`. E.g. to add a new John
profile to Netflix with a Cookie and Credential, take a look at the following CLI call,
`devine auth add John NF --cookie "C:\Users\John\Downloads\netflix.com.txt --credential "john@gmail.com:pass123"`

You can also delete a credential with `devine auth delete`. E.g., to delete the cookie for John that we just added, run
`devine auth delete John --cookie`. Take a look at `devine auth delete --help` for more information.

> __Note__ Profile names are case-sensitive and unique per-service. They also have no arbitrary character or length
> limit, but for convenience I don't recommend using any special characters as your terminal may get confused.

#### Cookie file format and Extensions

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

### Widevine Provisions

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
serving one, and they would need to give you access. Take a look at the [remote_cdm](CONFIG.md#remotecdm--listdict--)
config option for setup information. For further information on it see the pywidevine repository.

## Usage

First, take a look at `devine --help` for a full help document, listing all commands available and giving you more
information on what can be done with Devine.

Here's a checklist on what I recommend getting started with, in no particular order,

- [ ] Add [Services](#services), these will be used in `devine dl`.
- [ ] Add [Profiles](#profiles--cookies--credentials-), these are your cookies and credentials.
- [ ] Add [Widevine Provisions](#widevine-provisions), also known as CDMs, these are used for DRM-protected content.
- [ ] Set your Group Tag, the text at the end of the final filename, e.g., `devine cfg tag NOGRP` for ...-NOGRP.
- [ ] Set Up a Local Key Vault, take a look at the [Key Vaults Config](CONFIG.md#keyvaults--listdict--).

And here's some more advanced things you could take a look at,

- [ ] Setting default Headers that the Request Session uses.
- [ ] Setting default Profiles and CDM Provisions to use for services.
- [ ] NordVPN and Hola Proxy Providers for automatic proxies.
- [ ] Hosting and/or Using Remote Key Vaults.
- [ ] Serving and/or Using Remote CDM Provisions.

Documentation on the config is available in the [CONFIG.md](CONFIG.md) file, it has a lot of handy settings.  
If you start to get sick of putting something in your CLI call, then I recommend taking a look at it!

## Development

The following steps are instructions on downloading, preparing, and running the code under a [Poetry] environment.
You can skip steps 3-5 with a simple `pip install .` call instead, but you miss out on a wide array of benefits.

1. `git clone https://github.com/devine-dl/devine`
2. `cd devine`
3. (optional) `poetry config virtualenvs.in-project true`
4. `poetry install`
5. `poetry run devine --help`

As seen in Step 5, running the `devine` executable is somewhat different to a normal PIP installation.
See [Poetry's Docs] on various ways of making calls under the virtual-environment.

  [Poetry]: <https://python-poetry.org>
  [Poetry's Docs]: <https://python-poetry.org/docs/basic-usage/#using-your-virtual-environment>

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

## Disclaimer

1. This project requires a valid Google-provisioned Private/Public Keypair and a Device-specific Client Identification
   blob; neither of which are included with this project.
2. Public testing provisions are available and provided by Google to use for testing projects such as this one.
3. License Servers have the ability to block requests from any provision, and are likely already blocking test provisions
   on production endpoints. Therefore, have the ability to block the usage of Devine by themselves.
4. This project does not condone piracy or any action against the terms of the Service or DRM system.
5. All efforts in this project have been the result of Reverse-Engineering and Publicly available research.

## Credit

- The awesome community for their shared research and insight into the Widevine Protocol and Key Derivation.

## Contributors

<a href="https://github.com/rlaphoenix"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/17136956?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt=""/></a>
<a href="https://github.com/mnmll"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/22942379?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt=""/></a>
<a href="https://github.com/shirt-dev"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/2660574?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt=""/></a>
<a href="https://github.com/nyuszika7h"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/482367?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt=""/></a>
<a href="https://github.com/bccornfo"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/98013276?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt=""/></a>

## License

© 2019-2023 rlaphoenix — [GNU General Public License, Version 3.0](LICENSE)
