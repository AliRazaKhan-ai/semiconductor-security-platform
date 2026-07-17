"""Purpose: Convert public subscription requests into controlled SocketIO rooms.
Directory: app/websocket.
Dependencies: schema validation.
Connection: Namespace joins and leaves only rooms returned by this module.
"""

from __future__ import annotations

from app.websocket.schemas import validate_subscription


def room_for(data: object) -> str:
    channel, scan_id = validate_subscription(data)
    if channel == "scan" and scan_id is not None:
        return f"scan:{scan_id}"
    return channel

