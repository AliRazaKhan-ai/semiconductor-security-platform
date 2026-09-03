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
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.hardware.common import atomic_write_json, canonical_json, sha256_file  # noqa: E402
from app.hardware.opentitan.schemas import OpenTitanEvidence  # noqa: E402

FIRMWARE_PATH = PROJECT_ROOT / "hardware_lab/opentitan/firmware/simulated_rom_image.json"
CONFIG_PATH = PROJECT_ROOT / "configs/hardware/opentitan.json"
ENV_PATH = PROJECT_ROOT / ".env"

ENV_KEY_NAME = "SEMISURE_OPENTITAN_VERIFICATION_KEY"
KEY_BYTES = 48

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
    rom_payload = {
        "device_family": "opentitan-earlgrey",
        "image_role": "rom_ext",
        "image_version": "0.0.0-simulated",
        "boot_stage": "ROM_EXT",
        "code_sections": [
            {"name": ".rom_ext_start", "size_bytes": 4096},
            {"name": ".rom_ext_text", "size_bytes": 32768},
            {"name": ".rom_ext_rodata", "size_bytes": 8192},
        ],
    }

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
        "rom": rom_payload,
    }


def load_verification_key() -> bytes:
    """Return the configured HMAC key from the environment or .env."""
    import os

    value = os.environ.get(ENV_KEY_NAME)

    if not value and ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            name, separator, candidate = line.partition("=")
            if separator and name.strip() == ENV_KEY_NAME:
                value = candidate.strip()
                break

    if not value:
        raise SystemExit(f"{ENV_KEY_NAME} is not set; run this script without --verify-only")

    key = bytes.fromhex(value) if len(value) % 2 == 0 and all(
        character in "0123456789abcdefABCDEF" for character in value
    ) else value.encode("utf-8")

    if len(key) < 32:
        raise SystemExit(f"{ENV_KEY_NAME} must be at least 32 bytes, got {len(key)}")

    return key


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
    signature = hmac.new(key, canonical_json(payload), hashlib.sha256).hexdigest()

    document = evidence.to_dict()
    document["signature"] = signature
    return document


def write_env_key() -> int:
    """Generate the verification key into .env if absent. Returns its length in bytes."""
    existing = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""

    for line in existing.splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == ENV_KEY_NAME and value.strip():
            return len(bytes.fromhex(value.strip()))

    key_hex = secrets.token_hex(KEY_BYTES)

    with ENV_PATH.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(f"# OpenTitan attestation HMAC key. Locally generated: see\n")
        handle.write(f"# scripts/demo/provision_attestation_anchors.py trust anchor disclosure.\n")
        handle.write(f"{ENV_KEY_NAME}={key_hex}\n")

    ENV_PATH.chmod(0o600)
    return KEY_BYTES


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

    key_length = write_env_key()
    print(f"verification key  : present in .env, {key_length} bytes")

    print("\nTRUST ANCHOR DISCLOSURE")
    print(TRUST_ANCHOR_DISCLOSURE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
