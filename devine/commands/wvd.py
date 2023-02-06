from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import click
import yaml
from google.protobuf.json_format import MessageToDict
from pywidevine.device import Device
from pywidevine.license_protocol_pb2 import FileHashes
from unidecode import UnidecodeError, unidecode

from devine.core.config import config
from devine.core.constants import context_settings


@click.group(
    short_help="Manage configuration and creation of WVD (Widevine Device) files.",
    context_settings=context_settings)
def wvd() -> None:
    """Manage configuration and creation of WVD (Widevine Device) files."""


@wvd.command()
@click.argument("path", type=Path)
def parse(path: Path) -> None:
    """
    Parse a .WVD Widevine Device file to check information.
    Relative paths are relative to the WVDs directory.
    """
    try:
        named = not path.suffix and path.relative_to(Path(""))
    except ValueError:
        named = False
    if named:
        path = config.directories.wvds / f"{path.name}.wvd"

    log = logging.getLogger("wvd")

    device = Device.load(path)

    log.info(f"System ID: {device.system_id}")
    log.info(f"Security Level: {device.security_level}")
    log.info(f"Type: {device.type}")
    log.info(f"Flags: {device.flags}")
    log.info(f"Private Key: {bool(device.private_key)}")
    log.info(f"Client ID: {bool(device.client_id)}")
    log.info(f"VMP: {bool(device.client_id.vmp_data)}")

    log.info("Client ID:")
    log.info(device.client_id)

    log.info("VMP:")
    if device.client_id.vmp_data:
        file_hashes = FileHashes()
        file_hashes.ParseFromString(device.client_id.vmp_data)
        log.info(str(file_hashes))
    else:
        log.info("None")


@wvd.command()
@click.argument("wvd_paths", type=Path, nargs=-1)
@click.argument("out_dir", type=Path, nargs=1)
def dump(wvd_paths: list[Path], out_dir: Path) -> None:
    """
    Extract data from a .WVD Widevine Device file to a folder structure.

    If the path is relative, with no file extension, it will dump the WVD in the WVDs
    directory.
    """
    if wvd_paths == (Path(""),):
        wvd_paths = list(config.directories.wvds.iterdir())
    for wvd_path, out_path in zip(wvd_paths, (out_dir / x.stem for x in wvd_paths)):
        try:
            named = not wvd_path.suffix and wvd_path.relative_to(Path(""))
        except ValueError:
            named = False
        if named:
            wvd_path = config.directories.wvds / f"{wvd_path.stem}.wvd"
        out_path.mkdir(parents=True, exist_ok=True)

        device = Device.load(wvd_path)

        log = logging.getLogger("wvd")
        log.info(f"Dumping: {wvd_path}")
        log.info(f"L{device.security_level} {device.system_id} {device.type.name}")
        log.info(f"Saving to: {out_path}")

        device_meta = {
            "wvd": {
                "device_type": device.type.name,
                "security_level": device.security_level,
                **device.flags
            },
            "client_info": {},
            "capabilities": MessageToDict(device.client_id, preserving_proto_field_name=True)["client_capabilities"]
        }
        for client_info in device.client_id.client_info:
            device_meta["client_info"][client_info.name] = client_info.value

        device_meta_path = out_path / "metadata.yml"
        device_meta_path.write_text(yaml.dump(device_meta), encoding="utf8")
        log.info(" + Device Metadata")

        if device.private_key:
            private_key_path = out_path / "private_key.pem"
            private_key_path.write_text(
                data=device.private_key.export_key().decode(),
                encoding="utf8"
            )
            private_key_path.with_suffix(".der").write_bytes(
                device.private_key.export_key(format="DER")
            )
            log.info(" + Private Key")
        else:
            log.warning(" - No Private Key available")

        if device.client_id:
            client_id_path = out_path / "client_id.bin"
            client_id_path.write_bytes(device.client_id.SerializeToString())
            log.info(" + Client ID")
        else:
            log.warning(" - No Client ID available")

        if device.client_id.vmp_data:
            vmp_path = out_path / "vmp.bin"
            vmp_path.write_bytes(device.client_id.vmp_data)
            log.info(" + VMP (File Hashes)")
        else:
            log.info(" - No VMP (File Hashes) available")


@wvd.command()
@click.argument("name", type=str)
@click.argument("private_key", type=Path)
@click.argument("client_id", type=Path)
@click.argument("file_hashes", type=Path, required=False)
@click.option("-t", "--type", "type_", type=click.Choice([x.name for x in Device.Types], case_sensitive=False),
              default="Android", help="Device Type")
@click.option("-l", "--level", type=click.IntRange(1, 3), default=1, help="Device Security Level")
@click.option("-o", "--output", type=Path, default=None, help="Output Directory")
@click.pass_context
def new(
    ctx: click.Context,
    name: str,
    private_key: Path,
    client_id: Path,
    file_hashes: Optional[Path],
    type_: str,
    level: int,
    output: Optional[Path]
) -> None:
    """
    Create a new .WVD Widevine provision file.

    name: The origin device name of the provided data. e.g. `Nexus 6P`. You do not need to
        specify the security level, that will be done automatically.
    private_key: A PEM file of a Device's private key.
    client_id: A binary blob file which follows the Widevine ClientIdentification protobuf
        schema.
    file_hashes: A binary blob file with follows the Widevine FileHashes protobuf schema.
        Also known as VMP as it's used for VMP (Verified Media Path) assurance.
    """
    try:
        # TODO: Remove need for name, create name based on Client IDs ClientInfo values
        name = unidecode(name.strip().lower().replace(" ", "_"))
    except UnidecodeError as e:
        raise click.UsageError(f"name: Failed to sanitize name, {e}", ctx)
    if not name:
        raise click.UsageError("name: Empty after sanitizing, please make sure the name is valid.", ctx)
    if not private_key.is_file():
        raise click.UsageError("private_key: Not a path to a file, or it doesn't exist.", ctx)
    if not client_id.is_file():
        raise click.UsageError("client_id: Not a path to a file, or it doesn't exist.", ctx)
    if file_hashes and not file_hashes.is_file():
        raise click.UsageError("file_hashes: Not a path to a file, or it doesn't exist.", ctx)

    device = Device(
        type_=Device.Types[type_.upper()],
        security_level=level,
        flags=None,
        private_key=private_key.read_bytes(),
        client_id=client_id.read_bytes()
    )

    if file_hashes:
        device.client_id.vmp_data = file_hashes.read_bytes()

    out_path = (output or config.directories.wvds) / f"{name}_{device.system_id}_l{device.security_level}.wvd"
    device.dump(out_path)

    log = logging.getLogger("wvd")

    log.info(f"Created binary WVD file, {out_path.name}")
    log.info(f" + Saved to: {out_path.absolute()}")
    log.info(f" + System ID: {device.system_id}")
    log.info(f" + Security Level: {device.security_level}")
    log.info(f" + Type: {device.type}")
    log.info(f" + Flags: {device.flags}")
    log.info(f" + Private Key: {bool(device.private_key)}")
    log.info(f" + Client ID: {bool(device.client_id)}")
    log.info(f" + VMP: {bool(device.client_id.vmp_data)}")

    log.debug("Client ID:")
    log.debug(device.client_id)

    log.debug("VMP:")
    if device.client_id.vmp_data:
        file_hashes = FileHashes()
        file_hashes.ParseFromString(device.client_id.vmp_data)
        log.info(str(file_hashes))
    else:
        log.info("None")
