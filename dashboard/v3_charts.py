"""
dashboard/v3_charts.py
======================
Hand-built inline-SVG charts for the v3 dashboard (no Plotly — the whole v3
look depends on charts rendering inside the same styled HTML flow).

Both renderers return "" when there are fewer than 2 distinct points — a
polyline with <2 points renders nothing, so callers substitute their
coming-soon placeholder instead.
"""
from datetime import datetime, timedelta

BLUE = "#2F7DED"
TEAL = "#10B981"
RED = "#EF4444"
GRID = "#E4E9F0"
MUTED = "#6B7686"
BAND_FILL = "rgba(47,125,237,.12)"
HORIZON_COLORS = {30: "#F5A524", 60: "#A855F7", 120: "#10B981"}

_MONO = "font-family:'JetBrains Mono',monospace;"


def _parse_dt(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _rolling_mean_std(values: list[float], window: int = 5) -> tuple[list[float], list[float]]:
    means, stds = [], []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1): i + 1]
        m = sum(chunk) / len(chunk)
        var = sum((v - m) ** 2 for v in chunk) / len(chunk)
        means.append(m)
        stds.append(var ** 0.5)
    return means, stds


def render_history_chart(snaps: list[dict], preds: list[dict]) -> str:
    """Taxi count history with ±2σ band + ML prediction diamonds.

    Future predictions (latest per horizon) = filled diamonds right of the
    live edge. Past predictions whose target time falls inside the window =
    hollow diamonds over the actual line (predicted-vs-actual, grading
    rubric requirement).
    """
    pts = []
    for s in snaps:
        t = _parse_dt(s.get("fetched_at"))
        if t is not None and s.get("taxi_count") is not None:
            pts.append((t, float(s["taxi_count"])))
    if len({p[0] for p in pts}) < 2:
        return ""
    pts.sort(key=lambda p: p[0])
    times = [p[0] for p in pts]
    counts = [p[1] for p in pts]

    means, stds = _rolling_mean_std(counts)
    band_hi = [m + 2 * s for m, s in zip(means, stds)]
    band_lo = [m - 2 * s for m, s in zip(means, stds)]

    # Latest prediction per horizon → future diamonds; past predictions whose
    # target lands inside the history window → hollow diamonds.
    future, past = {}, []
    for p in preds or []:
        created = _parse_dt(p.get("created_at"))
        if created is None or p.get("predicted_count") is None:
            continue
        h = int(p.get("horizon_minutes") or 0)
        target = created + timedelta(minutes=h)
        if target > times[-1]:
            if h in HORIZON_COLORS and h not in future:  # preds are DESC → first wins
                future[h] = (target, float(p["predicted_count"]))
        elif target >= times[0]:
            past.append((target, float(p["predicted_count"]), h))

    t0 = times[0]
    t1 = max([times[-1]] + [t for t, _ in future.values()])
    span_s = max((t1 - t0).total_seconds(), 1.0)
    y_all = counts + band_hi + band_lo + [v for _, v in future.values()] + [v for _, v, _ in past]
    y_min, y_max = min(y_all), max(y_all)
    y_pad = max((y_max - y_min) * 0.1, 1.0)
    y_min -= y_pad
    y_max += y_pad

    W, H, L, R, T, B = 900, 220, 30, 880, 10, 190

    def x(t: datetime) -> float:
        return round(L + (t - t0).total_seconds() / span_s * (R - L), 1)

    def y(v: float) -> float:
        return round(B - (v - y_min) / (y_max - y_min) * (B - T), 1)

    band_pts = (" ".join(f"{x(t)},{y(v)}" for t, v in zip(times, band_hi))
                + " " + " ".join(f"{x(t)},{y(v)}" for t, v in zip(reversed(times), reversed(band_lo))))
    line_pts = " ".join(f"{x(t)},{y(v)}" for t, v in zip(times, counts))

    def diamond(cx: float, cy: float, color: str, hollow: bool, title: str) -> str:
        cls = "fc-diamond-past" if hollow else "fc-diamond"
        fill = "#FFFFFF" if hollow else color
        r = 5
        return (f'<polygon class="{cls}" points="{cx},{cy - r} {cx + r},{cy} {cx},{cy + r} {cx - r},{cy}" '
                f'fill="{fill}" stroke="{color}" stroke-width="1.5"><title>{title}</title></polygon>')

    marks = ""
    for h, (t, v) in sorted(future.items()):
        marks += diamond(x(t), y(v), HORIZON_COLORS[h], False, f"Forecast +{h}min: {v:.0f} taxis")
    for t, v, h in past[:40]:
        marks += diamond(x(t), y(v), HORIZON_COLORS.get(h, MUTED), True,
                         f"Predicted {v:.0f} at {t.strftime('%H:%M')} (+{h}min horizon)")

    gridlines = "".join(
        f'<line x1="{L}" y1="{gy}" x2="{R}" y2="{gy}" stroke="{GRID}" stroke-width="1"/>'
        for gy in (T + i * (B - T) / 4 for i in range(5)))

    legend = (
        f'<div style="display:flex; gap:14px; flex-wrap:wrap; font-size:9.5px; {_MONO} color:{MUTED}; padding:4px 30px 0;">'
        f'<span style="color:{BLUE};">━ Actual taxis</span>'
        f'<span style="color:{MUTED};">▨ Normal range (±2σ)</span>'
        + "".join(f'<span style="color:{c};">◆ Forecast +{h}min</span>'
                  for h, c in HORIZON_COLORS.items())
        + f'<span style="color:{MUTED};">◇ Past predictions (vs actual)</span></div>')

    labels = (f'<div style="display:flex; justify-content:space-between; font-size:9.5px; '
              f'color:{MUTED}; {_MONO} padding:0 30px;">'
              f'<span>{t0.strftime("%H:%M")}</span><span>{t1.strftime("%H:%M")}</span></div>')

    return (f'<div class="chart-wrap"><svg width="100%" height="220" viewBox="0 0 {W} {H}" '
            f'preserveAspectRatio="none">{gridlines}'
            f'<polygon points="{band_pts}" fill="{BAND_FILL}" stroke="none"/>'
            f'<polyline fill="none" stroke="{BLUE}" stroke-width="2" points="{line_pts}"/>'
            f'{marks}'
            f'<line x1="{L}" y1="{B}" x2="{R}" y2="{B}" stroke="{GRID}"/></svg>'
            f'{labels}{legend}</div>')


