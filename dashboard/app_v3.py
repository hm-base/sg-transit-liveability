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

from config import cfg
from storage.database import init_db, fetch_snapshots, fetch_alerts, fetch_latest_metrics
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
div[data-baseweb="select"] span { color: #0F172A !important; }
label { color: #6B7686 !important; font-family: 'JetBrains Mono', monospace !important; font-size: 11px !important; }
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
        alerts = fetch_alerts(None, limit=200)
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
            alerts=len(alerts), alerts_list=alerts[:6], conn_score=conn_score, verdict=verdict,
            price=get_avg_price(None), live=bool(rank), bus=None, forecast={},
            bus_stops="\u2014", bus_headway="\u2014",
        )

    snaps = fetch_snapshots(slug, minutes=60)
    alerts = fetch_alerts(slug, limit=50)
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
        alerts=len(alerts), alerts_list=alerts[:6], conn_score=conn_score, verdict=verdict,
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
    return "g" if score >= 80 else ("a" if score >= 65 else "r")


def _verdict_label(score):
    return "Well connected" if score >= 80 else ("Moderate" if score >= 65 else "Poor")


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
        color = "#EA8C1D" if is_sel else ("#10B981" if r["score"] >= 80 else ("#F5A524" if r["score"] >= 65 else "#EF4444"))
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


def render_24h_line_chart(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return render_coming_soon("Model needs at least 50 recent snapshots to predict.")
    vals = df["predicted_count"].tolist()
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = 30 + (i / (n - 1)) * 840 if n > 1 else 30
        y = 160 - ((v - lo) / span) * 140
        pts.append(f"{x:.0f},{y:.0f}")
    polyline = " ".join(pts)
    return f"""<svg width="100%" height="180" viewBox="0 0 900 180" preserveAspectRatio="none">
      <polyline fill="none" stroke="#F5A524" stroke-width="2.5" points="{polyline}"/>
      <line x1="30" y1="160" x2="870" y2="160" stroke="#E4E9F0"/></svg>
      <div style="display:flex; justify-content:space-between; font-size:9.5px; color:var(--muted);
                  font-family:'JetBrains Mono',monospace; padding:0 30px;">
        <span>+1hr</span><span>+6hr</span><span>+12hr</span><span>+18hr</span><span>+24hr</span></div>"""


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


def render_alerts(alerts: list) -> str:
    if not alerts:
        return '<div class="chip ok" style="display:block; text-align:center; padding:10px;">\u2705 No alerts \u2014 all clear</div>'
    return "".join(f'<div class="chip warn" style="display:block; margin-bottom:6px;">\u26A0\uFE0F {a["alert_type"]} \u00b7 {a["message"]}</div>' for a in alerts)


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


JS_BLOCK = r"""
function setPreset(bus, stab, el){
  document.getElementById('busSlider').value=bus;
  document.getElementById('stabSlider').value=stab;
  document.querySelectorAll('.preset').forEach(p=>p.classList.remove('active'));
  if(el) el.classList.add('active');
  recalc();
}
function recalc(){
  const bus = +document.getElementById('busSlider').value;
  const taxi = 100 - bus;
  const stabShare = +document.getElementById('stabSlider').value;
  const fricShare = 100 - stabShare;
  document.getElementById('busPct').innerText = bus + '%';
  document.getElementById('taxiPctTop').innerText = taxi + '%';
  document.getElementById('stabPct').innerText = stabShare + '%';
  document.getElementById('fricPctSub').innerText = fricShare + '%';
  const busTerm = Math.round(bus * BASELINE.bus);
  const stabTerm = Math.round(taxi * (stabShare/100) * BASELINE.stability);
  const fricTerm = Math.round(taxi * (fricShare/100) * BASELINE.friction);
  document.getElementById('busTerm').innerText = busTerm;
  document.getElementById('taxiTerm').innerText = stabTerm;
  document.getElementById('fricTerm').innerText = fricTerm;
  document.getElementById('scoreOut').innerText = Math.max(0, Math.min(100, busTerm + stabTerm - fricTerm));
}
recalc();
"""


def build_score_weights_widget(baseline: dict, live: bool) -> str:
    """Self-contained interactive calculator — the ONE piece that genuinely
    needs real JavaScript, so it's the only remaining components.html() call
    besides the real map. No modal/overlay chrome (that doesn't play well
    inside a fixed-height iframe) — just an always-visible card."""
    baseline_json = json.dumps(baseline)
    basis_note = "this district's live evaluation" if live else "illustrative defaults (live pipeline offline)"
    return f"""
<!DOCTYPE html><html><head><style>{CSS_TEXT}
body{{ margin:0; background:transparent; }}
.modal{{ box-shadow:none; padding:4px; width:auto; max-width:none; }}
</style></head><body>
<div class="modal">
  <div style="font-size:10px; font-family:'JetBrains Mono',monospace; color:var(--muted); margin-bottom:10px;">
    LIVE FORMULA · baseline from {basis_note}</div>
  <div class="formula" style="flex-wrap:wrap;">
    <div class="big-ring" id="scoreOut">0</div><span>=</span>
    <div class="term blue"><div class="n" id="busTerm">0</div><div class="l">Bus</div></div><span>+</span>
    <span style="font-size:16px; color:var(--muted-2);">(</span>
    <div class="term teal"><div class="n" id="taxiTerm">0</div><div class="l">Stability</div></div><span>−</span>
    <div class="term red"><div class="n" id="fricTerm">0</div><div class="l">Friction</div></div>
    <span style="font-size:16px; color:var(--muted-2);">)</span>
  </div>
  <div style="font-size:10.5px; text-align:center; color:var(--muted); font-family:'JetBrains Mono',monospace; margin:-8px 0 16px;">
    Score = Bus + Taxi · Taxi = Stability − Friction</div>
  <div class="presets">
    <div class="preset" onclick="setPreset(75,100,this)"><b>Bus-reliant</b>Bus 75% · Taxi 25%</div>
    <div class="preset active" onclick="setPreset(50,70,this)"><b>Balanced</b>Bus 50% · Taxi 50%</div>
    <div class="preset" onclick="setPreset(25,60,this)"><b>Taxi-reliant</b>Bus 25% · Taxi 75%</div>
  </div>
  <div class="slider-row"><div class="sl-head"><span>🚌 Bus</span><span id="busPct">50%</span></div>
    <input type="range" id="busSlider" min="0" max="100" value="50" oninput="recalc()">
    <div class="sl-head" style="margin-top:2px;"><span style="color:var(--muted-2); font-weight:500;">🚕 Taxi (auto-balances)</span><span id="taxiPctTop" style="color:var(--muted-2); font-weight:500;">50%</span></div></div>
  <div class="slider-row"><div class="sl-head"><span>Taxi Stability (reward)</span><span id="stabPct">70%</span></div>
    <input type="range" id="stabSlider" min="0" max="100" value="70" oninput="recalc()">
    <div class="sl-head" style="margin-top:2px;"><span style="color:var(--muted-2); font-weight:500;">Friction (auto-balances)</span><span id="fricPctSub" style="color:var(--muted-2); font-weight:500;">30%</span></div></div>
</div>
<script>
const BASELINE = {baseline_json};
{JS_BLOCK}
</script>
</body></html>"""



# ─────────────────────────────────────────────────────────────────────────────
# Chrome + per-tab HTML fragments — all plain HTML rendered via st.markdown,
# no iframe needed for any of it (nothing here requires real JavaScript).
# ─────────────────────────────────────────────────────────────────────────────
def build_chrome_and_kpis(selected: dict, data: dict, sel_day: str = "",
                          sel_hour: int | None = None,
                          expected_taxis: float | None = None) -> tuple[str, str, str, dict]:
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
  <div class="map-hint">💡 Click anywhere on the map for a live connectivity score — or search a postal code.</div>

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
        </div>"""
    else:
        timeliness_html = render_coming_soon("Bus + live connectivity detail needs the live pipeline "
                                             "(python main.py) running. Taxi numbers above are still real.")

    leaderboard_html = render_leaderboard(extra.get("rank") or [], highlight_district=None if selected["slug"]=="average" else selected_label)
    price_table_html = render_price_table(extra.get("town_summary"), n=8) if HDB_AVAILABLE else render_coming_soon("hdb.duckdb not found.")
    alerts_html = render_alerts(data.get("alerts_list", []))

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
          {render_coming_soon("Nearest MRT, bus coverage, and commute time — needs the OneMap lookup wired in next.")}</div>
        <div class="card"><h3>💰 Price Snapshot</h3>
          <div class="sub">Resale prices · {selected_label}</div>{price_table_html}</div>
        <div class="card"><h3>🚨 Anomaly Alerts</h3>{alerts_html}</div>
      </div>
    </div>"""


def build_forecast_html(selected: dict, extra: dict) -> str:
    selected_label = selected["label"]
    if selected["slug"] == "average":
        return render_coming_soon("Pick a specific district above — hourly forecasts and the "
                                  "weekly pattern are per-district, a citywide average wouldn't mean much here.")
    if not EXTENDED_FORECASTER_AVAILABLE:
        return render_coming_soon("ml/extended_forecaster.py could not be imported.")
    heatmap_html = render_heatmap(extra.get("pattern"))
    chart_html = render_24h_line_chart(extra.get("hourly_forecast"))
    peaks_html = render_peak_ratings(extra.get("peaks") or [])
    return f"""
        <div class="card"><h3>📅 Weekly Taxi Availability Heatmap · {selected_label}</h3>
          <div class="sub">Real historical average by hour × day of week.</div>{heatmap_html}</div>
        <div class="card"><h3>📈 24-Hour Forecast</h3>
          <div class="sub">Ridge model prediction for the next 24 hours.</div>{chart_html}</div>
        <div class="card"><h3>⏰ Peak Hour Ratings — Tomorrow</h3>{peaks_html}</div>"""


def build_map_and_prices_html(extra: dict) -> str:
    if not HDB_AVAILABLE:
        return render_coming_soon("hdb/analytics.py could not be imported — check hdb.duckdb exists in data/.")
    trend_html = render_price_trend_chart(extra.get("price_trend"))
    town_table_html = render_price_table(extra.get("town_summary"), n=len(extra.get("town_summary", [])) or 8)
    vfm_html = render_vfm_table(extra.get("vfm")) if extra.get("vfm") is not None else render_coming_soon(
        "VFM combines live connectivity score with price — needs the live pipeline running.")
    return f"""
        <div class="card"><h3>📈 Price Trend · {extra.get('trend_town','')}</h3>{trend_html}</div>
        <div class="grid-2">
          <div class="card"><h3>💰 Price by Town</h3>{town_table_html}</div>
          <div class="card"><h3>🏆 Value-for-Money Ranking</h3>{vfm_html}</div>
        </div>"""


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
rank_by_name = {r["district"].strip().lower(): r for r in (rank or [])}

def _display_label(o: dict) -> str:
    r = rank_by_name.get(o["label"].lower())
    return f'{o["label"]} · {r["score"]:.0f}' if r else o["label"]

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_FULL = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
            "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
_now_sgt = datetime.now(SGT)

c_district, c_day, c_hour, c_hist, c_refresh = st.columns([3, 1, 1, 1.9, 1.1])
with c_district:
    sel_idx = st.selectbox("District", list(range(len(options))), index=0,
                           format_func=lambda i: _display_label(options[i]))
with c_day:
    sel_day = st.selectbox("Day", DAYS, index=_now_sgt.weekday())
with c_hour:
    sel_hour = st.selectbox("Time", list(range(24)), index=_now_sgt.hour,
                            format_func=lambda h: f"{h:02d}:00")
with c_hist:
    history_min = st.slider("History (minutes)", 30, 360, 60, step=15)
with c_refresh:
    if st.button("↻ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Last refresh {_now_sgt.strftime('%H:%M')} SGT")

selected = options[sel_idx]

data = get_scope_snapshot(selected["slug"], selected["bbox"])

extra = {"rank": rank, "history_min": history_min,
         "sel_day": sel_day, "sel_hour": sel_hour}

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
    selected, data, sel_day=sel_day, sel_hour=sel_hour, expected_taxis=expected_taxis)
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

with st.expander("⚖ Score Weights — live formula calculator"):
    components.html(build_score_weights_widget(baseline, data["live"]), height=430, scrolling=False)

tab_overview, tab_forecast, tab_compare, tab_map, tab_glossary = st.tabs(
    ["Overview", "24H Forecast", "Compare", "🗺 Map & Housing Prices", "Glossary"]
)

with tab_overview:
    st.markdown(build_overview_html(selected, data, extra), unsafe_allow_html=True)

with tab_forecast:
    st.markdown(build_forecast_html(selected, extra), unsafe_allow_html=True)

with tab_compare:
    st.markdown(f'<div class="card">{render_coming_soon("Side-by-side district comparison, coming after this tab is fully wired.")}</div>',
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
    st.markdown(build_map_and_prices_html(extra), unsafe_allow_html=True)

with tab_glossary:
    st.markdown(build_glossary_html(), unsafe_allow_html=True)
