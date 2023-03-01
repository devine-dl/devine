# Config Documentation

This page documents configuration values and what they do. You begin with an empty configuration file.  
You may alter your configuration with `devine cfg --help`, or find the direct location with `devine env info`.  
Configuration values are listed in alphabetical order.

Avoid putting comments in the config file as they may be removed. Comments are currently kept only thanks
to the usage of `ruamel.yaml` to parse and write YAML files. In the future `yaml` may be used instead,
which does not keep comments.

## aria2c (dict)

- `file_allocation`
  Specify file allocation method. Default: `"prealloc"`

  - `"none"` doesn't pre-allocate file space.
  - `"prealloc"` pre-allocates file space before download begins. This may take some time depending on the size of the
    file.
  - `"falloc"` is your best choice if you are using newer file systems such as ext4 (with extents support), btrfs, xfs
    or NTFS (MinGW build only). It allocates large(few GiB) files almost instantly. Don't use falloc with legacy file
    systems such as ext3 and FAT32 because it takes almost same time as prealloc, and it blocks aria2 entirely until
    allocation finishes. falloc may not be available if your system doesn't have posix_fallocate(3) function.
  - `"trunc"` uses ftruncate(2) system call or platform-specific counterpart to truncate a file to a specified length.

## cdm (dict)

Pre-define which widevine device to use for each Service by Service Tag as Key (case-sensitive).  
The value should be a WVD filename without the file extension.

For example,

```yaml
AMZN: chromecdm_903_l3
NF: nexus_6_l1
```

You may also specify this device based on the profile used.

For example,

```yaml
AMZN: chromecdm_903_l3
NF: nexus_6_l1
DSNP:
  john_sd: chromecdm_903_l3
  jane_uhd: nexus_5_l1
```

You can also specify a fallback value to predefine if a match was not made.  
This can be done using `default` key. This can help reduce redundancy in your specifications.

For example, the following has the same result as the previous example, as well as all other
services and profiles being pre-defined to use `chromecdm_903_l3`.

```yaml
NF: nexus_6_l1
DSNP:
  jane_uhd: nexus_5_l1
default: chromecdm_903_l3
```

## credentials (dict)

Specify login credentials to use for each Service by Profile as Key (case-sensitive).

The value should be `email:password` or `username:password` (with some exceptions).  
The first section does not have to be an email or username. It may also be a Phone number.

For example,

```yaml
AMZN:
  james: james@gmail.com:TheFriend97
  jane: jane@example.tld:LoremIpsum99
  john: john@example.tld:LoremIpsum98
NF:
  john: john@gmail.com:TheGuyWhoPaysForTheNetflix69420
```

Credentials must be specified per-profile. You cannot specify a fallback or default credential.
Please be aware that this information is sensitive and to keep it safe. Do not share your config.

## directories (dict)

Override the default directories used across devine.  
The directories are set to common values by default.

The following directories are available and may be overridden,

- `commands` - CLI Command Classes.
- `services` - Service Classes.
- `vaults` - Vault Classes.
- `downloads` - Downloads.
- `temp` - Temporary files or conversions during download.
- `cache` - Expiring data like Authorization tokens, or other misc data.
- `cookies` - Expiring Cookie data.
- `logs` - Logs.
- `wvds` - Widevine Devices.

For example,

```yaml
downloads: "D:/Downloads/devine"
temp: "D:/Temp/devine"
```

There are directories not listed that cannot be modified as they are crucial to the operation of devine.

## dl (dict)

Pre-define default options and switches of the `dl` command.  
The values will be ignored if explicitly set in the CLI call.

The Key must be the same value Python click would resolve it to as an argument.  
E.g., `@click.option("-r", "--range", "range_", type=...` actually resolves as `range_` variable.

For example to set the default primary language to download to German,

```yaml
lang: de
```

or to set `--bitrate=CVBR` for the AMZN service,

```yaml
lang: de
AMZN:
  bitrate: CVBR
```

## headers (dict)

Case-Insensitive dictionary of headers that all Services begin their Request Session state with.  
All requests will use these unless changed explicitly or implicitly via a Server response.  
These should be sane defaults and anything that would only be useful for some Services should not
be put here.

Avoid headers like 'Accept-Encoding' as that would be a compatibility header that Python-requests will
set for you.

I recommend using,

```yaml
Accept-Language: "en-US,en;q=0.8"
User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.75 Safari/537.36"
```

## key_vaults (list\[dict])

Key Vaults store your obtained Content Encryption Keys (CEKs) and Key IDs per-service.

This can help reduce unnecessary License calls even during the first download. This is because a Service may
provide the same Key ID and CEK for both Video and Audio, as well as for multiple resolutions or bitrates.

You can have as many Key Vaults as you would like. It's nice to share Key Vaults or use a unified Vault on
Teams as sharing CEKs immediately can help reduce License calls drastically.

Two types of Vaults are in the Core codebase, SQLite and MySQL Vaults. Both directly connect to an SQLite or MySQL
Server. It has to connect directly to the Host/IP. It cannot be in front of a PHP API or such. Beware that some Hosts
do not let you access the MySQL server outside their intranet (aka Don't port forward or use permissive network
interfaces).

### Connecting to a MySQL Vault

MySQL vaults can be either MySQL or MariaDB servers. I recommend MariaDB.  
A MySQL Vault can be on a local or remote network, but I recommend SQLite for local Vaults.

```yaml
- type: MySQL
  name: "John#0001's Vault"  # arbitrary vault name
  host: "127.0.0.1"          # host/ip
  # port: 3306               # port (defaults to 3306)
  database: vault            # database used for devine
  username: jane11
  password: Doe123
```

I recommend giving only a trustable user (or yourself) CREATE permission and then use devine to cache at least one CEK
per Service to have it create the tables. If you don't give any user permissions to create tables, you will need to
make tables yourself.

