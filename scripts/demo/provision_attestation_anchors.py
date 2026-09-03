"""Purpose: Provision the OpenTitan attestation trust anchors for demonstration.

Directory: scripts/demo
Dependencies: standard library; app.hardware.opentitan
Connection: writes the simulated firmware fixture, its trusted digest into
            configs/hardware/opentitan.json, and the HMAC key into .env

DECLARED LIMITATION, recorded in both artefacts this script writes.

The OpenTitan attestation check has two trust anchors and this script creates both:

  1. trusted_firmware_digests - the SHA-256 the reported firmware_digest is checked
     against. It is derived from the fixture this script generates, so the image is
     being checked against a digest taken from itself.

  2. SEMISURE_OPENTITAN_VERIFICATION_KEY - the HMAC key the attestation signature is
     verified with. Any evidence signed with this key verifies, so the signature
     demonstrates that evidence was produced by something holding the key, not that it
     came from a device.

A real deployment would take the digest from a signed OpenTitan build artefact supplied
out of band by the silicon vendor, and would verify signatures against a public key whose
private half never leaves the device. Neither is available here.

The verification logic itself is unaffected and is exercised in both directions: a mutated
firmware image is rejected as UNTRUSTED_FIRMWARE, and tampered evidence is rejected as
INVALID_ATTESTATION_SIGNATURE.

KEY ENCODING. _decode_verification_key is imported from the adapter rather than
reimplemented. An earlier version of this script decoded bare hex while the adapter, which
requires a "hex:" or "base64:" prefix, fell through to UTF-8 - two different keys from one
string, and no signature could ever verify. One decoder, one place.

That fallback is itself a hazard worth naming: an unprefixed 64-character hex key is
silently accepted as 64 UTF-8 bytes, so a 32-byte key becomes a 64-byte key of half the
intended entropy and the length check still passes. This script always writes the prefix
and migrates an unprefixed value it finds.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.hardware.common import atomic_write_json, canonical_json, sha256_file  # noqa: E402
from app.hardware.opentitan.adapter import _decode_verification_key  # noqa: E402
from app.hardware.opentitan.schemas import OpenTitanEvidence  # noqa: E402

FIRMWARE_PATH = PROJECT_ROOT / "hardware_lab/opentitan/firmware/simulated_rom_image.json"
CONFIG_PATH = PROJECT_ROOT / "configs/hardware/opentitan.json"
ENV_PATH = PROJECT_ROOT / ".env"

ENV_KEY_NAME = "SEMISURE_OPENTITAN_VERIFICATION_KEY"

# PUFAdapter.from_project requires this and nothing provisioned it. The PUF identity
# hash is derived from it together with the config fingerprint, so rotating it or
# editing configs/hardware/puf.json changes every identity_hash and invalidates every
# digital twin that records one. Treat as a stable deployment constant.
PUF_SECRET_NAME = "SEMISURE_PUF_MASTER_SECRET"
KEY_PREFIX = "hex:"
KEY_BYTES = 32
MINIMUM_KEY_BYTES = 32

TRUST_ANCHOR_DISCLOSURE = (
    "The trusted digest below was derived from the generated fixture at "
    "hardware_lab/opentitan/firmware/simulated_rom_image.json, not from an "
    "independently supplied vendor image. The image is therefore checked against a "
    "digest taken from itself. The HMAC verification key is likewise generated locally, "
    "so any evidence signed with it verifies. A real deployment requires a signed "
    "firmware image produced by the OpenTitan build, with its digest supplied out of "
    "band by the silicon vendor, and signature verification against a device-held key "
    "whose private half is never exported."
)


def build_firmware_fixture() -> dict:
    """Return the declared simulated ROM image."""
    return {
        "artifact_type": "SIMULATED_FIRMWARE_IMAGE",
        "schema_version": "1.0",
        "provenance": {
            "source_type": "SIMULATED_FIRMWARE_IMAGE",
            "generated_by": "scripts/demo/provision_attestation_anchors.py",
            "physical_device_verified": False,
            "vendor_signed": False,
        },
        "trust_anchor_disclosure": {
            "digest_derived_from_this_file": True,
            "independently_supplied_vendor_image": False,
            "locally_generated_verification_key": True,
            "statement": TRUST_ANCHOR_DISCLOSURE,
        },
        "rom": {
            "device_family": "opentitan-earlgrey",
            "image_role": "rom_ext",
            "image_version": "0.0.0-simulated",
            "boot_stage": "ROM_EXT",
            "code_sections": [
                {"name": ".rom_ext_start", "size_bytes": 4096},
                {"name": ".rom_ext_text", "size_bytes": 32768},
                {"name": ".rom_ext_rodata", "size_bytes": 8192},
            ],
        },
    }


def read_env_lines() -> list[str]:
    """Return the .env file as lines, or an empty list when it does not exist."""
    if not ENV_PATH.exists():
        return []

    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def read_env_value(name: str) -> str | None:
    """Return the raw string assigned to name in .env, without interpreting it."""
    for line in read_env_lines():
        key, separator, value = line.partition("=")

        if separator and key.strip() == name:
            return value.strip()

    return None


def write_env_lines(lines: list[str]) -> None:
    """Replace .env atomically, preserving permissions. No backup file is written.

    A .env.bak would be untracked and NOT matched by the .gitignore entry for .env, which
    is an exact match. Leaving a copy of a secrets file in an unignored path is a worse
    outcome than the small risk this replacement carries, so it is done atomically instead.
    """
    handle, temporary = tempfile.mkstemp(
        prefix=".env.",
        dir=str(ENV_PATH.parent),
    )

    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines).rstrip("\n") + "\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.chmod(temporary, 0o600)
        os.replace(temporary, ENV_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def decoded_key_length(raw: str) -> int:
    """Return the length in bytes the adapter will derive from this raw value."""
    return len(_decode_verification_key(raw))


def load_verification_key() -> bytes:
    """Return the HMAC key exactly as the adapter derives it.

    Uses the adapter's own decoder so this script and the verifier cannot disagree about
    what a given string means.
    """
    raw = os.environ.get(ENV_KEY_NAME) or read_env_value(ENV_KEY_NAME)

    if not raw:
        raise SystemExit(f"{ENV_KEY_NAME} is not set")

    key = _decode_verification_key(raw)

    if len(key) < MINIMUM_KEY_BYTES:
        raise SystemExit(
            f"{ENV_KEY_NAME} decodes to {len(key)} bytes, "
            f"minimum is {MINIMUM_KEY_BYTES}"
        )

    return key


def provision_secret(name: str) -> tuple[int, str]:
    """Ensure a prefixed secret exists in .env. Returns (decoded byte length, action).

    Both SEMISURE_OPENTITAN_VERIFICATION_KEY and SEMISURE_PUF_MASTER_SECRET use the
    same hex:/base64:/UTF-8 convention and the same silent unprefixed fallback, so
    they are provisioned identically and always written with an explicit prefix.
    """
    existing = read_env_value(name)

    if existing:
        if existing.startswith(KEY_PREFIX) or existing.startswith("base64:"):
            return decoded_key_length(existing), "unchanged"

        # An unprefixed value is taken by the adapter as raw UTF-8. Where the value is
        # valid hexadecimal that is almost certainly not what was intended, so the prefix
        # is added. The value itself is not altered.
        try:
            bytes.fromhex(existing)
        except ValueError:
            return decoded_key_length(existing), "unchanged, not hexadecimal"

        migrated: list[str] = []

        for line in read_env_lines():
            key, separator, _ = line.partition("=")

            if separator and key.strip() == name:
                migrated.append(f"{name}={KEY_PREFIX}{existing}")
            else:
                migrated.append(line)

        write_env_lines(migrated)

        return decoded_key_length(f"{KEY_PREFIX}{existing}"), "migrated to hex: prefix"

    value = f"{KEY_PREFIX}{secrets.token_hex(KEY_BYTES)}"

    lines = read_env_lines()
    lines.extend(
        [
            "",
            f"# {name}. Locally generated: see the trust anchor disclosure in",
            "# scripts/demo/provision_attestation_anchors.py.",
            f"{name}={value}",
        ]
    )

    write_env_lines(lines)

    return decoded_key_length(value), "generated"


def mint_fixture_attestation(
    *,
    device_id: str,
    firmware_digest: str,
    counter: int,
    key: bytes,
    lifecycle_state: str = "PROD",
) -> dict:
    """Return signed OpenTitan evidence for the simulated fixture.

    Shared with the demonstration minting script so the signing construction exists in
    exactly one place: canonical JSON of every field except signature, HMAC-SHA256.
    """
    evidence = OpenTitanEvidence(
        device_id=device_id,
        lifecycle_state=lifecycle_state,
        boot_stage="ROM_EXT",
        rom_digest=hashlib.sha256(f"simulated-rom:{device_id}".encode()).hexdigest(),
        firmware_digest=firmware_digest,
        otp_digest=hashlib.sha256(f"simulated-otp:{device_id}".encode()).hexdigest(),
        monotonic_counter=counter,
        nonce=secrets.token_hex(24),
        signature="",
        certificate_chain=tuple(),
        timestamp_utc=datetime.now(UTC).isoformat(timespec="seconds"),
    )

    payload = evidence.to_dict()
    payload.pop("signature")

    document = evidence.to_dict()
    document["signature"] = hmac.new(
        key,
        canonical_json(payload),
        hashlib.sha256,
    ).hexdigest()

    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision OpenTitan attestation anchors.")
    parser.add_argument("--force", action="store_true", help="regenerate the firmware fixture")
    args = parser.parse_args()

    if FIRMWARE_PATH.exists() and not args.force:
        print(f"fixture exists    : {FIRMWARE_PATH.relative_to(PROJECT_ROOT)}")
    else:
        FIRMWARE_PATH.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(FIRMWARE_PATH, build_firmware_fixture(), mode=0o644)
        print(f"fixture written   : {FIRMWARE_PATH.relative_to(PROJECT_ROOT)}")

    digest = sha256_file(FIRMWARE_PATH)
    print(f"firmware digest   : {digest}")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["trusted_firmware_digests"] = [digest]
    config["trusted_firmware_digests_disclosure"] = TRUST_ANCHOR_DISCLOSURE
    config["trusted_firmware_digests_source"] = str(
        FIRMWARE_PATH.relative_to(PROJECT_ROOT)
    )
    atomic_write_json(CONFIG_PATH, config, mode=0o644)
    print(f"config updated    : {CONFIG_PATH.relative_to(PROJECT_ROOT)}")

    for label, name in (
        ("attestation key", ENV_KEY_NAME),
        ("puf master     ", PUF_SECRET_NAME),
    ):
        length, action = provision_secret(name)
        print(f"{label}   : {action}, decodes to {length} bytes")

    print("\nTRUST ANCHOR DISCLOSURE")
    print(TRUST_ANCHOR_DISCLOSURE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
