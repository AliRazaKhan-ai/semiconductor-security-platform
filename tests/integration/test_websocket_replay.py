from __future__ import annotations

from app.extensions import socketio


def test_socket_replay_returns_durable_events(app, client) -> None:
    response = client.post(
        "/api/v1/scans",
        json={"chip_id": "CHIP-001", "evidence": {"source": "terminal"}},
    )
    scan_id = response.get_json()["data"]["scan_id"]
    socket_client = socketio.test_client(app, namespace="/events")
    socket_client.emit("replay", {"scan_id": scan_id, "after_sequence": 0}, namespace="/events")
    messages = socket_client.get_received("/events")
    batches = [message for message in messages if message["name"] == "replay.batch"]
    assert batches
    assert batches[-1]["args"][0]["data"]["count"] == 1
    socket_client.disconnect(namespace="/events")

