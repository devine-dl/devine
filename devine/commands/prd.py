import logging
from pathlib import Path
from secrets import token_bytes
from typing import Optional

import click
import requests
from pyplayready.cdm import Cdm
from pyplayready.crypto.ecc_key import ECCKey
from pyplayready.device import Device
from pyplayready.exceptions import InvalidCertificateChain, OutdatedDevice
from pyplayready.system.bcert import Certificate, CertificateChain
from pyplayready.system.pssh import PSSH

from devine.core.config import config
from devine.core.constants import context_settings



@click.group(
    short_help="Manage creation of PRD (Playready Device) files.",
    context_settings=context_settings,
)
def prd() -> None:
    """Manage creation of PRD (Playready Device) files."""


@prd.command()
@click.argument("paths", type=Path, nargs=-1)
@click.option(
    "-e",
    "--encryption_key",
    type=Path,
    required=False,
    help="Optional Device ECC private encryption key",
)
@click.option(
    "-s",
    "--signing_key",
    type=Path,
    required=False,
    help="Optional Device ECC private signing key",
)
@click.option("-o", "--output", type=Path, default=None, help="Output Directory")
@click.pass_context
def new(
    ctx: click.Context,
    paths: tuple[Path, ...],
    encryption_key: Optional[Path],
    signing_key: Optional[Path],
    output: Optional[Path],
) -> None:
    """Create a new .PRD PlayReady Device file.

    Accepts either paths to a group key and certificate or a single directory
    containing ``zgpriv.dat`` and ``bgroupcert.dat``.
    """
    if len(paths) == 1 and paths[0].is_dir():
        device_dir = paths[0]
        group_key = device_dir / "zgpriv.dat"
        group_certificate = device_dir / "bgroupcert.dat"
        if not group_key.is_file() or not group_certificate.is_file():
            raise click.UsageError(
                "Folder must contain zgpriv.dat and bgroupcert.dat", ctx
            )
    elif len(paths) == 2:
        group_key, group_certificate = paths
        if not group_key.is_file():
            raise click.UsageError(
                "group_key: Not a path to a file, or it doesn't exist.", ctx
            )
        if not group_certificate.is_file():
            raise click.UsageError(
                "group_certificate: Not a path to a file, or it doesn't exist.", ctx
            )
        device_dir = None
    else:
        raise click.UsageError(
            "Provide either a folder path or paths to group_key and group_certificate",
            ctx,
        )
    if encryption_key and not encryption_key.is_file():
        raise click.UsageError(
            "encryption_key: Not a path to a file, or it doesn't exist.", ctx
        )
    if signing_key and not signing_key.is_file():
        raise click.UsageError(
            "signing_key: Not a path to a file, or it doesn't exist.", ctx
        )

    log = logging.getLogger("prd")

    encryption_key_obj = (
        ECCKey.load(encryption_key) if encryption_key else ECCKey.generate()
    )
    signing_key_obj = (
        ECCKey.load(signing_key) if signing_key else ECCKey.generate()
    )

    group_key_obj = ECCKey.load(group_key)
    certificate_chain = CertificateChain.load(group_certificate)

    if certificate_chain.get(0).get_issuer_key() != group_key_obj.public_bytes():
        raise InvalidCertificateChain("Group key does not match this certificate")

    new_certificate = Certificate.new_leaf_cert(
        cert_id=token_bytes(16),
        security_level=certificate_chain.get_security_level(),
        client_id=token_bytes(16),
        signing_key=signing_key_obj,
        encryption_key=encryption_key_obj,
        group_key=group_key_obj,
        parent=certificate_chain,
    )
    certificate_chain.prepend(new_certificate)
    certificate_chain.verify()

    device = Device(
        group_key=group_key_obj.dumps(),
        encryption_key=encryption_key_obj.dumps(),
        signing_key=signing_key_obj.dumps(),
        group_certificate=certificate_chain.dumps(),
    )

    if output and output.suffix:
        if output.suffix.lower() != ".prd":
            log.warning(
                "Saving PRD with the file extension '%s' but '.prd' is recommended.",
                output.suffix,
            )
        out_path = output
    else:
        out_dir = output or (device_dir or config.directories.prds)
        out_path = out_dir / f"{device.get_name()}.prd"

    if out_path.exists():
        log.error("A file already exists at the path '%s', cannot overwrite.", out_path)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(device.dumps())

    log.info("Created Playready Device (.prd) file, %s", out_path.name)
    log.info(" + Security Level: %s", device.security_level)
    log.info(" + Group Key: %s bytes", len(device.group_key.dumps()))
    log.info(" + Encryption Key: %s bytes", len(device.encryption_key.dumps()))
    log.info(" + Signing Key: %s bytes", len(device.signing_key.dumps()))
    log.info(" + Group Certificate: %s bytes", len(device.group_certificate.dumps()))
    log.info(" + Saved to: %s", out_path.absolute())