- Use a password on all user accounts.
- Never use the root account with devine (even if it's you).
- Do not give multiple users the same username and/or password.
- Only give users access to the database used for devine.
- You may give trusted users CREATE permission so devine can create tables if needed.
- Other uses should only be given SELECT and INSERT permissions.

### Connecting to an SQLite Vault

SQLite Vaults are usually only used for locally stored vaults. This vault may be stored on a mounted Cloud storage
drive, but I recommend using SQLite exclusively as an offline-only vault. Effectively this is your backup vault in
case something happens to your MySQL Vault.

```yaml
- type: SQLite
  name: "My Local Vault"  # arbitrary vault name
  path: "C:/Users/Jane11/Documents/devine/data/key_vault.db"
```

**Note**: You do not need to create the file at the specified path.  
SQLite will create a new SQLite database at that path if one does not exist.  
Try not to accidentally move the `db` file once created without reflecting the change in the config, or you will end
up with multiple databases.

If you work on a Team I recommend every team member having their own SQLite Vault even if you all use a MySQL vault
together.

## muxing (dict)

- `set_title`
  Set the container title to `Show SXXEXX Episode Name` or `Movie (Year)`. Default: `true`

## profiles (dict)

Pre-define Profiles to use Per-Service.

For example,

```yaml
AMZN: jane
DSNP: john
```

You can also specify a fallback value to pre-define if a match was not made.  
This can be done using `default` key. This can help reduce redundancy in your specifications.

```yaml
AMZN: jane
DSNP: john
default: james
```

If a Service doesn't require a profile (as it does not require Credentials or Authorization of any kind), you can
disable the profile checks by specifying `false` as the profile for the Service.

```yaml
ALL4: false
CTV: false
```

## proxy_providers (dict)

Enable external proxy provider services.

### basic (list\[dict])

Define a mapping of country to proxy to use where required.  
The keys are region Alpha 2 Country Codes. Alpha 2 Country Codes are `[a-z]{2}` codes, e.g., `us`, `gb`, and `jp`.  
Don't get this mixed up with language codes like `en` vs. `gb`, or `ja` vs. `jp`.

Do note that each key's value is not a string but a list or sequence.
It will randomly choose which entry to use.

For example,

```yaml
us:
  - "http://john%40email.tld:password123@proxy-us.domain.tld:8080"
  - "http://jane%40email.tld:password456@proxy-us.domain2.tld:8080"
de:
  - "http://127.0.0.1:8888"
```

### nordvpn (dict)

Set your NordVPN Service credentials with `username` and `password` keys to automate the use of NordVPN as a Proxy
system where required.

You can also specify specific servers to use per-region with the `servers` key.  
Sometimes a specific server works best for a service than others, so hard-coding one for a day or two helps.

For example,

```yaml
username: zxqsR7C5CyGwmGb6KSvk8qsZ  # example of the login format
password: wXVHmht22hhRKUEQ32PQVjCZ
servers:
  - us: 12  # force US server #12 for US proxies
```

The username and password should NOT be your normal NordVPN Account Credentials.  
They should be the `Service credentials` which can be found on your Nord Account Dashboard.

Once set, you can also specifically opt in to use a NordVPN proxy by specifying `--proxy=gb` or such.
You can even set a specific server number this way, e.g., `--proxy=gb2366`.

Note that `gb` is used instead of `uk` to be more consistent across regional systems.

## remote_cdm (list\[dict])

Use [pywidevine] Serve-compliant Remote CDMs in devine as if it was a local widevine device file.  
The name of each defined device maps as if it was a local device and should be used like a local device.

For example,

```yaml
- name: chromecdm_903_l3   # name must be unique for each remote CDM
  # the device type, system id and security level must match the values of the device on the API
  # if any of the information is wrong, it will raise an error, if you do not know it ask the API owner
  device_type: CHROME
  system_id: 1234
  security_level: 3
  host: "http://xxxxxxxxxxxxxxxx/the_cdm_endpoint"
  secret: "secret/api key"
  device_name: "remote device to use"  # the device name from the API, usually a wvd filename
```

  [pywidevine]: <https://github.com/rlaphoenix/pywidevine>

## serve (dict)

Configuration data for pywidevine's serve functionality run through devine.
This effectively allows you to run `devine serve` to start serving pywidevine Serve-compliant CDMs right from your
local widevine device files.

For example,

```yaml
users:
  secret_key_for_jane:  # 32bit hex recommended, case-sensitive
    devices:  # list of allowed devices for this user
      - generic_nexus_4464_l3
    username: jane  # only for internal logging, users will not see this name
  secret_key_for_james:
    devices:
      - generic_nexus_4464_l3
    username: james
  secret_key_for_john:
    devices:
      - generic_nexus_4464_l3
    username: john
# devices can be manually specified by path if you don't want to add it to
# devine's WVDs directory for whatever reason
# devices:
#   - 'C:\Users\john\Devices\test_devices_001.wvd'
```

## services (dict)

Configuration data for each Service. The Service will have the data within this section merged into the `config.yaml`
before provided to the Service class.

Think of this config to be used for more sensitive configuration data, like user or device-specific API keys, IDs,
device attributes, and so on. A `config.yaml` file is typically shared and not meant to be modified, so use this for
any sensitive configuration data.

The Key is the Service Tag, but can take any arbitrary form for its value. It's expected to begin as either a list or
a dictionary.

For example,

```yaml
NOW:
  client:
    auth_scheme: MESSO
    # ... more sensitive data
```

## tag (str)

Group or Username to postfix to the end of all download filenames following a dash.  
For example, `tag: "J0HN"` will have `-J0HN` at the end of all download filenames.
