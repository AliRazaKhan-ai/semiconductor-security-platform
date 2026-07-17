from __future__ import annotations


def test_scan_identifier_path_traversal_is_rejected(client) -> None:
    response = client.post(
        "/api/v1/scans",
        json={
            "scan_id": "../../outside",
            "chip_id": "CHIP-001",
            "evidence": {"source": "terminal"},
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"