@prd.command(name="reprovision")
@click.argument("prd_path", type=Path)
@click.option(
    "-e",
    "--encryption_key",
    type=Path,
    required=False,
    help="Optional Device ECC private encryption key",
)
@click.option(
    "-s",
    "--signing_key",
    type=Path,
    required=False,
    help="Optional Device ECC private signing key",
)
@click.option("-o", "--output", type=Path, default=None, help="Output Path or Directory")
@click.pass_context
def reprovision_device(
    ctx: click.Context,
    prd_path: Path,
    encryption_key: Optional[Path],
    signing_key: Optional[Path],
    output: Optional[Path] = None,
) -> None:
    """Reprovision a Playready Device (.prd) file."""
    if not prd_path.is_file():
        raise click.UsageError("prd_path: Not a path to a file, or it doesn't exist.", ctx)

    log = logging.getLogger("prd")
    log.info("Reprovisioning Playready Device (.prd) file, %s", prd_path.name)

    device = Device.load(prd_path)

    if device.group_key is None:
        raise OutdatedDevice(
            "Device does not support reprovisioning, re-create it or use a Device with a version of 3 or higher"
        )

    device.group_certificate.remove(0)

    encryption_key_obj = ECCKey.load(encryption_key) if encryption_key else ECCKey.generate()
    signing_key_obj = ECCKey.load(signing_key) if signing_key else ECCKey.generate()

    device.encryption_key = encryption_key_obj
    device.signing_key = signing_key_obj

    new_certificate = Certificate.new_leaf_cert(
        cert_id=token_bytes(16),
        security_level=device.group_certificate.get_security_level(),
        client_id=token_bytes(16),
        signing_key=signing_key_obj,
        encryption_key=encryption_key_obj,
        group_key=device.group_key,
        parent=device.group_certificate,
    )
    device.group_certificate.prepend(new_certificate)

    if output and output.suffix:
        if output.suffix.lower() != ".prd":
            log.warning(
                "Saving PRD with the file extension '%s' but '.prd' is recommended.",
                output.suffix,
            )
        out_path = output
    else:
        out_path = prd_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(device.dumps())

    log.info("Reprovisioned Playready Device (.prd) file, %s", out_path.name)