def render_flux_chart(snaps: list[dict], last_n: int = 30) -> str:
    """Taxi flux (inflow/outflow) bars: teal above zero, red below."""
    rows = [(s.get("fetched_at"), s.get("flux")) for s in snaps
            if s.get("flux") is not None and _parse_dt(s.get("fetched_at"))]
    rows = rows[-last_n:]
    if len(rows) < 2:
        return ""
    values = [float(v) for _, v in rows]
    v_max = max(abs(v) for v in values) or 1.0

    W, H, L, R = 900, 120, 30, 880
    mid = H / 2
    scale = (H / 2 - 12) / v_max
    n = len(values)
    slot = (R - L) / n
    bw = max(slot * 0.6, 2)

    bars = ""
    for i, v in enumerate(values):
        bx = round(L + i * slot + (slot - bw) / 2, 1)
        bh = round(abs(v) * scale, 1)
        if v >= 0:
            bars += f'<rect x="{bx}" y="{round(mid - bh, 1)}" width="{round(bw, 1)}" height="{max(bh, 0.5)}" fill="{TEAL}" rx="1"/>'
        else:
            bars += f'<rect x="{bx}" y="{mid}" width="{round(bw, 1)}" height="{max(bh, 0.5)}" fill="{RED}" rx="1"/>'

    return (f'<div class="chart-wrap"><svg width="100%" height="120" viewBox="0 0 {W} {H}" '
            f'preserveAspectRatio="none">{bars}'
            f'<line x1="{L}" y1="{mid}" x2="{R}" y2="{mid}" stroke="#D3DBE5" stroke-width="1"/></svg>'
            f'<div style="font-size:9.5px; color:{MUTED}; {_MONO} padding:0 30px;">'
            f'Positive = taxis arriving · Negative = taxis leaving</div></div>')
