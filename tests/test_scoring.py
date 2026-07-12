import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.scoring import (DEFAULT_WEIGHTS, apply_weights, verdict_for,
                               alert_kpi_color, is_custom)


def test_default_weights_reproduce_canonical_formula():
    # Canonical: Bus×0.5 + Stability×0.3 − Friction%×0.2
    components = {"bus_frequency_score": 80.0,
                  "taxi_stability_score": 90.0,
                  "friction_ratio": 0.5}
    # 80·0.5 + 90·0.3 − 50·0.2 = 40 + 27 − 10 = 57
    assert apply_weights(components, DEFAULT_WEIGHTS) == 57.0


def test_apply_weights_clamps_low_and_high():
    low = {"bus_frequency_score": 0.0, "taxi_stability_score": 0.0,
           "friction_ratio": 1.0}
    assert apply_weights(low, DEFAULT_WEIGHTS) == 0.0
    high = {"bus_frequency_score": 100.0, "taxi_stability_score": 100.0,
            "friction_ratio": 0.0}
    assert apply_weights(high, {"bus": 100, "stab": 100}) == 100.0


def test_apply_weights_missing_component_returns_none():
    assert apply_weights({"bus_frequency_score": 50.0}, DEFAULT_WEIGHTS) is None
    assert apply_weights({}, DEFAULT_WEIGHTS) is None
    assert apply_weights({"bus_frequency_score": None,
                          "taxi_stability_score": 50.0,
                          "friction_ratio": 0.1}, DEFAULT_WEIGHTS) is None


def test_verdict_boundaries():
    assert verdict_for(75) == ("GOOD", "#10B981")
    assert verdict_for(74.9) == ("MODERATE", "#F5A524")
    assert verdict_for(50) == ("MODERATE", "#F5A524")
    assert verdict_for(49.9) == ("POOR", "#EF4444")
    assert verdict_for(None) == ("OFFLINE", "#8B95A5")


def test_alert_kpi_color():
    assert alert_kpi_color(0) == "#10B981"
    assert alert_kpi_color(1) == "#F5A524"
    assert alert_kpi_color(5) == "#F5A524"
    assert alert_kpi_color(6) == "#EF4444"
    assert alert_kpi_color(200) == "#EF4444"


def test_is_custom():
    assert not is_custom(dict(DEFAULT_WEIGHTS))
    assert is_custom({"bus": 75, "stab": 60})
    assert is_custom({"bus": 50, "stab": 70})
