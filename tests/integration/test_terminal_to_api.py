from __future__ import annotations


def test_terminal_can_submit_json_scan(client) -> None:
    response = client.post(
        "/api/v1/scans",
        json={
            "chip_id": "CHIP-001",
            "source": {"terminal_id": "TESTER-01"},
            "evidence": {"chip_file": "chip_01_good.json"},
        },
        headers={"Idempotency-Key": "test-scan-1"},
    )
    assert response.status_code == 202
    body = response.get_json()
    assert body["ok"] is True
    scan_id = body["data"]["scan_id"]
    query = client.get(f"/api/v1/scans/{scan_id}")
    assert query.status_code == 200
    assert query.get_json()["data"]["chip_id"] == "CHIP-001"

