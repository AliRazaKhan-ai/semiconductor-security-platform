"""Prevent maintenance scripts from deleting Fabric runtime resources."""

from pathlib import Path


def test_safe_cleanup_does_not_prune_containers_or_volumes() -> None:
    source = Path(
        "scripts/maintenance/safe_cleanup.sh"
    ).read_text(encoding="utf-8")

    assert "docker container prune" not in source
    assert "docker volume prune" not in source


def test_runtime_startup_verifies_existing_fabric_ledger() -> None:
    source = Path(
        "scripts/runtime/start_everything.sh"
    ).read_text(encoding="utf-8")

    assert "./scripts/runtime/verify_fabric.sh" in source
    assert "network.sh createChannel" not in source
    assert "network.sh deployCC" not in source