@prd.command()
@click.argument("device", type=Path)
@click.option(
    "-c",
    "--ckt",
    type=click.Choice(["aesctr", "aescbc"], case_sensitive=False),
    default="aesctr",
    help="Content Key Encryption Type",
)
@click.option(
    "-sl",
    "--security-level",
    type=click.Choice(["150", "2000", "3000"], case_sensitive=False),
    default="2000",
    help="Minimum Security Level",
)
@click.pass_context
def test(
    ctx: click.Context,
    device: Path,
    ckt: str,
    security_level: str,
) -> None:
    """Test a Playready Device on the Microsoft demo server."""

    if not device.is_file():
        raise click.UsageError("device: Not a path to a file, or it doesn't exist.", ctx)

    log = logging.getLogger("prd")

    prd_device = Device.load(device)
    log.info("Loaded Device: %s", prd_device.get_name())

    cdm = Cdm.from_device(prd_device)
    log.info("Loaded CDM")

    session_id = cdm.open()
    log.info("Opened Session")

    pssh_b64 = (
        "AAADfHBzc2gAAAAAmgTweZhAQoarkuZb4IhflQAAA1xcAwAAAQABAFIDPABXAFIATQBIAEUAQQBEAEUAUgAgAHgAbQBsAG4AcwA9ACIAaAB0AHQAcAA6AC8ALwBzAGMAaABlAG0AYQBzAC4AbQBpAGMAcgBvAHMAbwBmAHQALgBjAG8AbQAvAEQAUgBNAC8AMgAwADAANwAvADAAMwAvAFAAbABhAHkAUgBlAGEAZAB5AEgAZQBhAGQAZQByACIAIAB2AGUAcgBzAGkAbwBuAD0AIgA0AC4AMAAuADAALgAwACIAPgA8AEQAQQBUAEEAPgA8AFAAUgBPAFQARQBDAFQASQBOAEYATwA+ADwASwBFAFkATABFAE4APgAxADYAPAAvAEsARQBZAEwARQBOAD4APABBAEwARwBJAEQAPgBBAEUAUwBDAFQAUgA8AC8AQQBMAEcASQBEAD4APAAvAFAAUgBPAFQARQBDAFQASQBOAEYATwA+ADwASwBJAEQAPgA0AFIAcABsAGIAKwBUAGIATgBFAFMAOAB0AEcAawBOAEYAVwBUAEUASABBAD0APQA8AC8ASwBJAEQAPgA8AEMASABFAEMASwBTAFUATQA+AEsATABqADMAUQB6AFEAUAAvAE4AQQA9ADwALwBDAEgARQBDAEsAUwBVAE0APgA8AEwAQQBfAFUAUgBMAD4AaAB0AHQAcABzADoALwAvAHAAcgBvAGYAZgBpAGMAaQBhAGwAcwBpAHQAZQAuAGsAZQB5AGQAZQBsAGkAdgBlAHIAeQAuAG0AZQBkAGkAYQBzAGUAcgB2AGkAYwBlAHMALgB3AGkAbgBkAG8AdwBzAC4AbgBlAHQALwBQAGwAYQB5AFIAZQBhAGQAeQAvADwALwBMAEEAXwBVAFIATAA+ADwAQwBVAFMAVABPAE0AQQBUAFQAUgBJAEIAVQBUAEUAUwA+ADwASQBJAFMAXwBEAFIATQBfAFYARQBSAFMASQBPAE4APgA4AC4AMQAuADIAMwAwADQALgAzADEAPAAvAEkASQBTAF8ARABSAE0AXwBWAEUAUgBTAEkATwBOAD4APAAvAEMAVQBTAFQATwBNAEEAVABUAFIASQBCAFUAVABFAFMAPgA8AC8ARABBAFQAQQA+ADwALwBXAFIATQBIAEUAQQBEAEUAUgA+AA=="
    )
    pssh = PSSH(pssh_b64)

    challenge = cdm.get_license_challenge(session_id, pssh.wrm_headers[0])
    log.info("Created License Request")

    license_server = (
        f"https://test.playready.microsoft.com/service/rightsmanager.asmx?cfg=(persist:false,sl:{security_level},ckt:{ckt})"
    )

    response = requests.post(
        url=license_server,
        headers={"Content-Type": "text/xml; charset=UTF-8"},
        data=challenge,
    )

    cdm.parse_license(session_id, response.text)
    log.info("License Parsed Successfully")

    for key in cdm.get_keys(session_id):
        log.info(f"{key.key_id.hex}:{key.key.hex()}")

    cdm.close(session_id)
    log.info("Closed Session")
