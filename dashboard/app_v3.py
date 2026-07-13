"""
dashboard/app_v3.py
====================
SG Liveability v3 — full HTML/CSS/JS embed architecture.

WHY THIS SHAPE (vs. Step-1's piecemeal st.markdown calls):
  Streamlit-native widgets (st.dataframe, st.bar_chart, st.tabs) each render
  in their own isolated web component with built-in styling our CSS can't
  reach — that's what caused the earlier "half real cards, half default-
  Streamlit-looking widgets" patchwork look.

  This version flips the approach: Python still does 100% of the real data
  fetching (same DB/DuckDB/API calls as Step 1), but instead of handing the
  page to the browser one small st.markdown() at a time, it fills in the
  ENTIRE mockup's HTML/CSS/JS as one single block and renders it through
  st.components.v1.html(). One consistent look, the exact approved design,
  real numbers inside it.

  The trade-off: content inside that block runs in an isolated iframe that
  can't trigger new Python computation on its own. So the ONE thing that
  stays a plain native Streamlit control is the district picker above the
  embed — picking a district reruns this script, which fetches new real
  data and rebuilds the whole HTML block with it. Everything else (tabs,
  map expand/collapse, the score-weights slider) is cosmetic JS inside the
  block, same as the approved mockup.

Run:
    streamlit run dashboard/app_v3.py --server.port 8502
Optionally, in another terminal, for live connectivity scores:
    LTA_API_KEY=<key> python main.py
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dashboard.scoring import (DEFAULT_WEIGHTS, apply_weights, verdict_for,
                               alert_kpi_color, is_custom)
from dashboard.v3_charts import render_history_chart, render_flux_chart

from config import cfg
from storage.database import (init_db, fetch_snapshots, fetch_predictions,
                              fetch_alerts, fetch_latest_metrics)
from hdb.planning_areas import load_all_planning_areas

try:
    from ml.forecaster import TaxiForecaster
    FORECASTER_AVAILABLE = True
except Exception:
    FORECASTER_AVAILABLE = False

try:
    from ml.extended_forecaster import DayPatternAnalyser, HourlyForecaster, PeakHourPredictor
    EXTENDED_FORECASTER_AVAILABLE = True
except Exception:
    EXTENDED_FORECASTER_AVAILABLE = False

try:
    from hdb.analytics import (get_town_summary, get_price_trend, get_available_towns,
                                get_flat_types, get_value_for_money)
    HDB_AVAILABLE = True
except Exception:
    HDB_AVAILABLE = False

SGT = timezone(timedelta(hours=8))
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="SG Liveability", page_icon="\U0001F1F8\U0001F1EC", layout="wide")
init_db()

st.markdown("""
<style>
/* Force a light shell regardless of the user's Streamlit theme setting —
   a dark Streamlit theme otherwise clashes badly with the light dashboard
   embedded below it. */
