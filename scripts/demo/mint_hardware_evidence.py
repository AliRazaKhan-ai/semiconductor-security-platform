"""Purpose: Mint the hardware evidence each chip fixture's manifest declares.

Directory: scripts/demo
Dependencies: app.hardware.{yosys,puf,sbom,digital_twin,chipwhisperer}; provision_attestation_anchors
Connection: writes traces, attestation, twins and the hardware_manifest block consumed by
            IntegratedPipelineService via build_hardware_manifest

RTL ASSIGNMENT. Which RTL a fixture represents is a fixture-authoring fact, not a pipeline
conclusion. chip_02 is defined as the fixture standing for a chip fabricated from the
Trojan-inserted RTL, exactly as its rare_net_ratio was authored. The assignment is declared
below, keyed on filename, and is NOT derived from the fixture's scenario field. The
analysis downstream never sees the label: synthesis_trace.generate_samples is a pure
function of (yosys_metrics, device_seed, channel), verified by crossing those inputs.

SCOPING. Only two RTL designs exist: hardware_lab/rtl/reference/semisecure_demo_core.sv and
its controlled-Trojan variant. Two fixtures therefore carry fixture-specific netlists. The
other six exercise supply-chain, compliance and PUF controls and have no distinct RTL, so
their candidate netlist IS the reference. Their measured netlist_delta_ratio is 0.0 because
the two sides are the same artefact, not because a distinct design was measured and found
identical. That distinction is recorded in the artefacts, and an assertion at the end of
the run fails if the two markers recording it ever disagree.

DEVICE SEEDS. sha256(chip_id)[:16]. A readable seed such as CHIP-PROD-TROJAN-002 carries the
verdict in its name; the generator cannot read it as anything but a string, but a reader
would have to take that on trust. The hashed form is visibly incapable of carrying a label
and remains reproducible from the chip_id in one command, recorded in every manifest.

FRESHNESS. OpenTitan attestation expires 300 seconds after minting and its counter cannot
be reused, so this script must be run immediately before the pipeline. Counters advance
from the recorded replay state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.hardware.chipwhisperer.synthesis_trace import build_trace_document  # noqa: E402
from app.hardware.common import atomic_write_json, sha256_file  # noqa: E402
from app.hardware.digital_twin.service import DigitalTwinService  # noqa: E402
from app.hardware.puf.adapter import PUFAdapter  # noqa: E402
from app.hardware.sbom.generator import SBOMGenerator  # noqa: E402
from app.hardware.yosys.adapter import YosysAdapter  # noqa: E402
from scripts.demo.provision_attestation_anchors import (  # noqa: E402
    FIRMWARE_PATH,
    load_verification_key,
    mint_fixture_attestation,
)

CHIPS_DIR = PROJECT_ROOT / "data/chips"
TRACE_DIR = PROJECT_ROOT / "hardware_lab/chipwhisperer/reference_traces"
ATTESTATION_DIR = PROJECT_ROOT / "hardware_lab/opentitan/attestation"
REPLAY_STATE = PROJECT_ROOT / "data/hardware/opentitan-replay.json"

REFERENCE_RTL = Path("hardware_lab/rtl/reference/semisecure_demo_core.sv")
TROJAN_RTL = Path("hardware_lab/rtl/controlled_trojan/semisecure_demo_core_trojan.sv")
TESTBENCH = Path("hardware_lab/verilator/testbenches/tb_semisecure_demo_core.sv")
# Yosys synthesises the design under test; Verilator elaborates the testbench that
# drives it. They are different modules and were previously collapsed into one
# constant, which built a design with no stimulus and produced no simulation output.
# The Verilator top is read from the RTL evidence manifests so the two cannot drift.
SYNTHESIS_TOP_MODULE = "semisecure_demo_core"
RTL_MANIFEST_DIR = PROJECT_ROOT / "hardware_lab/rtl/manifests"
REFERENCE_MANIFEST = "clean_rtl_evidence.json"
TROJAN_MANIFEST = "controlled_trojan_rtl_evidence.json"


def verilator_top_module(manifest_name: str) -> str:
    """Return the Verilator top module declared by an RTL evidence manifest."""
    import json as _json
    manifest = _json.loads((RTL_MANIFEST_DIR / manifest_name).read_text(encoding="utf-8"))
    top = str(manifest.get("verilator_top_module") or "").strip()
    if not top:
        raise MintError(f"{manifest_name} declares no verilator_top_module")
    return top

FIXTURE_SPECIFIC = "FIXTURE_SPECIFIC_NETLIST"
REFERENCE_SCOPED = "REFERENCE_NETLIST_NO_DISTINCT_RTL"
MEASURED = "MEASURED_REFERENCE_DIFFERENTIAL"
BY_CONSTRUCTION = "BY_CONSTRUCTION_NO_DISTINCT_RTL"

# Keyed on filename, never on the fixture's scenario field. rtl is what the fixture is
# defined to represent; scoped_evidence names the controls it exercises and is the single
# source for the coverage column in the summary table.
FIXTURES: dict[str, dict[str, Any]] = {
    "chip_01_good.json": {
        "rtl": REFERENCE_RTL,
        "scoped_evidence": "side-channel / baseline",
    },
    "chip_02_trojan.json": {
        "rtl": TROJAN_RTL,
        "scoped_evidence": "side-channel / hardware trojan",
    },
    "chip_03_puf_unstable.json": {
        "rtl": REFERENCE_RTL,
        "scoped_evidence": "PUF authentication; not a side-channel threat model",
    },
    "chip_04_supplychain_tampered.json": {
        "rtl": REFERENCE_RTL,
        "scoped_evidence": "supply-chain integrity; not a side-channel threat model",
    },
    "chip_05_highrisk_supplier.json": {
        "rtl": REFERENCE_RTL,
        "scoped_evidence": "supplier risk scoring; not a side-channel threat model",
    },
    "chip_06_counterfeit.json": {
        "rtl": REFERENCE_RTL,
        "scoped_evidence": "provenance / counterfeit; not a side-channel threat model",
    },
    "chip_07_sanctioned_manufacturer.json": {
        "rtl": REFERENCE_RTL,
        "scoped_evidence": "export control / compliance; not a side-channel threat model",
    },
    "chip_08_fake_provenance.json": {
        "rtl": REFERENCE_RTL,
        "scoped_evidence": "blockchain provenance; not a side-channel threat model",
    },
}


class MintError(RuntimeError):
    """Raised when a fixture cannot be minted."""


def device_seed(chip_id: str) -> str:
    """Return the derived device seed. Reproducible from the chip_id alone."""
    return hashlib.sha256(chip_id.encode("utf-8")).hexdigest()[:16]


def next_counter(device_id: str) -> int:
    """Return a monotonic counter above any value already accepted for this device."""
    if not REPLAY_STATE.exists():
        return 1

    try:
        state = json.loads(REPLAY_STATE.read_text(encoding="utf-8"))
        record = state.get("devices", {}).get(device_id) or {}
        return int(record.get("highest_counter", 0)) + 1
    except (json.JSONDecodeError, TypeError, ValueError):
        return 1


def relative(path: Path) -> str:
    """Return a project-root-relative path string for the manifest.

    Manifests must never carry an absolute path. build_hardware_manifest resolves
    relative entries against the project root, so an absolute one embeds the author's
    home directory in a committed fixture and breaks on any other machine.
    """
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError as exc:
        raise MintError(f"artefact is outside the project root: {resolved}") from exc


def mint_fixture(
    filename: str,
    assignment: dict[str, Any],
    *,
    yosys: YosysAdapter,
    puf: PUFAdapter,
    twins: DigitalTwinService,
    sbom: SBOMGenerator,
    key: bytes,
    firmware_digest: str,
) -> dict[str, Any]:
    """Mint every artefact one fixture declares and write its hardware_manifest."""
    fixture_path = CHIPS_DIR / filename
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    chip_id = str(fixture.get("chip_id") or fixture.get("chip", {}).get("chip_id") or "")

    if not chip_id:
        raise MintError(f"{filename}: no chip_id")

    seed = device_seed(chip_id)
    rtl = PROJECT_ROOT / assignment["rtl"]
    fixture_specific = assignment["rtl"] != REFERENCE_RTL

    # Reference-differential synthesis. For the six without distinct RTL the candidate and
    # the reference are the same file, so the measured delta is 0.0 for that reason.
    result, report = yosys.analyse_against_reference(
        rtl,
        PROJECT_ROOT / REFERENCE_RTL,
        SYNTHESIS_TOP_MODULE,
    )

    yosys_payload = result.to_dict()
    candidate_metrics = report["candidate_metrics"]
    reference_metrics = report["reference_metrics"]
    measured_ratio = float(report["netlist_delta_ratio"])

    netlist_source = FIXTURE_SPECIFIC if fixture_specific else REFERENCE_SCOPED
    derivation = MEASURED if fixture_specific else BY_CONSTRUCTION

    # Four traces. The candidate side derives from the candidate netlist's metrics, the
    # reference side from the reference netlist's, so the pair mirrors the structural
    # comparison rather than differing only by seed.
    trace_dir = TRACE_DIR / chip_id
    trace_dir.mkdir(parents=True, exist_ok=True)

    trace_paths: dict[str, Path] = {}

    channels = (
        ("side_channel_trace", "power", candidate_metrics, seed),
        ("side_channel_reference", "power", reference_metrics, device_seed("reference")),
        ("ai_em_trace", "em", candidate_metrics, seed),
        ("ai_timing_trace", "timing", candidate_metrics, seed),
    )

    for manifest_key, channel, metrics, trace_seed in channels:
        document = build_trace_document(
            metrics=metrics,
            device_seed=trace_seed,
            channel=channel,
            netlist_digest=str(yosys_payload["netlist_digest"]),
        )

        document["provenance"]["netlist_source"] = (
            netlist_source
            if manifest_key != "side_channel_reference"
            else FIXTURE_SPECIFIC
        )
        document["provenance"]["scoped_evidence"] = assignment["scoped_evidence"]
        document["provenance"]["device_seed"] = trace_seed
        document["provenance"]["device_seed_source"] = "sha256(chip_id)[:16]"

        path = trace_dir / f"{manifest_key}.json"
        atomic_write_json(path, document, mode=0o644)
        trace_paths[manifest_key] = path

    # Fresh attestation. Counter advances beyond anything already accepted.
    ATTESTATION_DIR.mkdir(parents=True, exist_ok=True)
    attestation_path = ATTESTATION_DIR / f"{chip_id}.json"
    atomic_write_json(
        attestation_path,
        mint_fixture_attestation(
            device_id=chip_id,
            firmware_digest=firmware_digest,
            counter=next_counter(chip_id),
            key=key,
        ),
        mode=0o644,
    )

    profile = puf.enroll_device(chip_id, replace=True)

    # SBOM over the design sources, the firmware image and every trace the verification
    # consumed. Substituting any of them after enrolment changes sbom_digest and fails the
    # twin, which is the binding this scope was chosen for.
    sbom_artifacts = [
        rtl,
        PROJECT_ROOT / TESTBENCH,
        FIRMWARE_PATH,
        *trace_paths.values(),
    ]

    sbom_result = sbom.generate(
        chip_id=chip_id,
        artifacts=sbom_artifacts,
        output=PROJECT_ROOT / "data/sbom" / f"{chip_id}.mint.cdx.json",
    )

    twin_id = f"TWIN-{chip_id}"
    twin_path = twins.repository.path(twin_id)
    twin_path.unlink(missing_ok=True)

    manufacturing = fixture.get("manufacturing", {}) or {}
    supplier = fixture.get("supplier", {}) or {}

    twins.create(
        twin_id=twin_id,
        chip_id=chip_id,
        manufacturer=str(manufacturing.get("fabrication_facility", "unknown")),
        supplier_id=str(supplier.get("supplier_id", "unknown")),
        lot_id=str(manufacturing.get("lot_id", "unknown")),
        serial_number=str(manufacturing.get("serial_number", "unknown")),
        puf_identity_hash=profile.identity_hash,
        rtl_digest=str(yosys_payload["rtl_digest"]),
        netlist_digest=str(yosys_payload["netlist_digest"]),
        firmware_digest=firmware_digest,
        sbom_digest=sbom_result.document_digest,
        lifecycle_state="PROD",
        custody_hashes=tuple(),
    )

    fixture["hardware_manifest"] = {
        "opentitan_evidence": relative(attestation_path),
        "side_channel_trace": relative(trace_paths["side_channel_trace"]),
        "side_channel_reference": relative(trace_paths["side_channel_reference"]),
        "ai_em_trace": relative(trace_paths["ai_em_trace"]),
        "ai_timing_trace": relative(trace_paths["ai_timing_trace"]),
        "rtl_file": relative(rtl),
        "reference_rtl_file": str(REFERENCE_RTL),
        "testbench_file": str(TESTBENCH),
        # Yosys synthesises the design; Verilator elaborates the testbench that drives
        # it. Two stages previously read one "top_module" key, so fixing either broke
        # the other. Each now names its own module and the contract requires both.
        "top_module": SYNTHESIS_TOP_MODULE,
        "verilator_top_module": verilator_top_module(
            TROJAN_MANIFEST if fixture_specific else REFERENCE_MANIFEST
        ),
        "sbom_artifacts": [relative(path) for path in sbom_artifacts],
        "puf_identity_hash": profile.identity_hash,
        "twin_id": twin_id,
        "device_seed": seed,
        "device_seed_source": "sha256(chip_id)[:16]",
        "device_seed_verification_command": (
            "python3 -c \"import hashlib,sys; "
            "print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])\" "
            f"{chip_id}"
        ),
        # Declarative scoping metadata. NOT consumed by the pipeline, which measures the
        # delta itself at run time from the netlists named above.
        "structural_scoping": {
            "netlist_source": netlist_source,
            "netlist_delta_ratio": measured_ratio,
            "derivation": derivation,
            "statement": (
                "Candidate and reference are the same artefact because no distinct RTL "
                "exists for this fixture, so the 0.0 delta is uninformative rather than a "
                "measurement of two designs found identical."
                if not fixture_specific
                else "Measured by differential synthesis of a distinct candidate netlist "
                "against the reference."
            ),
        },
        "scoped_evidence": assignment["scoped_evidence"],
    }

    atomic_write_json(fixture_path, fixture, mode=0o644)

    return {
        "chip_id": chip_id,
        "filename": filename,
        "device_seed": seed,
        "candidate_metrics": candidate_metrics,
        "reference_metrics": reference_metrics,
        "netlist_delta_ratio": measured_ratio,
        "netlist_source": netlist_source,
        "derivation": derivation,
        "scoped_evidence": assignment["scoped_evidence"],
        "sbom_digest": sbom_result.document_digest,
        "puf_identity_hash": profile.identity_hash,
        "twin_id": twin_id,
        "trace_paths": {key: str(path) for key, path in trace_paths.items()},
    }


def assert_markers_agree(minted: list[dict[str, Any]]) -> list[str]:
    """Return failures where the two scoping markers disagree.

    Two fields record one scoping fact and can drift apart in a later edit. A run that
    fails when they disagree is what stops a constructed 0.0 being presented as a measured
    one, in either direction.
    """
    failures: list[str] = []

    for record in minted:
        source = record["netlist_source"]
        derivation = record["derivation"]
        ratio = record["netlist_delta_ratio"]
        chip = record["chip_id"]

        if source == REFERENCE_SCOPED:
            if derivation != BY_CONSTRUCTION:
                failures.append(f"{chip}: {source} but derivation is {derivation}")
            if ratio != 0.0:
                failures.append(f"{chip}: {source} but netlist_delta_ratio is {ratio}")
        elif source == FIXTURE_SPECIFIC:
            if derivation != MEASURED:
                failures.append(f"{chip}: {source} but derivation is {derivation}")
        else:
            failures.append(f"{chip}: unknown netlist_source {source!r}")

        if derivation == BY_CONSTRUCTION and source != REFERENCE_SCOPED:
            failures.append(f"{chip}: {derivation} but netlist_source is {source}")

    return failures


def anomaly_table(minted: list[dict[str, Any]]) -> None:
    """Print candidate-against-reference anomaly scores before any verdict.

    The coverage column is read back from each fixture's written trace provenance, so the
    table and the artefacts cannot disagree.
    """
    from app.hardware.chipwhisperer.adapter import ChipWhispererAdapter

    adapter = ChipWhispererAdapter.from_project(PROJECT_ROOT)

    print("\n=== side-channel anomaly scores, candidate against reference ===")
    print(f"{'chip_id':<28} {'anomaly':>8} {'thresh':>7}  {'status':<10} evidences")
    print("-" * 108)

    rows = []

    for record in minted:
        candidate = Path(record["trace_paths"]["side_channel_trace"])
        reference = Path(record["trace_paths"]["side_channel_reference"])
        provenance = json.loads(candidate.read_text(encoding="utf-8"))["provenance"]

        result = adapter.analyse_files(candidate, reference)

        rows.append((record["chip_id"], result, provenance["scoped_evidence"]))

    # Baseline fixtures first so the separation is read against a stated floor.
    rows.sort(key=lambda row: 0 if "baseline" in row[2] else (2 if "trojan" in row[2] else 1))

    for chip, result, evidence in rows:
        print(
            f"{chip:<28} {result.anomaly_score:>8.4f} {result.threshold:>7.2f}  "
            f"{result.status:<10} {evidence}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Mint hardware evidence for every chip fixture.")
    parser.add_argument("--only", default=None, help="mint a single fixture filename")
    args = parser.parse_args()

    key = load_verification_key()
    firmware_digest = sha256_file(FIRMWARE_PATH)

    yosys = YosysAdapter.from_project(PROJECT_ROOT)
    puf = PUFAdapter.from_project(PROJECT_ROOT)
    twins = DigitalTwinService.from_project(PROJECT_ROOT)
    sbom = SBOMGenerator()

    selected = {
        name: assignment
        for name, assignment in FIXTURES.items()
        if args.only is None or name == args.only
    }

    if not selected:
        print(f"FAIL: no fixture named {args.only}", file=sys.stderr)
        return 2

    minted: list[dict[str, Any]] = []

    for name, assignment in selected.items():
        print(f"minting {name} ...", flush=True)
        minted.append(
            mint_fixture(
                name,
                assignment,
                yosys=yosys,
                puf=puf,
                twins=twins,
                sbom=sbom,
                key=key,
                firmware_digest=firmware_digest,
            )
        )

    print("\n=== netlist scoping ===")
    print(f"{'chip_id':<28} {'cells':>6} {'delta':>7}  {'source':<36} derivation")
    print("-" * 118)
    for record in minted:
        print(
            f"{record['chip_id']:<28} {record['candidate_metrics']['cells']:>6} "
            f"{record['netlist_delta_ratio']:>7.4f}  {record['netlist_source']:<36} "
            f"{record['derivation']}"
        )

    failures = assert_markers_agree(minted)

    print("\n=== scoping marker consistency ===")
    if failures:
        for failure in failures:
            print(f"  FAIL {failure}", file=sys.stderr)
        print(f"\n{len(failures)} marker disagreements. The artefacts are inconsistent.", file=sys.stderr)
        return 3
    print(f"  PASS: {len(minted)}/{len(minted)} fixtures, both markers agree")

    anomaly_table(minted)

    print("\n=== minted ===")
    for record in minted:
        print(f"  {record['chip_id']:<28} twin {record['twin_id']}")
        print(f"  {'':<28} sbom {record['sbom_digest']}")
        print(f"  {'':<28} puf  {record['puf_identity_hash']}")

    print(
        "\nOpenTitan attestation expires 300 seconds after minting and its counter cannot "
        "be reused.\nRun the pipeline now, or re-run this script before demonstrating."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
