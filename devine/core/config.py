from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import yaml
from appdirs import AppDirs


class Config:
    class _Directories:
        # default directories, do not modify here, set via config
        app_dirs = AppDirs("devine", False)
        core_dir = Path(__file__).resolve().parent
        namespace_dir = core_dir.parent
        commands = namespace_dir / "commands"
        services = namespace_dir / "services"
        vaults = namespace_dir / "vaults"
        user_configs = Path(app_dirs.user_config_dir)
        data = Path(app_dirs.user_data_dir)
        downloads = Path.home() / "Downloads" / "devine"
        temp = Path(tempfile.gettempdir()) / "devine"
        cache = Path(app_dirs.user_cache_dir)
        cookies = data / "Cookies"
        logs = Path(app_dirs.user_log_dir)
        wvds = data / "WVDs"
        dcsl = data / "DCSL"

    class _Filenames:
        # default filenames, do not modify here, set via config
        log = "devine_{name}_{time}.log"  # Directories.logs
        config = "config.yaml"  # Directories.services / tag
        root_config = "devine.yaml"  # Directories.user_configs
        chapters = "Chapters_{title}_{random}.txt"  # Directories.temp
        subtitle = "Subtitle_{id}_{language}.srt"  # Directories.temp

    def __init__(self, **kwargs: Any):
        self.dl: dict = kwargs.get("dl") or {}
        self.aria2c: dict = kwargs.get("aria2c") or {}
        self.cdm: dict = kwargs.get("cdm") or {}
        self.remote_cdm: list[dict] = kwargs.get("remote_cdm") or []
        self.credentials: dict = kwargs.get("credentials") or {}

        self.directories = self._Directories()
        for name, path in (kwargs.get("directories") or {}).items():
            if name.lower() in ("app_dirs", "core_dir", "namespace_dir", "user_configs", "data"):
                # these must not be modified by the user
                continue
            setattr(self.directories, name, Path(path).expanduser())

        self.filenames = self._Filenames()
        for name, filename in (kwargs.get("filenames") or {}).items():
            setattr(self.filenames, name, filename)

        self.headers: dict = kwargs.get("headers") or {}
        self.key_vaults: list[dict[str, Any]] = kwargs.get("key_vaults")
        self.muxing: dict = kwargs.get("muxing") or {}
        self.nordvpn: dict = kwargs.get("nordvpn") or {}
        self.profiles: dict = kwargs.get("profiles") or {}
        self.proxies: dict = kwargs.get("proxies") or {}
        self.proxy_providers: dict = kwargs.get("proxy_providers") or {}
        self.serve: dict = kwargs.get("serve") or {}
        self.services: dict = kwargs.get("services") or {}
        self.tag: str = kwargs.get("tag") or ""

    @classmethod
    def from_yaml(cls, path: Path) -> Config:
        if not path.exists():
            raise FileNotFoundError(f"Config file path ({path}) was not found")
        if not path.is_file():
            raise FileNotFoundError(f"Config file path ({path}) is not to a file.")
        return cls(**yaml.safe_load(path.read_text(encoding="utf8")))


# noinspection PyProtectedMember
config = Config.from_yaml(Config._Directories.user_configs / Config._Filenames.root_config)

__ALL__ = (config,)