.stApp { background: #F3F6FA !important; }
/* Keep Streamlit's header visible so the ⋮ menu (theme switcher etc.) stays
   reachable — only the footer is hidden. */
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
/* Our shell is always light — force dark ink on the header icons so they
   don't go white-on-white when the Streamlit theme is dark. */
header[data-testid="stHeader"] svg { color: #0F172A !important; fill: #0F172A !important; }
/* Keep our sticky topnav below the now-visible Streamlit header. */
header.topnav { top: 3.75rem !important; }
.block-container { padding-top: 1rem; max-width: 1500px; }

/* Streamlit's DARK theme sets color:white on its containers, and any of our
   elements without an explicit color inherit it → white-on-white. Force dark
   ink at the markdown-container level so inheritance resolves to our palette. */
div[data-testid="stMarkdownContainer"] { color: #0F172A; }
div[data-testid="stMarkdownContainer"] p { color: inherit; }

/* Belt-and-braces: the classes that relied on inheritance */
.kpi-val, .card h3, .card h4, .brand,
.stat-line .v, .bar-val, .sg-bar-val,
.row-title, .fc-row span:last-child,
.price-tile .v, .sg-price-tile .v,
table td, table.sg-table td,
.acc-head, .modal { color: #0F172A; }

/* Streamlit's tab labels + caption also go white-on-white in dark theme */
button[data-baseweb="tab"] { color: #6B7686 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: #2F7DED !important; }
div[data-testid="stCaptionContainer"] { color: #6B7686 !important; }
/* Expander: Streamlit's dark theme paints the <summary> header near-black —
   force the whole widget onto the light card palette. */
div[data-testid="stExpander"],
div[data-testid="stExpander"] > details,
div[data-testid="stExpander"] summary {
  background: #FFFFFF !important;
  border-color: #E4E9F0 !important;
}
div[data-testid="stExpander"] > details { border-radius: 10px; }
div[data-testid="stExpander"] summary,
div[data-testid="stExpander"] summary p,
div[data-testid="stExpander"] summary span { color: #0F172A !important; }
div[data-testid="stExpander"] summary svg { fill: #0F172A !important; color: #0F172A !important; }

div[data-baseweb="select"] > div {
  background: #FFFFFF !important; border: 1px solid #D3DBE5 !important;
  border-radius: 10px !important; font-family: 'JetBrains Mono', monospace !important;
}
/* Dark theme paints the selected value white — force dark ink on every
   descendant (the portal dropdown list is separate and stays theme-styled). */
div[data-baseweb="select"] span,
div[data-baseweb="select"] div,
div[data-baseweb="select"] input { color: #0F172A !important; }
div[data-baseweb="select"] svg { fill: #6B7686 !important; }
label { color: #6B7686 !important; font-family: 'JetBrains Mono', monospace !important; font-size: 11px !important; }

/* Buttons: dark theme gives them a near-black fill while our
   stMarkdownContainer rule turns their label dark → black-on-black boxes.
   Force the light-card button look everywhere (incl. the popover trigger). */
.stApp button[kind],
.stApp div[data-testid="stPopover"] > button {
  background: #FFFFFF !important; border: 1px solid #D3DBE5 !important;
  border-radius: 10px !important; color: #0F172A !important;
}
.stApp button[kind] p, .stApp button[kind] span,
.stApp div[data-testid="stPopover"] > button p { color: #0F172A !important; }
.stApp button[kind]:hover { border-color: #2F7DED !important; color: #2F7DED !important; }

/* Popover panel is a dark portal in dark theme — force the white card look
   so its sliders/captions/formula (all dark ink) stay readable. */
div[data-testid="stPopoverBody"] { background: #FFFFFF !important; border: 1px solid #E4E9F0 !important; }

/* Text inputs (postal code) */
div[data-baseweb="input"], div[data-baseweb="input"] > div { background: #FFFFFF !important; }
div[data-baseweb="input"] input { background: #FFFFFF !important; color: #0F172A !important; }

/* Hidden helper button the embedded map clicks to trigger a rerun after it
   writes ?district=… into the URL (its sandbox can't navigate the page). */
.st-key-map_sync { display: none !important; }
</style>
""", unsafe_allow_html=True)


# \u2500\u2500\u2500\u2500 API helpers \u2500\u2500\u2500\u2500

def call_api(path: str, params: dict | None = None, timeout: float = 2.0):
    """Best-effort call to the live FastAPI server. Returns None if it's not
    running \u2014 the live connectivity score genuinely only exists in-memory
    while `python main.py` is running the ingestion workers."""
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=timeout)
        if r.ok:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return None


@st.cache_data(ttl=30)
def call_rank_cached():
    """/rank evaluates all 55 districts live \u2014 genuinely slow (a few seconds).
    Cache for 30s so switching the district selector doesn't re-trigger it
    every time, and give it real room to respond instead of a too-short timeout."""
    return call_api("/rank", timeout=8.0)


@st.cache_data(ttl=300)
def get_district_options() -> list[dict]:
    """Real 55 planning areas, slugged the same way app.py already does."""
    areas = load_all_planning_areas()
    options = [{"label": "\U0001F1F8\U0001F1EC Singapore Average", "slug": "average", "bbox": None}]
    for a in areas:
        label = a["name"].title()
        slug = a["name"].lower().replace(" ", "_").replace("/", "_")
        bbox = (a["min_lon"], a["max_lon"], a["min_lat"], a["max_lat"])
        options.append({"label": label, "slug": slug, "bbox": bbox})
    return options


def friction_word(friction: float) -> tuple[str, str]:
    if friction < 0.2:
        return "Easy", "#10B981"
    if friction < 0.5:
        return "Moderate", "#F5A524"
    return "Hard", "#EF4444"


def get_avg_price(slug: str | None):
    if not HDB_AVAILABLE:
        return None
    try:
        df = get_town_summary(flat_type="4 ROOM", months=12)
    except Exception:
        return None
    if df.empty:
        return None
    if slug is None:
        return round(df["avg_price"].mean(), -3)
    match = df[df["town"].str.lower().str.replace(" ", "_") == slug]
    if not match.empty:
        return round(match["avg_price"].iloc[0], -3)
    return None


def get_taxi_forecast(slug: str) -> dict:
    """Real Ridge-model +30/+60/+120min forecast \u2014 DB + saved model only, no live API needed."""
    if not FORECASTER_AVAILABLE or slug == "average":
        return {}
    try:
        return TaxiForecaster(slug).predict()
    except Exception:
        return {}


def _alerts_24h(slug: str | None) -> list[dict]:
    """Alerts scoped to the last 24 hours (timestamps stored in SGT)."""
    cutoff = (datetime.now(SGT) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        rows = fetch_alerts(slug, limit=200)
    except Exception:
        return []
    return [a for a in rows if str(a.get("triggered_at", "")) >= cutoff]


def get_scope_snapshot(slug: str, bbox) -> dict:
    """Assemble every real number needed for the whole page, for one district
    or the citywide average when slug == 'average'."""
    all_options = get_district_options()

    if slug == "average":
        slugs = [o["slug"] for o in all_options if o["slug"] != "average"]
        latest_counts = []
        for s in slugs:
            snaps = fetch_snapshots(s, minutes=5)
            if snaps:
                latest_counts.append(snaps[-1]["taxi_count"])
        alerts = _alerts_24h(None)
        live_taxis = sum(latest_counts) if latest_counts else 0
        avg_taxi = (sum(latest_counts) / len(latest_counts)) if latest_counts else 0.0
        rank = call_rank_cached()
        conn_score, verdict = None, None
        if rank:
            scores = [r["score"] for r in rank]
            conn_score = round(sum(scores) / len(scores)) if scores else None
            verdict = "MODERATE" if conn_score and conn_score < 80 else "GOOD"
        return dict(
            live_taxis=live_taxis, avg_taxi=round(avg_taxi, 1), friction=0.0,
            alerts=len(alerts), alerts_list=alerts[:8], conn_score=conn_score, verdict=verdict,
            price=get_avg_price(None), live=bool(rank), bus=None, forecast={},
            bus_stops="\u2014", bus_headway="\u2014",
        )

    snaps = fetch_snapshots(slug, minutes=60)
    alerts = _alerts_24h(slug)
    live_taxis = snaps[-1]["taxi_count"] if snaps else 0
    avg_taxi = (sum(s["taxi_count"] for s in snaps) / len(snaps)) if snaps else 0.0
    friction = snaps[-1].get("friction", 0.0) if snaps else 0.0

    evaluated = None
    if bbox:
        evaluated = call_api("/evaluate", {
            "min_lon": bbox[0], "max_lon": bbox[1], "min_lat": bbox[2], "max_lat": bbox[3],
        })
    conn_score = round(evaluated["connectivity_score"]) if evaluated else None
    verdict = None
    if conn_score is not None:
        verdict = "GOOD" if conn_score >= 75 else ("MODERATE" if conn_score >= 50 else "POOR")

    return dict(
        live_taxis=live_taxis, avg_taxi=round(avg_taxi, 1), friction=friction,
        alerts=len(alerts), alerts_list=alerts[:8], conn_score=conn_score, verdict=verdict,
        price=get_avg_price(slug), live=bool(evaluated), bus=evaluated,
        forecast=get_taxi_forecast(slug),
    )


# \u2500\u2500\u2500\u2500 HTML fragment renderers (server-side, real data only) \u2500\u2500\u2500\u2500

def esc(v, fallback="\u2014"):
    return fallback if v is None else v


def render_coming_soon(message: str) -> str:
    return f"""<div style="text-align:center; padding:30px 20px; color:var(--muted); font-size:12.5px;
                background:var(--bg); border:1px dashed var(--border-strong); border-radius:10px;">
      \U0001F6A7 <b style="color:var(--text)">Not built yet</b><br>{message}</div>"""


def render_price_table(df: pd.DataFrame, n: int = 8) -> str:
    if df is None or df.empty:
        return render_coming_soon("No price data available.")
    rows = ""
    for _, r in df.head(n).iterrows():
        rows += (f"<tr><td>{r['town'].title()}</td><td>S${r['avg_price']:,.0f}</td>"
                 f"<td>{int(r['num_transactions'])}</td></tr>")
    return f'<table class="sg-table"><tr><th>Town</th><th>Avg Price</th><th>Txns</th></tr>{rows}</table>'


def render_vfm_table(df: pd.DataFrame, n: int = 10) -> str:
    if df is None or df.empty:
        return render_coming_soon("VFM ranking needs price + connectivity data.")
    rows = ""
    for _, r in df.head(n).iterrows():
        rows += (f"<tr><td>{r['town'].title()}</td><td>{r['vfm_score']:.1f}</td>"
                 f"<td>S${r['avg_price']:,.0f}</td><td>{r['vfm_verdict']}</td></tr>")
    return f'<table class="sg-table"><tr><th>Town</th><th>VFM</th><th>Avg Price</th><th>Verdict</th></tr>{rows}</table>'


def _verdict_class(score):
    return "g" if score >= 75 else ("a" if score >= 50 else "r")


def _verdict_label(score):
    return "Well connected" if score >= 75 else ("Moderate" if score >= 50 else "Poor")


def render_leaderboard(rank_list: list, highlight_district: str | None = None) -> str:
    if not rank_list:
        return render_coming_soon("Ranks all districts by live connectivity score \u2014 "
                                  "needs the live pipeline (python main.py) running.")
    ranked = sorted(rank_list, key=lambda r: r["score"], reverse=True)
    max_score = max((r["score"] for r in ranked), default=1) or 1
    bars = ""
    for r in ranked[:10]:
        pct = round((r["score"] / max_score) * 100, 1)
        is_sel = r["district"] == highlight_district
        color = "#EA8C1D" if is_sel else ("#10B981" if r["score"] >= 75 else ("#F5A524" if r["score"] >= 50 else "#EF4444"))
        val_color = "#D97706" if is_sel else "#111"
        bars += (f'<div class="sg-bar-col"><div class="sg-bar-val" style="color:{val_color}">{r["score"]:.0f}</div>'
                  f'<div class="sg-bar" style="height:{pct}%; background:{color};"></div>'
                  f'<div class="sg-bar-lbl">{r["district"]}</div></div>')
    rows = ""
    for r in ranked:
        cls = _verdict_class(r["score"])
        sel_cls = " selected" if r["district"] == highlight_district else ""
        rows += (f'<tr class="{sel_cls.strip()}"><td>{r["district"]}</td><td>{r["score"]:.0f}</td>'
                  f'<td><span class="sg-verdict"><span class="sg-dot {cls}"></span>{_verdict_label(r["score"])}</span></td></tr>')
    return f'<div class="sg-bars">{bars}</div><table class="sg-table"><tr><th>District</th><th>Score</th><th>Verdict</th></tr>{rows}</table>'


def render_heatmap(pattern: pd.DataFrame) -> str:
    if pattern is None or pattern.empty:
        return render_coming_soon("Not enough history yet for this district.")
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cells = '<div class="sg-heatmap">'
    cells += "<div></div>" + "".join(f'<div class="hhead">{h}</div>' for h in range(24))
    lookup = {(int(r.weekday), int(r.hour)): r.relative_pct for r in pattern.itertuples()}
    for wd, name in enumerate(day_names):
        cells += f'<div class="hlabel">{name}</div>'
        for h in range(24):
            pct = lookup.get((wd, h))
            color = "#EEE" if pct is None else ("#10B981" if pct > 10 else ("#F87171" if pct < -10 else "#FDE68A"))
            cells += f'<div class="hcell" style="background:{color}"></div>'
    cells += "</div>"
    return cells


PEAK_HOURS = {7, 8, 17, 18}  # 7-9am + 5-7pm, matching v1's shaded bands


def render_24h_line_chart(df: pd.DataFrame) -> str:
    if df is None or df.empty or len(df) < 2:
        return render_coming_soon("Model needs at least 50 recent snapshots to predict.")
    vals = df["predicted_count"].tolist()
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)

    def x_at(i: int) -> float:
        return 30 + (i / (n - 1)) * 840

    pts = []
    for i, v in enumerate(vals):
        pts.append(f"{x_at(i):.0f},{160 - ((v - lo) / span) * 140:.0f}")
    polyline = " ".join(pts)

    # Peak-hour shading: contiguous runs of predictions landing in 7-9am/5-7pm.
    rects, label_x = "", None
    try:
        hours = pd.to_datetime(df["predicted_at"]).dt.hour.tolist()
        half = 420 / max(n - 1, 1)
        run_start = None
        for i in range(n + 1):
            in_peak = i < n and hours[i] in PEAK_HOURS
            if in_peak and run_start is None:
                run_start = i
            elif not in_peak and run_start is not None:
                x0 = max(30.0, x_at(run_start) - half)
                x1 = min(870.0, x_at(i - 1) + half)
                rects += f'<rect x="{x0:.0f}" y="0" width="{x1 - x0:.0f}" height="160" fill="#FDEAEA"/>'
                if label_x is None:
                    label_x = x0 + 4
                run_start = None
    except Exception:
        rects = ""
    peak_label = (f'<text x="{label_x:.0f}" y="12" font-size="9" fill="#EF4444" '
                  f"font-family=\"'JetBrains Mono',monospace\">Peak</text>") if label_x else ""

    return f"""<svg width="100%" height="180" viewBox="0 0 900 180" preserveAspectRatio="none">
      {rects}{peak_label}
      <polyline fill="none" stroke="#F5A524" stroke-width="2.5" points="{polyline}"/>
      <line x1="30" y1="160" x2="870" y2="160" stroke="#E4E9F0"/></svg>
      <div style="display:flex; justify-content:space-between; font-size:9.5px; color:var(--muted);
                  font-family:'JetBrains Mono',monospace; padding:0 30px;">
        <span>+1hr</span><span>+6hr</span><span>+12hr</span><span>+18hr</span><span>+24hr</span></div>
      <div style="font-size:9.5px; color:var(--muted); font-family:'JetBrains Mono',monospace; padding:2px 30px 0;">
        🔴 shaded = peak hours (7–9am, 5–7pm)</div>"""


def render_peak_ratings(peaks: list) -> str:
    if not peaks:
        return render_coming_soon("Not enough history yet to rate tomorrow's peak hours.")
    boxes = "".join(f'<div class="sg-peak-box"><div class="h">{p["time_label"]}</div>'
                     f'<div class="n">{p["rating"]}</div><div class="h">{p["expected"]} taxis</div></div>'
                     for p in peaks)
    return f'<div style="display:grid; grid-template-columns:repeat({len(peaks)},1fr); gap:8px;">{boxes}</div>'


def render_price_trend_chart(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return render_coming_soon("No transaction history for this town/flat-type combination.")
    vals = df["avg_price"].tolist()
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = 30 + (i / (n - 1)) * 840 if n > 1 else 30
        y = 180 - ((v - lo) / span) * 150
        pts.append(f"{x:.0f},{y:.0f}")
    polyline = " ".join(pts)
    first_year = df["sale_month"].iloc[0].strftime("%Y")
    last_year = df["sale_month"].iloc[-1].strftime("%Y")
    latest_price = vals[-1]
    change = vals[-1] - vals[0]
    pct = (change / vals[0] * 100) if vals[0] else 0
    total_txn = int(df["num_transactions"].sum())
    return f"""<svg width="100%" height="200" viewBox="0 0 900 200" preserveAspectRatio="none">
      <polyline fill="none" stroke="#2F7DED" stroke-width="2" points="{polyline}"/>
      <line x1="30" y1="180" x2="870" y2="180" stroke="#E4E9F0"/></svg>
      <div style="display:flex; justify-content:space-between; font-size:9.5px; color:var(--muted);
                  font-family:'JetBrains Mono',monospace; padding:0 30px;">
        <span>{first_year}</span><span>{last_year}</span></div>
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-top:12px;">
        <div class="sg-price-tile"><div class="l">LATEST AVG PRICE</div><div class="v">S${latest_price:,.0f}</div></div>
        <div class="sg-price-tile"><div class="l">PRICE CHANGE</div>
          <div class="v" style="color:{'var(--teal)' if change>=0 else 'var(--red)'}">
            {'+' if change>=0 else ''}S${change:,.0f} ({pct:+.1f}%)</div></div>
        <div class="sg-price-tile"><div class="l">TOTAL TRANSACTIONS</div><div class="v">{total_txn}</div></div>
      </div>"""


def render_alerts(alerts: list, total: int | None = None) -> str:
    if not alerts:
        return '<div class="chip ok" style="display:block; text-align:center; padding:10px;">\u2705 No alerts in the last 24h \u2014 all clear</div>'
    rows = ""
    for a in alerts[:8]:
        atype = a.get("alert_type", "")
        chip = "bad" if atype == "LOW_TAXI" else "mid"
        dot = "\U0001F534" if chip == "bad" else "\U0001F7E1"
        stamp = str(a.get("triggered_at", ""))[11:16]
        district = str(a.get("district", "")).replace("_", " ").title()
        rows += (f'<div class="chip {chip}" style="display:block; margin-bottom:6px;">'
                 f'{dot} <b>{atype}</b> \u00b7 {district} \u00b7 {a.get("message", "")} '
                 f'<span style="opacity:.65;">{stamp} SGT</span></div>')
    n = total if total is not None else len(alerts)
    if n > 8:
        rows += (f'<div style="font-size:10px; color:#6B7686; font-family:\'JetBrains Mono\',monospace; '
                 f'text-align:center; padding-top:4px;">\u2026and {n - 8} more in the last 24h</div>')
    return rows


def render_forecast_col(forecast: dict) -> str:
    if not forecast:
        return ('<div class="stat-line"><span class="l">+30 MIN</span><span class="v" style="color:var(--muted)">\u2014</span></div>'
                '<div class="stat-line"><span class="l">+60 MIN</span><span class="v" style="color:var(--muted)">\u2014</span></div>'
                '<div class="stat-line"><span class="l">+2 HR</span><span class="v" style="color:var(--muted)">\u2014</span></div>')
    v30 = forecast.get(30, 0)
    v60 = forecast.get(60, 0)
    v120 = forecast.get(120, 0)
    return (f'<div class="stat-line"><span class="l">+30 MIN</span><span class="v" style="color:var(--teal)">{v30:.0f}</span></div>'
            f'<div class="stat-line"><span class="l">+60 MIN</span><span class="v" style="color:var(--amber)">{v60:.0f}</span></div>'
            f'<div class="stat-line"><span class="l">+2 HR</span><span class="v" style="color:var(--red)">{v120:.0f}</span></div>')
CSS_TEXT = "\n  :root{\n    --bg:#F3F6FA;\n    --card:#FFFFFF;\n    --border:#E4E9F0;\n    --border-strong:#D3DBE5;\n    --text:#0F172A;\n    --muted:#6B7686;\n    --muted-2:#8B95A5;\n    --blue:#2F7DED;\n    --blue-dark:#1A5FC4;\n    --blue-pale:#EAF2FE;\n    --teal:#10B981;\n    --teal-pale:#E6F9F1;\n    --amber:#F5A524;\n    --amber-pale:#FEF3DE;\n    --red:#EF4444;\n    --red-pale:#FDEAEA;\n    --shadow: 0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.04);\n    --radius: 14px;\n  }\n  *{box-sizing:border-box;}\n  html,body{margin:0;padding:0;background:var(--bg);color:var(--text);\n    font-family:'Inter',system-ui,sans-serif;}\n  .mono{font-family:'JetBrains Mono',monospace;}\n  h1,h2,h3,h4{font-family:'JetBrains Mono',monospace; margin:0;}\n  a{color:inherit;text-decoration:none;}\n  button{font-family:inherit;cursor:pointer;}\n\n  \n  \n  header.topnav{\n    background:#fff; border-bottom:1px solid var(--border);\n    display:flex; align-items:center; gap:16px; padding:12px 24px; position:sticky; top:0; z-index:40;\n  }\n  .brand{display:flex; align-items:center; gap:10px; font-family:'JetBrains Mono',monospace; font-weight:700; font-size:15px;}\n  .brand .mark{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,#3EA6FF,#2F7DED);\n    display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:14px;}\n  .search{\n    flex:1; max-width:340px; background:var(--bg); border:1px solid var(--border);\n    border-radius:10px; padding:9px 14px; font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--muted-2);\n  }\n  .nav-right{display:flex; align-items:center; gap:10px; margin-left:auto;}\n  .pill-select{\n    background:var(--bg); border:1px solid var(--border); border-radius:10px;\n    padding:8px 14px; font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:600;\n    display:inline-flex; align-items:center; gap:7px; color:var(--text);\n    white-space:nowrap; line-height:1; height:34px; flex-shrink:0;\n  }\n  .pill-select .dotmark{width:7px;height:7px;min-width:7px;border-radius:50%;background:var(--teal);display:inline-block;}\n  .pill-select .dotmark.blue{background:var(--blue);}\n  .nav-item-wrap{position:relative; display:inline-block;}\n\n  /* Floating connectivity summary card — now scoped to the map container, not the page */\n  .map-container{display:flex; align-items:flex-start; gap:14px; margin-bottom:6px;}\n  .map-container .map-strip{flex:1; min-width:0; margin-bottom:0;}\n  .float-card{\n    width:250px; flex-shrink:0; background:#fff;\n    border:1px solid var(--border-strong); border-radius:var(--radius); box-shadow:0 6px 20px rgba(16,24,40,.08);\n    padding:16px; z-index:20;\n  }\n  .map-hint{text-align:center; font-size:10.5px; color:var(--muted-2); font-family:'JetBrains Mono',monospace; margin:0 0 16px;}\n  .float-card .fc-head{font-family:'JetBrains Mono',monospace; font-size:10.5px; color:var(--muted); letter-spacing:.5px; margin-bottom:10px;}\n  .ring{width:76px;height:76px;border-radius:50%;border:6px solid var(--amber);\n    display:flex; align-items:center; justify-content:center; font-family:'JetBrains Mono',monospace;\n    font-weight:800; font-size:24px; color:var(--amber); margin:0 auto 6px;}\n  .fc-verdict{text-align:center; font-family:'JetBrains Mono',monospace; font-weight:700; font-size:12px; color:var(--amber); margin-bottom:2px;}\n  .fc-verdict-sub{text-align:center; font-size:10.5px; color:var(--muted); margin-bottom:14px;}\n  .fc-row{display:flex; justify-content:space-between; font-size:11.5px; padding:5px 0; border-top:1px dashed var(--border);}\n  .fc-row span:first-child{color:var(--muted);}\n  .fc-row span:last-child{font-weight:700; font-family:'JetBrains Mono',monospace;}\n  .fc-services{display:flex; gap:6px; flex-wrap:wrap; margin:10px 0 12px;}\n  .svc-chip{background:var(--blue-pale); color:var(--blue-dark); font-family:'JetBrains Mono',monospace;\n    font-size:10.5px; font-weight:700; padding:4px 8px; border-radius:6px;}\n  .deep-dive{width:100%; background:var(--text); color:#fff; border:none; padding:10px; border-radius:9px;\n    font-family:'JetBrains Mono',monospace; font-size:11.5px; font-weight:700;}\n\n  main{padding:22px 24px 60px; max-width:1500px; margin:0 auto;}\n\n  /* map placeholder strip */\n  .map-strip{height:180px; border-radius:var(--radius); border:1px solid var(--border);\n    background:\n      linear-gradient(135deg, rgba(47,125,237,.10), rgba(47,125,237,.03)),\n      repeating-linear-gradient(0deg, rgba(47,125,237,.05) 0 1px, transparent 1px 26px),\n      repeating-linear-gradient(90deg, rgba(47,125,237,.05) 0 1px, transparent 1px 26px);\n    margin-bottom:16px; position:relative; overflow:hidden;\n    transition: height .28s ease;\n  }\n  .map-strip.expanded{height:80vh;}\n  .map-tools{position:absolute; left:14px; bottom:14px; display:flex; gap:8px; z-index:2;}\n  .map-btn{background:#fff; border:1px solid var(--border-strong); font-family:'JetBrains Mono',monospace;\n    font-size:11px; font-weight:600; padding:7px 12px; border-radius:8px; color:var(--muted);}\n  .map-btn.active{background:var(--blue); color:#fff; border-color:var(--blue);}\n  .map-legend{position:absolute; right:14px; bottom:14px; background:rgba(255,255,255,.9); border:1px solid var(--border);\n    border-radius:8px; padding:6px 10px; font-family:'JetBrains Mono',monospace; font-size:10px; display:flex; gap:10px; z-index:2;}\n  .map-expand-btn{position:absolute; top:14px; right:14px; z-index:2; background:#fff; border:1px solid var(--border-strong);\n    font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:700; padding:8px 13px; border-radius:8px;\n    color:var(--blue-dark); display:flex; align-items:center; gap:6px; box-shadow:var(--shadow);}\n  .map-expand-btn:hover{background:var(--blue-pale);}\n  .hotspot{position:absolute; width:12px; height:12px; border-radius:50%; background:var(--blue);\n    border:2px solid #fff; box-shadow:0 0 0 3px rgba(47,125,237,.25); cursor:pointer; z-index:3; transition:transform .15s;}\n  .hotspot:hover{transform:scale(1.35);}\n  .hotspot.active{background:var(--amber); box-shadow:0 0 0 4px rgba(245,165,36,.3);}\n\n  /* KPI context label */\n  .kpi-context{display:flex; align-items:center; gap:8px; margin-bottom:10px; font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--muted);}\n  .kpi-context b{color:var(--blue-dark); font-weight:700;}\n  .kpi-context .scope-chip{background:var(--blue-pale); color:var(--blue-dark); padding:3px 9px; border-radius:6px; font-weight:700;}\n  .map-expand-btn{position:absolute; top:12px; right:12px; background:#fff; border:1px solid var(--border-strong);\n    border-radius:8px; padding:7px 12px; font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:600;\n    color:var(--muted); display:flex; align-items:center; gap:6px; box-shadow:var(--shadow); z-index:5;}\n  .map-strip.expanded{height:80vh; position:relative; z-index:90;}\n  .map-overlay-close{display:none; position:fixed; inset:0; background:rgba(15,23,42,.5); z-index:80;}\n  .map-overlay-close.open{display:block;}\n  .scope-badge{display:inline-flex; align-items:center; gap:7px; background:var(--blue-pale); color:var(--blue-dark);\n    border:1px solid #C7DEFB; border-radius:9px; padding:6px 12px; font-family:'JetBrains Mono',monospace;\n    font-size:11.5px; font-weight:700; margin-bottom:12px;}\n  .scope-badge .sb-sub{font-weight:500; color:var(--blue); opacity:.8; font-size:10.5px;}\n  .dot-ind{width:7px;height:7px;border-radius:50%;display:inline-block; flex-shrink:0;}\n  .dot-ind.teal{background:var(--teal);}\n  .dot-ind.blue{background:var(--blue);}\n\n  /* KPI row */\n  .kpi-row{display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-bottom:20px;}\n  .kpi{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; box-shadow:var(--shadow);}\n  .kpi.highlight{border-color:var(--amber); background:var(--amber-pale);}\n  .kpi-label{font-size:10px; font-family:'JetBrains Mono',monospace; color:var(--muted); letter-spacing:.4px; margin-bottom:8px; display:flex; justify-content:space-between;}\n  .kpi-val{font-family:'JetBrains Mono',monospace; font-size:26px; font-weight:800;}\n  .kpi-sub{font-size:10.5px; color:var(--muted); margin-top:4px; font-family:'JetBrains Mono',monospace;}\n  .kpi-sub.up{color:var(--teal);}\n  .kpi-sub.down{color:var(--red);}\n  .kpi.highlight .kpi-val{color:var(--amber); display:flex; align-items:center; gap:8px;}\n  .badge-mod{font-size:10px; background:var(--amber); color:#fff; padding:2px 7px; border-radius:6px; font-weight:700;}\n\n  /* Tabs */\n  .tabbar{display:flex; align-items:center; border-bottom:1px solid var(--border); margin-bottom:20px;}\n  .tab{padding:10px 4px; margin-right:26px; font-family:'JetBrains Mono',monospace; font-size:12.5px; font-weight:600;\n    color:var(--muted); border-bottom:2px solid transparent; background:none; border-top:none;border-left:none;border-right:none;}\n  .tab.active{color:var(--blue); border-bottom-color:var(--blue);}\n  .tab-right{margin-left:auto; display:flex; gap:16px;}\n  .tab-right .tab{margin-right:0; color:var(--muted-2);}\n\n  /* Cards / grid helpers */\n  .grid-2{display:grid; grid-template-columns:2fr 1fr; gap:16px;}\n  .grid-3{display:grid; grid-template-columns:repeat(3,1fr); gap:16px;}\n  .card{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:18px; box-shadow:var(--shadow); margin-bottom:16px;}\n  .card h3{font-size:14.5px; display:flex; align-items:center; gap:8px;}\n  .card .sub{font-size:11.5px; color:var(--muted); margin:4px 0 14px;}\n\n  .mini-grid{display:grid; grid-template-columns:1.15fr 0.85fr 1.15fr 1fr; gap:0; border:1px solid var(--border); border-radius:10px; overflow:hidden;}\n  .mini-col{padding:14px; border-right:1px solid var(--border);}\n  .mini-col:last-child{border-right:none;}\n  .mini-col-title{font-size:10px; font-family:'JetBrains Mono',monospace; color:var(--muted); margin-bottom:10px; display:flex; align-items:center; gap:6px;}\n  .stat-line{display:flex; justify-content:space-between; align-items:baseline; padding:6px 0;}\n  .stat-line .l{font-size:10px; color:var(--muted); font-family:'JetBrains Mono',monospace;}\n  .stat-line .v{font-family:'JetBrains Mono',monospace; font-weight:700; font-size:16px;}\n  .conn-center{display:flex; flex-direction:column; align-items:center; justify-content:center; padding:14px; background:var(--amber-pale);}\n  .conn-center .ring{width:64px;height:64px; border-width:5px;}\n\n  .row-card{display:flex; align-items:center; gap:14px; padding:16px; margin-bottom:10px;}\n  .row-icon{width:38px;height:38px;border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:17px; flex-shrink:0;}\n  .row-icon.blue{background:var(--blue-pale);}\n  .row-icon.teal{background:var(--teal-pale);}\n  .row-icon.amber{background:var(--amber-pale);}\n  .row-title{font-weight:700; font-size:13px;}\n  .row-sub{font-size:11px; color:var(--muted);}\n  .row-score{margin-left:auto; font-family:'JetBrains Mono',monospace; font-weight:700; font-size:12px;\n    padding:5px 10px; border-radius:8px; border:1px solid var(--border-strong);}\n  .row-score.good{color:var(--teal); border-color:var(--teal); background:var(--teal-pale);}\n  .row-score.mod{color:var(--amber); border-color:var(--amber); background:var(--amber-pale);}\n\n  .chips{display:flex; gap:6px; flex-wrap:wrap; margin-top:12px;}\n  .chip{font-family:'JetBrains Mono',monospace; font-size:10.5px; padding:5px 9px; border-radius:7px; font-weight:600;}\n  .chip.ok{background:var(--teal-pale); color:#0C8457;}\n  .chip.bad{background:var(--red-pale); color:#C13232;}\n  .chip.mid{background:var(--amber-pale); color:#B4790F;}\n\n  .forecast-trio{display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px;}\n  .fc-box{background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:12px; text-align:center;}\n  .fc-box .h{font-size:9.5px; color:var(--muted); font-family:'JetBrains Mono',monospace;}\n  .fc-box .n{font-family:'JetBrains Mono',monospace; font-weight:800; font-size:20px; margin:4px 0;}\n  .fc-box .u{font-size:9.5px; color:var(--muted); font-family:'JetBrains Mono',monospace;}\n  .fc-box.g .n{color:var(--teal);} .fc-box.a .n{color:var(--amber);} .fc-box.r .n{color:var(--red);}\n\n  /* leaderboard bars */\n  .bars{display:flex; align-items:flex-end; gap:10px; height:130px; margin:14px 0 6px; padding:0 4px;}\n  .bar-col{flex:1; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; height:100%;}\n  .bar-val{font-family:'JetBrains Mono',monospace; font-size:10.5px; font-weight:700; margin-bottom:4px;}\n  .bar{width:100%; border-radius:5px 5px 0 0;}\n  .bar-lbl{font-size:9px; color:var(--muted); margin-top:6px; font-family:'JetBrains Mono',monospace; text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:60px;}\n  table{width:100%; border-collapse:collapse; font-size:12px;}\n  th{text-align:left; font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--muted); font-weight:600; padding:8px 6px; border-bottom:1px solid var(--border);}\n  td{padding:9px 6px; border-bottom:1px solid var(--border); font-family:'JetBrains Mono',monospace; font-size:12px;}\n  tr.selected td{background:var(--blue-pale);}\n  .verdict{display:flex; align-items:center; gap:6px; font-weight:600;}\n  .dot{width:7px;height:7px;border-radius:50%;display:inline-block;}\n  .dot.g{background:var(--teal);} .dot.a{background:var(--amber);} .dot.r{background:var(--red);}\n\n  .price-tiles{display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-bottom:14px;}\n  .price-tile{background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:12px; text-align:center;}\n  .price-tile .l{font-size:9px; color:var(--muted); font-family:'JetBrains Mono',monospace;}\n  .price-tile .v{font-family:'JetBrains Mono',monospace; font-weight:800; font-size:15px; margin-top:4px;}\n  .vfm-list .vfm-row{display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px dashed var(--border); font-size:11.5px;}\n  .vfm-rank{color:var(--muted); font-family:'JetBrains Mono',monospace; margin-right:6px;}\n\n  /* heatmap */\n  .heatmap{display:grid; grid-template-columns:34px repeat(24,1fr); gap:3px; font-family:'JetBrains Mono',monospace;}\n  .heatmap .hlabel{font-size:9px; color:var(--muted); display:flex; align-items:center;}\n  .heatmap .hcell{height:16px; border-radius:2px;}\n  .heatmap .hhead{font-size:8px; color:var(--muted-2); text-align:center;}\n\n  /* line chart (svg) */\n  .chart-wrap{width:100%; overflow-x:auto;}\n\n  /* score weights modal */\n  .modal-overlay{display:none; position:fixed; inset:0; background:rgba(15,23,42,.45); z-index:100; align-items:center; justify-content:center;}\n  .modal-overlay.open{display:flex;}\n  .modal{background:#fff; border-radius:16px; width:480px; max-width:90vw; padding:26px; box-shadow:0 30px 60px rgba(0,0,0,.25);}\n  .modal-head{display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;}\n  .modal-head h3{font-size:15px;}\n  .close-x{background:none;border:none;font-size:18px;color:var(--muted);}\n  .formula{display:flex; align-items:center; justify-content:center; gap:12px; margin-bottom:20px; font-family:'JetBrains Mono',monospace;}\n  .formula .big-ring{width:64px;height:64px;border-radius:50%;border:5px solid var(--amber); display:flex;align-items:center;justify-content:center; font-weight:800; font-size:22px; color:var(--amber);}\n  .formula .term{text-align:center;}\n  .formula .term .n{font-size:20px; font-weight:800;}\n  .formula .term.blue .n{color:var(--blue);} .formula .term.teal .n{color:var(--teal);} .formula .term.red .n{color:var(--red);}\n  .formula .term .l{font-size:9px; color:var(--muted);}\n  .presets{display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-bottom:20px;}\n  .preset{border:1px solid var(--border-strong); border-radius:10px; padding:10px; font-size:11px; font-family:'JetBrains Mono',monospace; background:#fff;}\n  .preset.active{border-color:var(--blue); background:var(--blue-pale); color:var(--blue-dark);}\n  .preset b{display:block; font-size:11.5px; margin-bottom:2px;}\n  .slider-row{margin-bottom:16px;}\n  .slider-row .sl-head{display:flex; justify-content:space-between; font-size:11.5px; font-weight:600; margin-bottom:6px;}\n  input[type=range]{width:100%; accent-color:var(--blue);}\n  .apply-btn{width:100%; background:var(--blue); color:#fff; border:none; padding:13px; border-radius:10px; font-family:'JetBrains Mono',monospace; font-weight:700; font-size:12.5px;}\n\n  /* glossary */\n  .acc{border:1px solid var(--border); border-radius:10px; margin-bottom:8px; overflow:hidden;}\n  .acc-head{padding:12px 14px; display:flex; justify-content:space-between; align-items:center; font-size:12.5px; font-weight:600; background:var(--bg);}\n  .acc-body{display:none; padding:14px; font-size:12.5px; line-height:1.7; color:#374151;}\n  .acc.open .acc-body{display:block;}\n  .acc.open .acc-head{color:var(--blue-dark);}\n\n  .footer-note{text-align:center; font-size:11px; color:var(--muted-2); font-family:'JetBrains Mono',monospace; margin-top:30px;}\n\n  .info-i{width:14px;height:14px; border-radius:50%; border:1px solid var(--muted-2); color:var(--muted-2); font-size:9px; display:inline-flex; align-items:center; justify-content:center;}\n  .flex-between{display:flex; justify-content:space-between; align-items:center;}\n"


def render_formula_card(comps: dict, weights: dict, basis: str) -> str:
    """The mockup's live-formula block as plain v3 HTML. No JS: Streamlit
    reruns on every slider move, so the numbers recompute server-side."""
    bus = comps.get("bus_frequency_score") or 0.0
    stab = comps.get("taxi_stability_score") or 0.0
    fric = comps.get("friction_ratio") or 0.0
    bus_share = weights["bus"] / 100.0
    taxi_share = 1.0 - bus_share
    stab_share = weights["stab"] / 100.0
    fric_share = 1.0 - stab_share
    bus_term = round(bus_share * bus)
    stab_term = round(taxi_share * stab_share * stab)
    fric_term = round(taxi_share * fric_share * fric * 100.0)
    score = max(0, min(100, bus_term + stab_term - fric_term))
    return f"""
<div style="font-size:10px; font-family:'JetBrains Mono',monospace; color:#6B7686; margin-bottom:8px;">
  LIVE FORMULA · baseline from {basis}</div>
<div class="formula" style="flex-wrap:wrap;">
  <div class="big-ring">{score}</div><span style="color:#0F172A;">=</span>
  <div class="term blue"><div class="n">{bus_term}</div><div class="l">Bus</div></div><span style="color:#0F172A;">+</span>
  <span style="font-size:16px; color:#8B95A5;">(</span>
  <div class="term teal"><div class="n">{stab_term}</div><div class="l">Stability</div></div><span style="color:#0F172A;">−</span>
  <div class="term red"><div class="n">{fric_term}</div><div class="l">Friction</div></div>
  <span style="font-size:16px; color:#8B95A5;">)</span>
</div>
<div style="font-size:10.5px; text-align:center; color:#6B7686; font-family:'JetBrains Mono',monospace; margin:-6px 0 4px;">
  Score = Bus + Taxi · Taxi = Stability − Friction</div>"""



# ─────────────────────────────────────────────────────────────────────────────
# Chrome + per-tab HTML fragments — all plain HTML rendered via st.markdown,
# no iframe needed for any of it (nothing here requires real JavaScript).
# ─────────────────────────────────────────────────────────────────────────────
def build_chrome_and_kpis(selected: dict, data: dict, sel_day: str = "",
                          sel_hour: int | None = None,
                          expected_taxis: float | None = None,
                          custom_weights: bool = False) -> tuple[str, str, str, dict]:
    selected_label = selected["label"]
    is_average = selected["slug"] == "average"

    fw, fw_color = friction_word(data["friction"])
    price_txt = f"S${data['price']:,.0f}" if data["price"] else "—"
    score_txt = data["conn_score"] if data["conn_score"] is not None else "—"
    verdict_txt = data["verdict"] or "OFFLINE"
    verdict_color = {"GOOD": "#10B981", "MODERATE": "#F5A524", "POOR": "#EF4444", "OFFLINE": "#8B95A5"}.get(verdict_txt, "#F5A524")
    scope_text = ("🇸🇬 Singapore Average · across 55 planning areas" if is_average
                  else f"📍 {selected_label} · district detail")

    topnav_html = f"""
  <header class="topnav">
    <div class="brand"><div class="mark">A</div>SG Liveability</div>
    <div class="nav-right" style="margin-left:auto;">
      <div class="pill-select"><span class="dotmark"></span>{selected_label}</div>
    </div>
  </header>
"""

    fc_time = (f" · {sel_day.upper()} {sel_hour:02d}:00"
               if sel_day and sel_hour is not None else " · LIVE")
    expected_txt = f"~{expected_taxis:.0f}" if expected_taxis is not None else "—"
    floatcard_html = f"""
  <div class="float-card" style="width:100%;">
    <div class="fc-head">{selected_label.upper()}{fc_time}</div>
    <div class="ring" style="border-color:{verdict_color}; color:{verdict_color};">{score_txt}</div>
    <div class="fc-verdict" style="color:{verdict_color};">{verdict_txt}</div>
    <div class="fc-verdict-sub">Connectivity Score · {selected_label}</div>
    <div class="fc-row"><span>🚕 taxis nearby</span><span>{data['live_taxis']}</span></div>
    <div class="fc-row" title="Historical average taxi count for the selected day + hour"><span>🔮 expected at this time</span><span>{expected_txt}</span></div>
    <div class="fc-row"><span>🚌 bus stops</span><span>{data['bus']['stops_in_bbox'] if data.get('bus') else '—'}</span></div>
    <div class="fc-row"><span>🚨 active alerts</span><span>{data['alerts']}</span></div>
  </div>
"""

    kpis_html = f"""
  <div class="map-hint">💡 Click a district on the map to select it — or search a postal code.{' · Map colors still use the DEFAULT weights.' if custom_weights else ''}</div>

  <div class="scope-badge">{scope_text}</div>

  <div class="kpi-row">
    <div class="kpi" title="Number of taxis available in this district right now — LTA data, updated every 60 seconds"><div class="kpi-label">LIVE TAXIS ⓘ</div><div class="kpi-val">{data['live_taxis']}</div><div class="kpi-sub">this minute</div></div>
    <div class="kpi" title="Average taxi count over the last 60 minutes"><div class="kpi-label">AVERAGE TAXI ⓘ</div><div class="kpi-val">{data['avg_taxi']}</div><div class="kpi-sub">60-min rolling avg</div></div>
    <div class="kpi" title="Friction = how much demand is eating into taxi supply (0 = easy, 1 = very hard to get a taxi)"><div class="kpi-label">GETTING A TAXI ⓘ</div><div class="kpi-val" style="color:{fw_color}">{fw}</div><div class="kpi-sub">friction {data['friction']:.3f}</div></div>
    <div class="kpi" title="Anomaly alerts triggered in the last 24 hours (LOW_TAXI / HIGH_FLUX / BUS_GAP)"><div class="kpi-label">ALERTS ⓘ</div><div class="kpi-val" style="color:{alert_kpi_color(data['alerts'])}">{data['alerts']}</div><div class="kpi-sub">last 24h</div></div>
    <div class="kpi highlight" title="Bus frequency ×50% + taxi stability ×30% − friction ×20% (adjustable in Score Weights)"><div class="kpi-label">CONNECTIVITY SCORE ⓘ</div>
      <div class="kpi-val">{score_txt} <span class="badge-mod" style="background:{verdict_color}">{verdict_txt}</span></div>
      <div class="kpi-sub">/100</div></div>
    <div class="kpi" title="Average resale price, last 12 months, 4 ROOM flats"><div class="kpi-label">AVG HDB PRICE ⓘ</div><div class="kpi-val">{price_txt}</div><div class="kpi-sub">last 12mo · 4 ROOM</div></div>
  </div>
"""
    if data["live"] and data.get("bus"):
        b = data["bus"]
        baseline = dict(bus=b['bus_frequency_score']/100, stability=b['taxi_stability_score']/100,
                        friction=min(1.0, data['friction']))
    else:
        baseline = dict(bus=0.73, stability=0.87, friction=0.68)
    return topnav_html, floatcard_html, kpis_html, baseline


@st.cache_data(ttl=60)
def fetch_average_history(minutes: int) -> list[dict]:
    """Citywide taxi history: sum per-minute counts across all districts."""
    bucket: dict[str, int] = {}
    for o in get_district_options():
        if o["slug"] == "average":
            continue
        for s in fetch_snapshots(o["slug"], minutes=minutes):
            key = str(s["fetched_at"])[:16]  # minute bucket
            bucket[key] = bucket.get(key, 0) + int(s["taxi_count"])
    return [{"fetched_at": k + ":00", "taxi_count": v, "flux": None}
            for k, v in sorted(bucket.items())]


def build_history_card(selected: dict, history_min: int) -> str:
    """Full-width taxi history ±2σ + forecast diamonds + flux bars (parity
    3.1/3.2 + rubric predicted-vs-actual overlay)."""
    try:
        if selected["slug"] == "average":
            snaps = fetch_average_history(history_min)
            preds = []
        else:
            snaps = fetch_snapshots(selected["slug"], minutes=history_min)
            preds = fetch_predictions(selected["slug"], limit=50)
        hist_svg = render_history_chart(snaps, preds)
        flux_svg = render_flux_chart(snaps)
    except Exception:
        hist_svg, flux_svg = "", ""
    body = hist_svg or render_coming_soon(
        "Needs at least 2 taxi snapshots in the selected window — run the "
        "pipeline (python main.py) or widen the window above.")
    flux_block = (f'<h4 style="font-size:12.5px; margin-top:14px; color:#0F172A;">Taxi flux (inflow / outflow)</h4>'
                  f'{flux_svg}') if flux_svg else ""
    hours = history_min // 60
    win_txt = f"{hours}h" if history_min % 60 == 0 else f"{history_min} min"
    return (f'<div class="card"><h3>📈 Taxi availability — history &amp; forecast</h3>'
            f'<div class="sub">Shaded band = normal range (±2σ) · ◆ filled = upcoming ML forecasts · '
            f'◇ hollow = earlier predictions vs what actually happened · rolling past {win_txt}</div>'
            f'{body}{flux_block}</div>')


@st.cache_data(ttl=3600)
def _onemap_local_context(slug: str, lat: float, lng: float) -> dict:
    """Nearest MRT + CBD commute for a district centroid. Cached hard —
    these are slow external calls and centroids don't move."""
    out = {"mrt": None, "cbd": None}
    try:
        from hdb.onemap_services import get_nearest_mrt_summary, get_pt_commute_time
        try:
            out["mrt"] = get_nearest_mrt_summary(lat, lng)
        except Exception:
            pass
        try:
            out["cbd"] = get_pt_commute_time(lat, lng)
        except Exception:
            pass
    except Exception:
        pass
    return out


def _peak_chip(p: dict) -> str:
    rating = str(p.get("rating", ""))
    label = str(p.get("time_label", "")).replace(":00", "").lower()
    if "good" in rating.lower():
        return f'<span class="chip ok" title="{p.get("advice", "")}">{label} ✓</span>'
    if "mod" in rating.lower():
        return f'<span class="chip mid" title="{p.get("advice", "")}">{label} ~</span>'
    return f'<span class="chip bad" title="{p.get("advice", "")}">{label} ✗</span>'


def build_local_snapshot(selected: dict, data: dict, extra: dict) -> str:
    """Mockup's Local Snapshot rows: MRT / Bus / Taxi + peak chips / CBD.
    Every row degrades to an em-dash independently — the card never dies."""
    is_average = selected["slug"] == "average"
    ctx = {"mrt": None, "cbd": None}
    if not is_average and selected.get("bbox"):
        b = selected["bbox"]  # (min_lon, max_lon, min_lat, max_lat)
        ctx = _onemap_local_context(selected["slug"], (b[2] + b[3]) / 2, (b[0] + b[1]) / 2)

    if is_average:
        mrt_sub, mrt_badge, mrt_cls = "6 lines · 134 stations citywide", "—", "good"
    elif ctx["mrt"]:
        m = ctx["mrt"]
        mrt_sub = f'{m.get("name", "?")} · {m.get("distance_label", "")} · ~{m.get("walking_min", "?")} min walk'
        walk = m.get("walking_min") or 99
        mrt_badge, mrt_cls = ("Near", "good") if walk <= 10 else ("Far", "mod")
    else:
        mrt_sub, mrt_badge, mrt_cls = "needs OneMap (token / network)", "—", "mod"

    bus = data.get("bus")
    if bus:
        bus_sub = f'{bus["stops_in_bbox"]} stops · every ~{bus["avg_bus_headway_min"]:.0f} min · {bus["num_unique_routes"]} routes'
        bscore = bus["bus_frequency_score"]
        bus_badge = f"{bscore:.0f}/100"
        bus_cls = "good" if bscore >= 75 else "mod"
    else:
        bus_sub, bus_badge, bus_cls = "needs the live pipeline (python main.py)", "—", "mod"

    fw, _ = friction_word(data["friction"])
    taxi_sub = f'{data["live_taxis"]} nearby · friction {data["friction"]:.3f}'
    taxi_badge, taxi_cls = (fw, "good" if fw == "Easy" else "mod")

    peaks = extra.get("peaks") or []
    chips = ("".join(_peak_chip(p) for p in peaks[:6])
             or '<span class="chip mid" style="opacity:.7;">peak ratings need more history</span>')

    if ctx["cbd"]:
        mins = ctx["cbd"].get("total_time_min")
        cbd_sub = f"{mins:.0f} min by public transport" if mins else "—"
        cbd_badge, cbd_cls = ("OK", "good") if (mins or 99) <= 35 else ("Long", "mod")
    else:
        cbd_sub, cbd_badge, cbd_cls = ("—" if is_average else "needs OneMap routing"), "—", "mod"

    def row(icon_cls, icon, title, sub, badge, badge_cls, pad="12px 0"):
        return (f'<div class="row-card" style="padding:{pad};">'
                f'<div class="row-icon {icon_cls}">{icon}</div>'
                f'<div><div class="row-title">{title}</div><div class="row-sub">{sub}</div></div>'
                f'<div class="row-score {badge_cls}">{badge}</div></div>')

    hr = '<div style="border-top:1px solid var(--border);"></div>'
    return (row("blue", "🚇", "MRT Network", mrt_sub, mrt_badge, mrt_cls)
            + hr + row("teal", "🚌", "Bus Coverage", bus_sub, bus_badge, bus_cls)
            + hr + row("amber", "🚕", "Taxi Availability", taxi_sub, taxi_badge, taxi_cls, pad="12px 0 6px")
            + f'<div class="chips" style="justify-content:center; margin-top:2px;">{chips}</div>'
            + '<div style="border-top:1px solid var(--border); margin-top:14px;"></div>'
            + row("blue", "🏢", "Commute to CBD", cbd_sub, cbd_badge, cbd_cls, pad="12px 0 0"))


def render_score_breakdown_bars(bus: dict, friction: float) -> str:
    """3 labelled progress bars under the timeliness grid (parity 3.6)."""
    fric_pct = min(100.0, friction * 100.0)
    items = [
        ("Bus frequency", bus.get("bus_frequency_score") or 0.0, False),
        ("Taxi stability", bus.get("taxi_stability_score") or 0.0, False),
        ("Friction penalty", fric_pct, True),
    ]
    bars = ""
    for label, val, inverse in items:
        if inverse:
            verdict = "High" if val > 50 else "Low"
            v_color = "#EF4444" if val > 50 else "#10B981"
        else:
            v_label, v_color = verdict_for(val)[0].title(), verdict_for(val)[1]
            verdict = v_label
        bars += (
            f'<div style="flex:1;">'
            f'<div style="display:flex; justify-content:space-between; font-size:10px; '
            f"font-family:'JetBrains Mono',monospace; color:#6B7686; margin-bottom:4px;\">"
            f'<span>{label}</span><span style="color:{v_color}; font-weight:700;">{val:.1f}/100 — {verdict}</span></div>'
            f'<div style="height:6px; border-radius:3px; background:var(--bg); border:1px solid var(--border);">'
            f'<div style="width:{min(100.0, val):.1f}%; height:100%; border-radius:3px; background:var(--blue);"></div>'
            f'</div></div>')
    return f'<div style="display:flex; gap:16px; margin-top:14px;">{bars}</div>'


def build_price_snapshot(selected: dict, extra: dict) -> str:
    """Mockup Price Snapshot: 3 tiles + Top-5 value-for-money list.
    Tiles cover the last 3 months with the range spelled out."""
    SNAPSHOT_MONTHS = 3
    ts = _town_summary_cached("4 ROOM", SNAPSHOT_MONTHS)
    if ts is None or ts.empty:
        ts = extra.get("town_summary")  # fall back to the 12-month set
    if ts is None or ts.empty:
        return render_coming_soon("No price data available.")
    match = ts[ts["town"].str.lower().str.replace(" ", "_") == selected["slug"]]
    if not match.empty:
        row = match.iloc[0]
        avg, med, txn = row["avg_price"], row.get("median_price"), int(row["num_transactions"])
    else:
        avg = ts["avg_price"].mean()
        med = ts["median_price"].median() if "median_price" in ts else None
        txn = int(ts["num_transactions"].sum())
    med_txt = f"S${med:,.0f}" if med is not None and not pd.isna(med) else "—"

    _now = datetime.now(SGT)
    _sm, _sy = _now.month - SNAPSHOT_MONTHS, _now.year
    if _sm <= 0:
        _sm += 12
        _sy -= 1
    range_txt = f"{datetime(_sy, _sm, 1).strftime('%b')} – {_now.strftime('%b %Y')}"

    tiles = (f'<div style="font-size:10px; font-family:\'JetBrains Mono\',monospace; color:#6B7686; '
             f'margin-bottom:6px;">LAST {SNAPSHOT_MONTHS} MONTHS · {range_txt.upper()} · 4 ROOM</div>'
             f'<div class="price-tiles">'
             f'<div class="price-tile"><div class="l">AVG PRICE</div><div class="v">S${avg:,.0f}</div></div>'
             f'<div class="price-tile"><div class="l">MEDIAN</div><div class="v">{med_txt}</div></div>'
             f'<div class="price-tile"><div class="l">TRANSACTIONS</div><div class="v">{txn:,}</div></div></div>')

    vfm = extra.get("vfm")
    if vfm is not None and not vfm.empty:
        rows = ""
        for i, (_, r) in enumerate(vfm.head(5).iterrows(), 1):
            price = f'S${r["avg_price"]:,.0f}' if "avg_price" in r else ""
            rows += (f'<div class="vfm-row"><span style="color:#0F172A;"><span class="vfm-rank">{i}</span>'
                     f'{str(r["town"]).title()}</span><span style="color:#10B981; font-weight:700;">'
                     f'{r["vfm_score"]:.1f} <span style="color:#6B7686; font-weight:400;">{price}</span></span></div>')
        vfm_html = (f'<div style="font-size:10px; font-family:\'JetBrains Mono\',monospace; color:#6B7686; '
                    f'margin-bottom:6px;">TOP 5 VALUE-FOR-MONEY</div><div class="vfm-list">{rows}</div>')
    else:
        vfm_html = ('<div style="font-size:10.5px; color:#6B7686; text-align:center; padding:6px;">'
                    'Value-for-money ranking needs the live pipeline running.</div>')
    return tiles + vfm_html


def build_overview_html(selected: dict, data: dict, extra: dict) -> str:
    selected_label = selected["label"]
    score_txt = data["conn_score"] if data["conn_score"] is not None else "—"
    verdict_txt = data["verdict"] or "OFFLINE"
    verdict_color = {"GOOD": "#10B981", "MODERATE": "#F5A524", "POOR": "#EF4444", "OFFLINE": "#8B95A5"}.get(verdict_txt, "#F5A524")

    if data["live"] and data.get("bus"):
        b = data["bus"]
        timeliness_html = f"""<div class="mini-grid">
          <div class="mini-col"><div class="mini-col-title">🚌 BUS</div>
            <div class="stat-line"><span class="l">STOPS IN ZONE</span><span class="v">{b['stops_in_bbox']}</span></div>
            <div class="stat-line"><span class="l">AVG HEADWAY</span><span class="v">{b['avg_bus_headway_min']:.1f} min</span></div>
            <div class="stat-line"><span class="l">BUS SCORE</span><span class="v" style="color:var(--teal)">{b['bus_frequency_score']:.0f}</span></div>
            <div class="stat-line"><span class="l">REDUNDANCY</span><span class="v" style="color:var(--teal)">{b['bus_redundancy_score']:.0f} <span style="font-size:9px;color:var(--muted);font-weight:400;">({b['num_unique_routes']} routes)</span></span></div>
          </div>
          <div class="mini-col conn-center" style="background:{verdict_color}22;">
            <div class="ring" style="border-color:{verdict_color}; color:{verdict_color};">{score_txt}</div>
            <div style="font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:700; color:{verdict_color};">{verdict_txt}</div>
          </div>
          <div class="mini-col"><div class="mini-col-title">🚕 TAXI</div>
            <div class="stat-line"><span class="l">AVAILABLE</span><span class="v">{data['live_taxis']}</span></div>
            <div class="stat-line"><span class="l">FRICTION</span><span class="v">{data['friction']:.3f}</span></div>
            <div class="stat-line"><span class="l">MEAN (60M)</span><span class="v">{data['avg_taxi']}</span></div>
            <div class="stat-line"><span class="l">STABILITY</span><span class="v" style="color:var(--teal)">{b['taxi_stability_score']:.0f}</span></div>
          </div>
          <div class="mini-col"><div class="mini-col-title">🔮 TAXI FORECAST</div>
            {render_forecast_col(data['forecast'])}
          </div>
        </div>
        {render_score_breakdown_bars(b, data['friction'])}"""
    else:
        timeliness_html = render_coming_soon("Bus + live connectivity detail needs the live pipeline "
                                             "(python main.py) running. Taxi numbers above are still real.")

    leaderboard_html = render_leaderboard(extra.get("rank") or [], highlight_district=None if selected["slug"]=="average" else selected_label)
    price_snapshot_html = (build_price_snapshot(selected, extra) if HDB_AVAILABLE
                           else render_coming_soon("hdb.duckdb not found."))
    alerts_html = render_alerts(data.get("alerts_list", []), data.get("alerts"))

    return f"""
    <div class="grid-2">
      <div>
        <div class="card"><h3>⏱ Transport Timeliness</h3>
          <div class="sub">Real-time bus + taxi service quality · {selected_label}</div>
          {timeliness_html}
        </div>
        <div class="card"><h3>🏆 District Leaderboard</h3>
          <div class="sub">Connectivity score ranking across districts</div>{leaderboard_html}</div>
      </div>
      <div>
        <div class="card"><h3>📍 Local Snapshot</h3>
          <div class="sub">{'Singapore average — pick a district for local detail' if selected["slug"] == "average" else f'Local context · {selected_label}'}</div>
          {build_local_snapshot(selected, data, extra)}</div>
        <div class="card"><h3>💰 Price Snapshot</h3>
          <div class="sub">Resale prices · {selected_label}</div>{price_snapshot_html}</div>
        <div class="card"><h3>🚨 Anomaly Alerts</h3>{alerts_html}</div>
      </div>
    </div>"""


def _mae_chip(mae: float) -> str:
    if mae <= 3.5:
        return '<span class="chip ok">✓ GREAT</span>'
    if mae <= 4.5:
        return '<span class="chip mid">✓ GOOD</span>'
    return '<span class="chip mid">~ OK</span>'


def render_model_performance(slug: str) -> str:
    """MAE per horizon with plain-English badges (parity 3.4). Falls back to
    the model's training accuracy when no daily-eval row exists yet."""
    note = "Training accuracy shown · live eval runs daily at 08:00 SGT"
    lines = ""
    try:
        rows = [r for r in fetch_latest_metrics() if r.get("district") == slug]
    except Exception:
        rows = []
    if rows and rows[0].get("mae"):
        r = rows[0]
        mae, rmse = float(r["mae"]), float(r["rmse"] or 0)
        note = f"Evaluated {str(r['evaluated_at'])[:16]} · n={r['n_samples']}"
        lines = (f'<div class="stat-line"><span class="l">MAE</span><span class="v" style="font-size:13px;">{mae:.2f} {_mae_chip(mae)}</span></div>'
                 f'<div class="stat-line"><span class="l">RMSE</span><span class="v" style="font-size:13px;">{rmse:.2f}</span></div>')
    else:
        for label, mae in (("+30 MIN", 3.08), ("+60 MIN", 3.92), ("+2 HR", 5.03)):
            lines += (f'<div class="stat-line"><span class="l">{label}</span>'
                      f'<span class="v" style="font-size:12px;" title="off by ~{mae:.1f} taxis on average">{_mae_chip(mae)}</span></div>')
    explainer = ('<div style="margin-top:12px; background:var(--blue-pale); border-radius:8px; padding:10px; '
                 'font-size:11px; color:var(--blue-dark); line-height:1.5;">💡 MAE = how many taxis our '
                 'prediction is off by on average. E.g. +30min MAE 3.1 means a prediction of 20 is usually '
                 'right between 17–23.</div>')
    return f'<div class="sub">{note}</div>{lines}{explainer}'


ALERT_LEGEND = """
<div style="font-size:9.5px; font-family:'JetBrains Mono',monospace; color:#6B7686; margin:10px 0 4px;">ALERT TYPES</div>
<div class="stat-line"><span class="l">🔴 LOW_TAXI</span><span class="v" style="font-size:11px; font-weight:500; color:#6B7686;">supply drops &gt;2σ below normal</span></div>
<div class="stat-line"><span class="l">🟡 HIGH_FLUX</span><span class="v" style="font-size:11px; font-weight:500; color:#6B7686;">±15 taxis in one minute</span></div>
<div class="stat-line"><span class="l">🔵 BUS_GAP</span><span class="v" style="font-size:11px; font-weight:500; color:#6B7686;">avg wait exceeds 8 min</span></div>"""


def render_forecast_trio(forecast: dict) -> str:
    v30, v60, v120 = forecast.get(30), forecast.get(60), forecast.get(120)
    def box(cls, label, v):
        val = f"{v:.0f}" if v is not None else "—"
        return f'<div class="fc-box {cls}"><div class="h">{label}</div><div class="n">{val}</div><div class="u">taxis</div></div>'
    return (f'<div class="forecast-trio">{box("g", "+30 MIN", v30)}{box("a", "+60 MIN", v60)}'
            f'{box("r", "+2 HR", v120)}</div>')


@st.cache_data(ttl=60)
def _evaluate_bbox_cached(bbox: tuple) -> dict | None:
    return call_api("/evaluate", {"min_lon": bbox[0], "max_lon": bbox[1],
                                  "min_lat": bbox[2], "max_lat": bbox[3]}, timeout=6.0)


def build_compare_html(a: dict, b: dict, weights: dict) -> str:
    """Side-by-side district comparison (mockup Compare tab). Every metric
    row degrades to an em-dash independently."""
    def side(o: dict) -> dict:
        ev = _evaluate_bbox_cached(o["bbox"]) if o.get("bbox") else None
        s = apply_weights(ev, weights) if ev else None
        bx = o["bbox"]
        ctx = (_onemap_local_context(o["slug"], (bx[2] + bx[3]) / 2, (bx[0] + bx[1]) / 2)
               if bx else {"mrt": None, "cbd": None})
        return {"ev": ev or {}, "score": s, "price": get_avg_price(o["slug"]), "ctx": ctx}

    A, B = side(a), side(b)

    def score_cell(s):
        if s is None:
            return '<td style="color:#8B95A5;">—</td>'
        _, color = verdict_for(s)
        return f'<td style="color:{color}; font-weight:700;">{s:.0f}</td>'

    def num_cell(v, fmt="{:.0f}"):
        return f'<td>{fmt.format(v)}</td>' if v is not None else '<td style="color:#8B95A5;">—</td>'

    def mrt_cell(ctx):
        m = ctx.get("mrt")
        return (f'<td>{m["name"]} · {m.get("distance_label", "")}</td>' if m
                else '<td style="color:#8B95A5;">—</td>')

    def cbd_cell(ctx):
        c = ctx.get("cbd")
        return (f'<td>{c["total_time_min"]:.0f} min</td>' if c and c.get("total_time_min")
                else '<td style="color:#8B95A5;">—</td>')

    rows = (
        f'<tr><td>Connectivity Score</td>{score_cell(A["score"])}{score_cell(B["score"])}</tr>'
        f'<tr><td>Bus Score</td>{num_cell(A["ev"].get("bus_frequency_score"))}{num_cell(B["ev"].get("bus_frequency_score"))}</tr>'
        f'<tr><td>Taxi Stability</td>{num_cell(A["ev"].get("taxi_stability_score"))}{num_cell(B["ev"].get("taxi_stability_score"))}</tr>'
        f'<tr><td>Friction</td>{num_cell(A["ev"].get("friction_ratio"), "{:.3f}")}{num_cell(B["ev"].get("friction_ratio"), "{:.3f}")}</tr>'
        f'<tr><td>Live Taxis</td>{num_cell(A["ev"].get("taxi_count"))}{num_cell(B["ev"].get("taxi_count"))}</tr>'
        f'<tr><td>Bus Stops</td>{num_cell(A["ev"].get("stops_in_bbox"))}{num_cell(B["ev"].get("stops_in_bbox"))}</tr>'
        f'<tr><td>Avg Price (4R, 12mo)</td>{num_cell(A["price"], "S${:,.0f}")}{num_cell(B["price"], "S${:,.0f}")}</tr>')
    # Distances are measured from each district's geographic centre — say so,
    # or "nearest MRT 2km" reads as "this district has no MRT".
    if A["ctx"].get("mrt") or B["ctx"].get("mrt"):
        rows += (f'<tr><td>Nearest MRT <span style="color:#8B95A5; font-size:10px;">(from district centre)</span></td>'
                 f'{mrt_cell(A["ctx"])}{mrt_cell(B["ctx"])}</tr>')
    _has_cbd = ((A["ctx"].get("cbd") or {}).get("total_time_min")
                or (B["ctx"].get("cbd") or {}).get("total_time_min"))
    if _has_cbd:
        rows += (f'<tr><td>Commute to CBD <span style="color:#8B95A5; font-size:10px;">(from district centre)</span></td>'
                 f'{cbd_cell(A["ctx"])}{cbd_cell(B["ctx"])}</tr>')

    offline_note = ("" if A["ev"] or B["ev"] else
                    '<div class="sub">Live metrics need the pipeline (python main.py) running — showing what\'s available offline.</div>')
    return (f'<div class="card"><h3>⚖ Compare Districts</h3>'
            f'<div class="sub">Live metrics per district · scores use your current weight settings</div>{offline_note}'
            f'<table class="sg-table"><tr><th>Metric</th><th>{a["label"]}</th><th>{b["label"]}</th></tr>{rows}</table></div>')


@st.cache_data(ttl=600)
def citywide_pattern() -> pd.DataFrame:
    """Weekly availability pattern averaged across every district that has
    enough history — the citywide view for the 24H tab."""
    frames = []
    for o in get_district_options():
        if o["slug"] == "average":
            continue
        try:
            df = DayPatternAnalyser(o["slug"]).get_pattern()
            if df is not None and not df.empty:
                frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    return merged.groupby(["weekday", "hour"], as_index=False)["relative_pct"].mean()


def build_forecast_html(selected: dict, data: dict, extra: dict) -> str:
    selected_label = selected["label"]
    if not EXTENDED_FORECASTER_AVAILABLE:
        return render_coming_soon("ml/extended_forecaster.py could not be imported.")
    if selected["slug"] == "average":
        heatmap_html = render_heatmap(citywide_pattern())
        return f"""
        <div class="card"><h3>📅 Weekly Taxi Availability Heatmap · Singapore Average</h3>
          <div class="sub" style="color:var(--blue-dark); background:var(--blue-pale); padding:8px 10px;
               border-radius:8px; margin-bottom:10px;">💡 Citywide average pattern across all 55
               districts. Pick a specific district above for its hourly 24h forecast, peak-hour
               ratings and model performance.</div>
          {heatmap_html}</div>"""
    heatmap_html = render_heatmap(extra.get("pattern"))
    chart_html = render_24h_line_chart(extra.get("hourly_forecast"))
    peaks_html = render_peak_ratings(extra.get("peaks") or [])
    alerts_html = render_alerts(data.get("alerts_list", []), data.get("alerts"))
    return f"""
        <div class="card"><h3>📅 Weekly Taxi Availability Heatmap · {selected_label}</h3>
          <div class="sub">Real historical average by hour × day of week.</div>{heatmap_html}</div>
        <div class="card"><h3>📈 24-Hour Forecast</h3>
          <div class="sub">Ridge model prediction for the next 24 hours.</div>{chart_html}</div>
        <div class="grid-2">
          <div>
            <div class="card"><h3>🚨 Anomaly Alerts</h3>{alerts_html}{ALERT_LEGEND}</div>
            <div class="card"><h3>⏰ Peak Hour Ratings — Tomorrow</h3>{peaks_html}</div>
          </div>
          <div>
            <div class="card"><h3>📐 Model Performance</h3>{render_model_performance(selected["slug"])}</div>
            <div class="card"><h3>🚕 Taxi Forecast</h3>{render_forecast_trio(data.get("forecast") or {})}</div>
          </div>
        </div>"""


@st.cache_data(ttl=300)
def _town_summary_cached(flat_type: str, months: int) -> pd.DataFrame | None:
    try:
        return get_town_summary(flat_type=flat_type, months=months)
    except Exception:
        return None


@st.cache_data(ttl=300)
def _price_trend_cached(town: str, flat_type: str) -> pd.DataFrame | None:
    try:
        return get_price_trend(town, flat_type)
    except Exception:
        return None


def build_map_and_prices_html(extra: dict, trend_town: str, flat_type: str,
                              months: int, transport_weight: int) -> str:
    if not HDB_AVAILABLE:
        return render_coming_soon("hdb/analytics.py could not be imported — check hdb.duckdb exists in data/.")
    summary = _town_summary_cached(flat_type, months)
    trend_html = render_price_trend_chart(_price_trend_cached(trend_town, flat_type))
    town_table_html = render_price_table(summary, n=len(summary) if summary is not None else 8)
    vfm_html = render_coming_soon("VFM combines live connectivity score with price — needs the live pipeline running.")
    if extra.get("rank") and summary is not None and not summary.empty:
        try:
            conn_scores = {r["district"]: r["score"] for r in extra["rank"]}
            w = transport_weight / 100.0
            vfm_html = render_vfm_table(get_value_for_money(summary, conn_scores,
                                                            transport_weight=w, price_weight=1.0 - w))
        except Exception:
            pass
    return f"""
        <div class="card"><h3>📈 Price Trend · {trend_town.title()} · {flat_type}</h3>{trend_html}</div>
        <div class="grid-2">
          <div class="card"><h3>💰 Price by Town</h3>
            <div class="sub">Average {flat_type} resale price, last {months} months</div>{town_table_html}</div>
          <div class="card"><h3>🏆 Value-for-Money Ranking</h3>
            <div class="sub">Transport {transport_weight}% · Affordability {100 - transport_weight}%</div>{vfm_html}</div>
        </div>"""


def render_block_profile(profile: dict) -> str:
    """Result card for the postal-code Block Transport Profile (parity 3.10)."""
    if not profile or profile.get("error"):
        return render_coming_soon(profile.get("error", "No profile data returned."))
    loc = profile.get("location") or {}
    mrt = profile.get("nearest_mrt")
    cbd = profile.get("cbd_commute")
    stops = profile.get("bus_stops") or []
    lines = ""
    if mrt:
        lines += (f'<div class="stat-line"><span class="l">🚇 NEAREST MRT</span>'
                  f'<span class="v" style="font-size:12px;">{mrt.get("name", "?")} · {mrt.get("distance_label", "")}</span></div>')
    if cbd and cbd.get("total_time_min"):
        lines += (f'<div class="stat-line"><span class="l">🏢 CBD COMMUTE</span>'
                  f'<span class="v" style="font-size:12px;">{cbd["total_time_min"]:.0f} min by public transport</span></div>')
    lines += (f'<div class="stat-line"><span class="l">🚌 BUS STOPS IN RADIUS</span>'
              f'<span class="v" style="font-size:12px;">{profile.get("num_stops", 0)}</span></div>')
    stop_rows = ""
    for s in stops[:5]:
        svc = " ".join(f'<span class="svc-chip">{x.get("service_no", x) if isinstance(x, dict) else x}</span>'
                       for x in (s.get("services") or [])[:4])
        stop_rows += (f'<div class="stat-line"><span class="l">{s.get("description", s.get("stop_code", ""))} '
                      f'· {s.get("distance_m", 0):.0f}m</span>'
                      f'<span class="v" style="font-size:11px;">{svc or "—"}</span></div>')
    addr = loc.get("address", "")
    return (f'<div style="font-size:11.5px; color:#0F172A; font-weight:600; margin-bottom:8px;">📍 {addr}</div>'
            f'{lines}{stop_rows}')


def build_glossary_html() -> str:
    return """
    <div class="card"><h3>📖 What is this app?</h3>
      <p style="font-size:12.5px; line-height:1.7; color:#374151;">This dashboard helps you decide whether a
      Singapore district is worth moving into if it has no MRT station nearby. It scores real-time bus and taxi
      connectivity from 0–100 using LTA DataMall data, and overlays HDB resale prices from data.gov.sg.</p></div>
    <div class="card"><h3>🏆 Connectivity Score (0–100)</h3>
      <table class="sg-table"><tr><th>Score</th><th>Meaning</th></tr>
      <tr><td>75–100</td><td><span class="sg-verdict"><span class="sg-dot g"></span>Well connected</span></td></tr>
      <tr><td>50–74</td><td><span class="sg-verdict"><span class="sg-dot a"></span>Moderate</span></td></tr>
      <tr><td>0–49</td><td><span class="sg-verdict"><span class="sg-dot r"></span>Poor</span></td></tr></table></div>"""


# ───────────────────────────────────────────────────────────────────────────
# Streamlit flow — the ONLY native widget on this page is the selectbox below.
# Picking a district reruns this script top to bottom, fetches new real data,
# and rebuilds the entire HTML block with it.
# ───────────────────────────────────────────────────────────────────────────
# Inject the full mockup CSS at the page level — now that content is plain
# HTML via st.markdown (not one big iframe), this is what actually styles it.
st.markdown(f"""
<style>{CSS_TEXT}
.hero-summary{{ display:flex; align-items:center; gap:20px; background:#fff; border:1px solid var(--border);
  border-radius:14px; padding:16px 20px; margin:16px 0; box-shadow:0 1px 2px rgba(16,24,40,.04); flex-wrap:wrap; }}
.hero-ring{{ width:56px; height:56px; border-radius:50%; border:5px solid var(--amber); flex-shrink:0;
  display:flex; align-items:center; justify-content:center; font-family:'JetBrains Mono',monospace; font-weight:800; font-size:20px; }}
.hero-stats{{ display:flex; gap:22px; margin-left:auto; flex-wrap:wrap; }}
.hero-stats > div{{ display:flex; flex-direction:column; }}
.hero-stat-label{{ font-size:9.5px; color:var(--muted); font-family:'JetBrains Mono',monospace; }}
.hero-stat-val{{ font-family:'JetBrains Mono',monospace; font-weight:800; font-size:17px; }}
.sg-heatmap{{ display:grid; grid-template-columns:36px repeat(24,1fr); gap:3px; font-family:'JetBrains Mono',monospace; margin-top:6px; }}
.sg-heatmap .hlabel{{ font-size:9px; color:var(--muted); display:flex; align-items:center; }}
.sg-heatmap .hcell{{ height:16px; border-radius:2px; }}
.sg-heatmap .hhead{{ font-size:8px; color:var(--muted-2); text-align:center; }}
.sg-peak-box{{ background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:12px; text-align:center; }}
.sg-peak-box .h{{ font-size:9.5px; color:var(--muted); font-family:'JetBrains Mono',monospace; }}
.sg-peak-box .n{{ font-family:'JetBrains Mono',monospace; font-weight:800; font-size:14px; margin:4px 0; }}
.sg-price-tile{{ background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:12px; text-align:center; }}
.sg-price-tile .l{{ font-size:9px; color:var(--muted); font-family:'JetBrains Mono',monospace; }}
.sg-price-tile .v{{ font-family:'JetBrains Mono',monospace; font-weight:800; font-size:15px; margin-top:4px; }}
table.sg-table{{ width:100%; border-collapse:collapse; font-size:12px; }}
table.sg-table th{{ text-align:left; font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--muted); font-weight:600; padding:8px 6px; border-bottom:1px solid var(--border); }}
table.sg-table td{{ padding:9px 6px; border-bottom:1px solid var(--border); font-family:'JetBrains Mono',monospace; font-size:12px; }}
table.sg-table tr.selected td{{ background:var(--blue-pale); }}
.sg-verdict{{ display:flex; align-items:center; gap:6px; font-weight:600; }}
.sg-dot{{ width:7px; height:7px; border-radius:50%; display:inline-block; }}
.sg-dot.g{{ background:var(--teal); }} .sg-dot.a{{ background:var(--amber); }} .sg-dot.r{{ background:var(--red); }}
.sg-bars{{ display:flex; align-items:flex-end; gap:10px; height:130px; margin:14px 0 10px; padding:0 4px; }}
.sg-bar-col{{ flex:1; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; height:100%; }}
.sg-bar-val{{ font-family:'JetBrains Mono',monospace; font-size:10.5px; font-weight:700; margin-bottom:4px; }}
.sg-bar{{ width:100%; border-radius:5px 5px 0 0; min-height:2px; }}
.sg-bar-lbl{{ font-size:9px; color:var(--muted); margin-top:6px; font-family:'JetBrains Mono',monospace; text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:70px; }}
/* Streamlit wraps our markdown in its own containers — make sure margins collapse cleanly */
.element-container {{ margin-bottom: 0 !important; }}
</style>
""", unsafe_allow_html=True)

st.caption("Select a district — the whole dashboard below updates with real data for it.")

# Score weights live in session state so the popover (rendered further down)
# re-scores everything on this run — widget state is applied before rerun.
st.session_state.setdefault("w_bus", DEFAULT_WEIGHTS["bus"])
st.session_state.setdefault("w_stab", DEFAULT_WEIGHTS["stab"])
weights = {"bus": st.session_state["w_bus"], "stab": st.session_state["w_stab"]}
weights_custom = is_custom(weights)

options = get_district_options()

# Rank early: powers scored selector labels + re-weighted leaderboard. First
# uncached call genuinely takes a few seconds (evaluates 55 districts).
if "rank_seen" not in st.session_state:
    with st.spinner("Scoring 55 districts…"):
        rank = call_rank_cached()
    st.session_state["rank_seen"] = True
else:
    rank = call_rank_cached()
pipeline_up = bool(rank)

# Re-weight every district's score from its raw components (no-op with the
# default weights — apply_weights reproduces the server formula).
if rank:
    _rw = []
    for r in rank:
        s = apply_weights(r, weights)
        _rw.append({**r, "score": s if s is not None else r["score"]})
    _rw.sort(key=lambda x: x["score"], reverse=True)
    rank = _rw

rank_by_name = {r["district"].strip().lower(): r for r in (rank or [])}

def _display_label(o: dict) -> str:
    r = rank_by_name.get(o["label"].lower())
    return f'{o["label"]} · {r["score"]:.0f}' if r else o["label"]

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_FULL = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
            "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
_now_sgt = datetime.now(SGT)

# Map clicks land here: the embedded map writes ?district=<slug> into the
# URL (history API — the sandbox blocks real navigation) and clicks the
# hidden sync button below to trigger this rerun. Apply each query-param
# value once, so the dropdown still works normally afterwards.
_qp_slug = st.query_params.get("district")
_default_idx = next((i for i, o in enumerate(options) if o["slug"] == _qp_slug), 0)
if _qp_slug and st.session_state.get("_applied_qp_district") != _qp_slug:
    _qp_idx = next((i for i, o in enumerate(options) if o["slug"] == _qp_slug), None)
    if _qp_idx is not None:
        st.session_state["district_sel"] = _qp_idx
    st.session_state["_applied_qp_district"] = _qp_slug

c_district, c_day, c_hour, c_refresh = st.columns([3.4, 1, 1, 1.2])
with c_district:
    sel_idx = st.selectbox("District", list(range(len(options))), index=_default_idx,
                           key="district_sel",
                           format_func=lambda i: _display_label(options[i]))
# Invisible rerun trigger for the map (see .st-key-map_sync CSS rule).
st.button("sync", key="map_sync")
with c_day:
    sel_day = st.selectbox("Day", DAYS, index=_now_sgt.weekday())
with c_hour:
    sel_hour = st.selectbox("Time", list(range(24)), index=_now_sgt.hour,
                            format_func=lambda h: f"{h:02d}:00")
with c_refresh:
    if st.button("↻ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Last refresh {_now_sgt.strftime('%H:%M')} SGT")

selected = options[sel_idx]

data = get_scope_snapshot(selected["slug"], selected["bbox"])

# Apply the user's weights to the headline score (KPI, ring, verdict).
if data.get("bus"):
    _eff = apply_weights(data["bus"], weights)
    if _eff is not None:
        data["conn_score"] = round(_eff)
elif selected["slug"] == "average" and rank:
    data["conn_score"] = round(sum(r["score"] for r in rank) / len(rank))
if data["conn_score"] is not None:
    data["verdict"] = verdict_for(data["conn_score"])[0]

extra = {"rank": rank, "sel_day": sel_day, "sel_hour": sel_hour}

if HDB_AVAILABLE:
    try:
        extra["town_summary"] = get_town_summary(flat_type="4 ROOM", months=12)
    except Exception:
        extra["town_summary"] = None
    try:
        towns = get_available_towns()
        trend_town = towns[0] if towns else None
        extra["trend_town"] = trend_town
        extra["price_trend"] = get_price_trend(trend_town, "4 ROOM") if trend_town else None
    except Exception:
        extra["price_trend"] = None
        extra["trend_town"] = ""
    if extra.get("rank") and extra.get("town_summary") is not None:
        try:
            conn_scores = {r["district"]: r["score"] for r in extra["rank"]}
            extra["vfm"] = get_value_for_money(extra["town_summary"], conn_scores)
        except Exception:
            extra["vfm"] = None
    else:
        extra["vfm"] = None

if EXTENDED_FORECASTER_AVAILABLE and selected["slug"] != "average":
    try:
        extra["pattern"] = DayPatternAnalyser(selected["slug"]).get_pattern()
    except Exception:
        extra["pattern"] = pd.DataFrame()
    try:
        extra["hourly_forecast"] = HourlyForecaster(selected["slug"]).predict_24h()
    except Exception:
        extra["hourly_forecast"] = pd.DataFrame()
    try:
        extra["peaks"] = PeakHourPredictor(selected["slug"]).predict_peaks()
    except Exception:
        extra["peaks"] = []

# Expected taxi count at the chosen day/hour from the historical pattern.
expected_taxis = None
_patt = extra.get("pattern")
if _patt is not None and not _patt.empty:
    try:
        _m = _patt[(_patt["day_name"] == DAY_FULL[sel_day]) & (_patt["hour"] == sel_hour)]
        if not _m.empty:
            expected_taxis = float(_m["avg_count"].iloc[0])
    except Exception:
        expected_taxis = None

topnav_html, floatcard_html, kpis_html, baseline = build_chrome_and_kpis(
    selected, data, sel_day=sel_day, sel_hour=sel_hour, expected_taxis=expected_taxis,
    custom_weights=weights_custom)
st.markdown(topnav_html, unsafe_allow_html=True)

if not pipeline_up:
    st.markdown(
        '<div style="background:#FEF3DE; border:1px solid #F5A524; border-radius:10px; '
        "padding:10px 14px; margin:6px 0 10px; font-family:'JetBrains Mono',monospace; "
        'font-size:11.5px; color:#B4790F;">🔌 Live pipeline offline — showing stored data '
        'only. Run <b>python main.py</b> for live scores and the district leaderboard.</div>',
        unsafe_allow_html=True)

# Top-of-page live map strip + floating connectivity card (mockup layout).
# load_map_html inlines the local planning-area polygons so district borders
# render even when the FastAPI pipeline is offline.
from dashboard.map_embed import load_map_html
MAP_HTML = load_map_html(Path(__file__).parent / "sg_map.html",
                         Path(__file__).parent / "planning_areas.geojson")
map_col, card_col = st.columns([2.9, 1.1], gap="small")
with map_col:
    if MAP_HTML:
        components.html(MAP_HTML, height=330, scrolling=False)
    else:
        st.markdown(render_coming_soon("dashboard/sg_map.html not found next to app_v3.py."),
                    unsafe_allow_html=True)
with card_col:
    st.markdown(floatcard_html, unsafe_allow_html=True)

st.markdown(kpis_html, unsafe_allow_html=True)

# Score Weights: right-aligned popover on its own row above the tab bar —
# the closest Streamlit layout to the mockup's tabbar button. Adjusting the
# sliders reruns the script, which re-scores the whole page (see `weights`).
_wchip_col, _pop_col = st.columns([5, 1.3])
with _wchip_col:
    if weights_custom:
        st.markdown('<span class="chip mid" title="Scores on this page use your custom weights, '
                    'not the default 50/30/20 formula">⚖ CUSTOM WEIGHTS ACTIVE</span>',
                    unsafe_allow_html=True)
def _set_weights(bus: int, stab: int) -> None:
    # on_click callbacks run before widgets instantiate on the next run, so
    # writing widget-keyed session state here is legal.
    st.session_state["w_bus"] = bus
    st.session_state["w_stab"] = stab

with _pop_col:
    with st.popover("⚖ Score Weights", use_container_width=True):
        _p1, _p2, _p3 = st.columns(3)
        _p1.button("Bus-reliant", use_container_width=True, help="Bus 75% · Taxi 25%",
                   on_click=_set_weights, args=(75, DEFAULT_WEIGHTS["stab"]))
        _p2.button("Balanced", use_container_width=True, help="Bus 50% · Taxi 50% (default)",
                   on_click=_set_weights, args=(DEFAULT_WEIGHTS["bus"], DEFAULT_WEIGHTS["stab"]))
        _p3.button("Taxi-reliant", use_container_width=True, help="Bus 25% · Taxi 75%",
                   on_click=_set_weights, args=(25, DEFAULT_WEIGHTS["stab"]))
        st.slider("🚌 Bus share %", 0, 100, key="w_bus")
        st.caption(f"🚕 Taxi auto-balances: {100 - st.session_state['w_bus']}%")
        st.slider("Taxi stability share %", 0, 100, key="w_stab",
                  help="Within the taxi term: reward for stable supply vs friction penalty")
        st.caption(f"Friction auto-balances: {100 - st.session_state['w_stab']}%")
        # Same components the headline score uses, so the formula card and the
        # KPI/ring always agree: live /evaluate for a district, mean of all 55
        # districts' components for Singapore Average.
        if data.get("bus"):
            _formula_comps = data["bus"]
            _formula_basis = "this district's live evaluation"
        elif rank and any(r.get("bus_frequency_score") for r in rank):
            _formula_comps = {
                "bus_frequency_score": sum(r.get("bus_frequency_score", 0.0) for r in rank) / len(rank),
                "taxi_stability_score": sum(r.get("taxi_stability_score", 0.0) for r in rank) / len(rank),
                "friction_ratio": sum(r.get("friction_ratio", 0.0) for r in rank) / len(rank),
            }
            _formula_basis = "citywide mean of all 55 live evaluations"
        else:
            _formula_comps = {"bus_frequency_score": 73.0, "taxi_stability_score": 87.0,
                              "friction_ratio": 0.68}
            _formula_basis = "illustrative defaults (live pipeline offline)"
        st.markdown(render_formula_card(_formula_comps, weights, _formula_basis),
                    unsafe_allow_html=True)
        if weights_custom:
            st.button("↺ Reset to default weights", use_container_width=True,
                      on_click=_set_weights,
                      args=(DEFAULT_WEIGHTS["bus"], DEFAULT_WEIGHTS["stab"]))
        st.divider()
        if selected["slug"] != "average" and FORECASTER_AVAILABLE:
            if st.button("🔁 Retrain forecast model", use_container_width=True,
                         help="Retrains this district's Ridge model on the last 24h of snapshots"):
                with st.spinner("Training…"):
                    try:
                        _res = TaxiForecaster(selected["slug"]).train(lookback_min=1440)
                    except Exception as e:
                        _res = f"failed: {e}"
                st.caption(f"Done: {_res or 'insufficient data'}")

tab_overview, tab_forecast, tab_compare, tab_map, tab_glossary = st.tabs(
    ["Overview", "24H Forecast", "Compare", "🗺 Map & Housing Prices", "Glossary"]
)

with tab_overview:
    # Window picker for the history chart — the control lives right where it
    # applies, instead of a detached slider in the top bar.
    _win_col, _ = st.columns([1, 5])
    with _win_col:
        _win_label = st.selectbox("Chart window", ["3h", "6h", "12h", "24h", "48h"], index=2,
                                  help="How far back the taxi availability chart looks")
    _win_minutes = {"3h": 180, "6h": 360, "12h": 720, "24h": 1440, "48h": 2880}[_win_label]
    st.markdown(build_history_card(selected, _win_minutes), unsafe_allow_html=True)
    st.markdown(build_overview_html(selected, data, extra), unsafe_allow_html=True)

with tab_forecast:
    st.markdown(build_forecast_html(selected, data, extra), unsafe_allow_html=True)

with tab_compare:
    _non_avg = [o for o in options if o["slug"] != "average"]
    _names = [o["label"] for o in _non_avg]

    def _cmp_default(name: str, fallback: int = 0) -> int:
        return _names.index(name) if name in _names else fallback

    _ca, _cb = st.columns(2)
    with _ca:
        _a_label = st.selectbox("District A", _names, index=_cmp_default("Ang Mo Kio"), key="cmp_a")
    with _cb:
        _b_label = st.selectbox("District B", _names, index=_cmp_default("Bishan", 1), key="cmp_b")
    _a = next(o for o in _non_avg if o["label"] == _a_label)
    _b = next(o for o in _non_avg if o["label"] == _b_label)
    try:
        st.markdown(build_compare_html(_a, _b, weights), unsafe_allow_html=True)
    except Exception:
        st.markdown(f'<div class="card">{render_coming_soon("Comparison failed — check the pipeline and try again.")}</div>',
                    unsafe_allow_html=True)

with tab_map:
    st.markdown('<div class="card"><h3>🗺 Live Interactive Map</h3>'
                '<div class="sub">Full-size view of the live map — real planning-area polygons, '
                'click anywhere for a live connectivity score, or search a postal code. '
                'Dark-themed on purpose (its own design).</div></div>', unsafe_allow_html=True)
    if MAP_HTML:
        components.html(MAP_HTML, height=560, scrolling=False)
    else:
        st.markdown(render_coming_soon("dashboard/sg_map.html not found next to app_v3.py."), unsafe_allow_html=True)

    if HDB_AVAILABLE:
        try:
            _flat_types = get_flat_types()
        except Exception:
            _flat_types = ["4 ROOM"]
        try:
            _towns = get_available_towns()
        except Exception:
            _towns = []
        _mc1, _mc2, _mc3, _mc4 = st.columns([1.2, 1.6, 1.4, 1.6])
        with _mc1:
            _flat = st.selectbox("Flat type", _flat_types,
                                 index=_flat_types.index("4 ROOM") if "4 ROOM" in _flat_types else 0)
        with _mc2:
            _months = st.slider("Months of data", 1, 24, 12)
        with _mc3:
            _tw = st.slider("Transport importance %", 0, 100, 50,
                            help="Weight of transport connectivity vs affordability in the VFM ranking")
        with _mc4:
            _trend_town = st.selectbox("Town for price trend", _towns or ["—"])
        st.markdown(build_map_and_prices_html(extra, _trend_town, _flat, _months, _tw),
                    unsafe_allow_html=True)
    else:
        st.markdown(render_coming_soon("hdb/analytics.py could not be imported — check hdb.duckdb exists in data/."),
                    unsafe_allow_html=True)

    # Block Transport Profile (postal code + radius → live OneMap/LTA lookup)
    st.markdown('<div class="card" style="margin-bottom:0;"><h3>📍 Block Transport Profile</h3>'
                '<div class="sub">Enter a Singapore postal code to see real-time transport + nearby context</div></div>',
                unsafe_allow_html=True)
    _bp1, _bp2, _bp3 = st.columns([2, 2.5, 1])
    with _bp1:
        _postal = st.text_input("Postal code", placeholder="e.g. 440010", max_chars=6)
    with _bp2:
        _radius = st.slider("Search radius (m)", 100, 1000, 500, step=100)
    with _bp3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        _fetch = st.button("🔍 Fetch", use_container_width=True)
    if _fetch and _postal.strip():
        try:
            from hdb.onemap_services import get_area_transport_profile
            from config import cfg as _cfg
            with st.spinner("Looking up transport profile…"):
                _profile = get_area_transport_profile(_postal.strip(), radius_m=_radius,
                                                      lta_api_key=_cfg.lta_api_key)
            st.markdown(f'<div class="card">{render_block_profile(_profile)}</div>',
                        unsafe_allow_html=True)
        except Exception as e:
            st.markdown(f'<div class="card">{render_coming_soon(f"OneMap lookup failed ({e}) — check ONEMAP_TOKEN.")}</div>',
                        unsafe_allow_html=True)

with tab_glossary:
    st.markdown(build_glossary_html(), unsafe_allow_html=True)
