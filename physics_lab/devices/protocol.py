from __future__ import annotations

from typing import Any


PROTOCOL_NAME = "physics-lab-jsonl"
CURRENT_PROTOCOL_VERSION = 1
SUPPORTED_PROTOCOL_VERSIONS = frozenset({CURRENT_PROTOCOL_VERSION})


def validate_protocol_version(value: Any) -> int:
    try:
        version = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid protocol version: {value!r}") from exc
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        supported = ", ".join(str(item) for item in sorted(SUPPORTED_PROTOCOL_VERSIONS))
        raise ValueError(f"Unsupported protocol version: {version}; supported versions: {supported}")
    return version
