from pathlib import Path

from app.pipeline.runtime_store import PipelineRuntimeStore


def test_runtime_store_saves_and_loads_run(
    tmp_path: Path,
) -> None:
    store = PipelineRuntimeStore(tmp_path)
    store.save_run(
        "scan-test-12345678",
        {
            "scan_id": "scan-test-12345678",
            "status": "RUNNING",
        },
    )

    loaded = store.load_run(
        "scan-test-12345678"
    )

    assert loaded["status"] == "RUNNING"


def test_runtime_store_indexes_file_hash(
    tmp_path: Path,
) -> None:
    store = PipelineRuntimeStore(tmp_path)
    store.register_file_hash(
        "a" * 64,
        "scan-test-12345678",
    )

    assert (
        store.find_by_file_hash("a" * 64)
        == "scan-test-12345678"
    )


def test_runtime_store_persists_quarantine(
    tmp_path: Path,
) -> None:
    store = PipelineRuntimeStore(tmp_path)
    store.quarantine(
        "scan-test-12345678",
        {
            "scan_id": "scan-test-12345678",
            "stage": "PUF_AUTHENTICATION",
        },
    )

    records = store.list_quarantine()

    assert len(records) == 1
    assert records[0]["stage"] == "PUF_AUTHENTICATION"
