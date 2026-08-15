import math

import pytest

from physics_lab.plugins.faraday.calculations import linear_fit, rotation_angle, summarize_samples, wavelength_result


def test_faraday_summarizes_two_raw_channels_before_ratio() -> None:
    result = summarize_samples(
        [{"raw_left": 2.0, "raw_right": 1.0}, {"raw_left": 4.0, "raw_right": 2.0}]
    )
    assert result["raw_left"] == 3.0
    assert result["raw_right"] == 1.5
    assert result["r"] == 2.0


def test_faraday_rotation_angle_uses_radians() -> None:
    assert rotation_angle(4.0, 1.0) == pytest.approx(math.atan(2.0) - math.atan(1.0))


def test_faraday_wavelength_result_calculates_fit_and_verdet_constant() -> None:
    base = math.atan(1.0)
    points = [
        {"magnetic_field_t": 0.0, "r": 1.0, "status": "complete", "index": 1},
        {"magnetic_field_t": 1.0, "r": math.tan(base + 0.1) ** 2, "status": "complete", "index": 2},
        {"magnetic_field_t": 2.0, "r": math.tan(base + 0.2) ** 2, "status": "complete", "index": 3},
    ]
    result = wavelength_result(points, 0.5)
    assert result["r0"] == 1.0
    assert result["r_squared"] == pytest.approx(1.0)
    assert result["v_rad_per_t_m"] == pytest.approx(result["k_rad_per_t"] / 0.5)
    assert result["points"][0]["theta_rad"] == 0.0


def test_faraday_fit_rejects_duplicate_magnetic_fields() -> None:
    with pytest.raises(ValueError, match="不能全部相同"):
        linear_fit([(1.0, 0.1), (1.0, 0.2)])
