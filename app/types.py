"""Purpose: Central type aliases for JSON-compatible data.
Directory: app.
Dependencies: Python typing.
Connection: Used by every layer to keep serialisation contracts explicit.
"""

from __future__ import annotations

from typing import TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]

