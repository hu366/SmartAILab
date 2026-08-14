import pytest

from physics_lab.devices.protocol import validate_protocol_version


def test_protocol_version_accepts_current_version() -> None:
    assert validate_protocol_version("1") == 1


def test_protocol_version_rejects_invalid_version() -> None:
    with pytest.raises(ValueError, match="Invalid protocol version"):
        validate_protocol_version("one")
