"""
dashboard/scoring.py
====================
Pure scoring logic for the v3 dashboard's reactive score weights.

Weight semantics (mirrors the connectivity formula in analytics/engine.py):
    score = bus_share·bus_score + taxi_share·(stab_share·stability − fric_share·friction·100)
where bus_share + taxi_share = 1 and stab_share + fric_share = 1.

The user-facing weights dict stores the two free percentages:
    {"bus": 50, "stab": 60}
Defaults reproduce the canonical Bus×0.5 + Stability×0.3 − Friction×0.2.
"""

DEFAULT_WEIGHTS = {"bus": 50, "stab": 60}

VERDICT_COLORS = {
    "GOOD": "#10B981",
    "MODERATE": "#F5A524",
    "POOR": "#EF4444",
    "OFFLINE": "#8B95A5",
}


def apply_weights(components: dict, weights: dict) -> float | None:
    """Re-weight a district's score from its raw components.

    components must carry bus_frequency_score (0-100),
    taxi_stability_score (0-100) and friction_ratio (0-1).
    Returns a 0-100 clamped score, or None if any component is missing.
    """
    if not components:
        return None
    bus = components.get("bus_frequency_score")
    stab = components.get("taxi_stability_score")
    fric = components.get("friction_ratio")
    if bus is None or stab is None or fric is None:
        return None
    bus_share = weights["bus"] / 100.0
    taxi_share = 1.0 - bus_share
    stab_share = weights["stab"] / 100.0
    fric_share = 1.0 - stab_share
    score = (bus_share * bus
             + taxi_share * (stab_share * stab - fric_share * fric * 100.0))
    return round(max(0.0, min(100.0, score)), 1)


def verdict_for(score: float | None) -> tuple[str, str]:
    """Map a score to (verdict label, hex color). None → OFFLINE."""
    if score is None:
        return "OFFLINE", VERDICT_COLORS["OFFLINE"]
    if score >= 75:
        return "GOOD", VERDICT_COLORS["GOOD"]
    if score >= 50:
        return "MODERATE", VERDICT_COLORS["MODERATE"]
    return "POOR", VERDICT_COLORS["POOR"]


def alert_kpi_color(n: int) -> str:
    """Honest alert coloring: calm at zero, alarmed as alerts pile up."""
    if n <= 0:
        return "#10B981"
    if n <= 5:
        return "#F5A524"
    return "#EF4444"


def is_custom(weights: dict) -> bool:
    return (weights.get("bus") != DEFAULT_WEIGHTS["bus"]
            or weights.get("stab") != DEFAULT_WEIGHTS["stab"])
