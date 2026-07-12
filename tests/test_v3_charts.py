import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.v3_charts import render_history_chart, render_flux_chart

T0 = datetime(2026, 7, 12, 20, 0, 0)


def _snaps(n, counts=None):
    return [{"fetched_at": (T0 + timedelta(minutes=i)).isoformat(sep=" "),
             "taxi_count": (counts[i] if counts else 100 + i),
             "flux": (-3 if i % 2 else 4),
             "friction": 0.1}
            for i in range(n)]


def test_history_empty_and_single_point_return_sentinel():
    assert render_history_chart([], []) == ""
    assert render_history_chart(_snaps(1), []) == ""
    # 2 rows but identical timestamps/points → still 1 distinct point
    s = _snaps(1) * 2
    assert render_history_chart(s, []) == ""


def test_history_chart_has_line_band_and_legend():
    out = render_history_chart(_snaps(30), [])
    assert "<svg" in out and "polyline" in out
    assert "rgba(47,125,237" in out          # ±2σ band fill
    assert "Normal range" in out             # legend
    assert "Actual taxis" in out


def test_history_chart_marks_future_and_past_predictions():
    snaps = _snaps(60)
    now = T0 + timedelta(minutes=59)
    preds = [
        # future predictions (created now)
        {"created_at": now.isoformat(sep=" "), "horizon_minutes": 30,
         "predicted_count": 120, "actual_count": None},
        {"created_at": now.isoformat(sep=" "), "horizon_minutes": 60,
         "predicted_count": 115, "actual_count": None},
        # past prediction whose target lands inside the window
        {"created_at": (T0 + timedelta(minutes=10)).isoformat(sep=" "),
         "horizon_minutes": 30, "predicted_count": 90, "actual_count": 95},
    ]
    out = render_history_chart(snaps, preds)
    assert out.count('class="fc-diamond"') == 2       # future, filled
    assert out.count('class="fc-diamond-past"') == 1  # past, hollow
    assert "Forecast +30" in out and "Past predictions" in out


def test_flux_sentinel_and_colors():
    assert render_flux_chart([]) == ""
    assert render_flux_chart(_snaps(1)) == ""
    out = render_flux_chart(_snaps(30))
    assert "#10B981" in out   # positive bars teal
    assert "#EF4444" in out   # negative bars red
    assert "taxis arriving" in out
