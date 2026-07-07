"""
dashboard/render.py
====================
Pure HTML-building functions for the SG Liveability dashboard.

No Streamlit. No FastAPI decorators. Just plain Python functions that take
already-fetched real data and return an HTML string. api.py's /dashboard
route calls get_scope_data() then build_full_page() and returns the result
directly as an HTMLResponse — the browser gets a genuine, ordinary webpage.

Because this is a real page (not text stuffed through st.markdown or an
iframe sandbox), <script> tags actually execute normally: tabs, the score
weights calculator, and the embedded map all just work the way they did in
the original approved mockup.

These functions have zero framework dependency, so they can be unit tested
directly (see the bottom of this file / accompanying tests) by calling them
with plain dicts and DataFrames — no live server needed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

SGT = timezone(timedelta(hours=8))


# ─────────────────────────────────────────────────────────────────────────────
# CSS — identical to the approved mockup, verbatim.
# ─────────────────────────────────────────────────────────────────────────────
CSS_TEXT = r"""
:root{
  --bg:#F3F6FA; --card:#FFFFFF; --border:#E4E9F0; --border-strong:#D3DBE5;
  --text:#0F172A; --muted:#6B7686; --muted-2:#8B95A5;
  --blue:#2F7DED; --blue-dark:#1A5FC4; --blue-pale:#EAF2FE;
  --teal:#10B981; --teal-pale:#E6F9F1;
  --amber:#F5A524; --amber-pale:#FEF3DE;
  --red:#EF4444; --red-pale:#FDEAEA;
  --shadow: 0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.04);
  --radius: 14px;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);
  font-family:'Inter',system-ui,sans-serif;}
h1,h2,h3,h4{font-family:'JetBrains Mono',monospace; margin:0;}
a{color:inherit;text-decoration:none;}
button{font-family:inherit;cursor:pointer;}

header.topnav{
  background:#fff; border-bottom:1px solid var(--border);
  padding:12px 24px; position:sticky; top:0; z-index:40;
}
.topnav-inner{
  display:flex; align-items:center; gap:16px; max-width:1500px; margin:0 auto;
}
.brand{display:flex; align-items:center; gap:10px; font-family:'JetBrains Mono',monospace; font-weight:700; font-size:15px;}
.brand .mark{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,#3EA6FF,#2F7DED);
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:14px;}
.nav-right{display:flex; align-items:center; gap:10px; margin-left:auto;}
select.district-select{
  background:var(--bg); border:1px solid var(--border); border-radius:10px;
  padding:9px 14px; font-family:'JetBrains Mono',monospace; font-size:12.5px; font-weight:600;
  color:var(--text); cursor:pointer;
}

main{padding:22px 24px 60px; max-width:1500px; margin:0 auto;}

.hero-map-row{ display:flex; gap:16px; align-items:stretch; margin:16px 0; flex-wrap:wrap; }
.hero-map{ flex:2; min-width:320px; min-height:340px; }
.hero-summary-side{ flex:1; min-width:220px; flex-direction:column; align-items:flex-start; margin:0; justify-content:center; }
.hero-stats-stacked{ flex-direction:column; gap:10px; margin-left:0; margin-top:10px; width:100%; }
.hero-stats-stacked > div{ flex-direction:row; justify-content:space-between; width:100%; }
.hero-summary{ display:flex; align-items:center; gap:20px; background:#fff; border:1px solid var(--border);
  border-radius:var(--radius); padding:16px 20px; margin:16px 0; box-shadow:var(--shadow); flex-wrap:wrap; }
.hero-ring{ width:56px; height:56px; border-radius:50%; border:5px solid var(--amber); flex-shrink:0;
  display:flex; align-items:center; justify-content:center; font-family:'JetBrains Mono',monospace; font-weight:800; font-size:20px; }
.hero-stats{ display:flex; gap:22px; margin-left:auto; flex-wrap:wrap; }
.hero-stats > div{ display:flex; flex-direction:column; }
.hero-stat-label{ font-size:9.5px; color:var(--muted); font-family:'JetBrains Mono',monospace; }
.hero-stat-val{ font-family:'JetBrains Mono',monospace; font-weight:800; font-size:17px; }
.fc-verdict{font-family:'JetBrains Mono',monospace; font-weight:700; font-size:13px;}
.fc-verdict-sub{font-size:11px; color:var(--muted); margin-bottom:2px;}
.fc-verdict-desc{font-size:10.5px; color:var(--muted); line-height:1.4; margin-top:4px; max-width:220px;}
.local-snapshot-list .local-row{padding:10px 0; border-bottom:1px solid var(--border);}
.local-snapshot-list .local-row:last-child{border-bottom:none;}
.local-title{font-weight:700; font-size:12.5px;}
.local-sub{font-size:11px; color:var(--muted); margin-top:2px;}
.fc-head{font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--muted); letter-spacing:.4px; margin-bottom:8px;}
.hero-missing-note{font-size:10px; color:var(--muted-2); font-family:'JetBrains Mono',monospace; margin-top:10px; line-height:1.5;}
.deep-dive-btn{width:100%; background:var(--text); color:#fff; border:none; padding:10px; border-radius:9px;
  font-family:'JetBrains Mono',monospace; font-size:11.5px; font-weight:700; margin-top:12px; cursor:pointer;}

.scope-badge{display:inline-flex; align-items:center; gap:7px; background:var(--blue-pale); color:var(--blue-dark);
  border:1px solid #C7DEFB; border-radius:9px; padding:6px 12px; font-family:'JetBrains Mono',monospace;
  font-size:11.5px; font-weight:700; margin-bottom:12px;}

.kpi-row{display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-bottom:20px;}
.kpi{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; box-shadow:var(--shadow);}
.kpi.highlight{border-color:var(--border-strong);}
.kpi-label{font-size:10px; font-family:'JetBrains Mono',monospace; color:var(--muted); letter-spacing:.4px; margin-bottom:8px;}
.kpi-val{font-family:'JetBrains Mono',monospace; font-size:26px; font-weight:800;}
.kpi-sub{font-size:10.5px; color:var(--muted); margin-top:4px; font-family:'JetBrains Mono',monospace;}
.badge-mod{font-size:10px; background:var(--amber); color:#fff; padding:2px 7px; border-radius:6px; font-weight:700;}

.tabbar{display:flex; align-items:center; border-bottom:1px solid var(--border); margin-bottom:20px; flex-wrap:wrap;}
.tab{padding:10px 4px; margin-right:26px; font-family:'JetBrains Mono',monospace; font-size:12.5px; font-weight:600;
  color:var(--muted); border-bottom:2px solid transparent; background:none; border:none;}
.tab.active{color:var(--blue); border-bottom-color:var(--blue);}
.tab-right{margin-left:auto;}

.grid-2{display:grid; grid-template-columns:2fr 1fr; gap:16px;}
.card{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:18px; box-shadow:var(--shadow); margin-bottom:16px;}
.card h3{font-size:14.5px; display:flex; align-items:center; gap:8px; margin-bottom:4px;}
.card .sub{font-size:11.5px; color:var(--muted); margin:4px 0 14px;}

.mini-grid{display:grid; grid-template-columns:1.15fr 0.85fr 1.15fr 1fr; gap:0; border:1px solid var(--border); border-radius:10px; overflow:hidden;}
.mini-col{padding:14px; border-right:1px solid var(--border);}
.mini-col:last-child{border-right:none;}
.mini-col-title{font-size:10px; font-family:'JetBrains Mono',monospace; color:var(--muted); margin-bottom:10px;}
.stat-line{display:flex; justify-content:space-between; align-items:baseline; padding:6px 0;}
.stat-line .l{font-size:10px; color:var(--muted); font-family:'JetBrains Mono',monospace;}
.stat-line .v{font-family:'JetBrains Mono',monospace; font-weight:700; font-size:16px;}
.conn-center{display:flex; flex-direction:column; align-items:center; justify-content:center; padding:14px;}
.conn-center .ring{width:64px;height:64px; border-width:5px; border-style:solid; border-radius:50%; display:flex; align-items:center; justify-content:center;
  font-family:'JetBrains Mono',monospace; font-weight:800; font-size:22px;}

.chip{font-family:'JetBrains Mono',monospace; font-size:10.5px; padding:5px 9px; border-radius:7px; font-weight:600; display:inline-block;}
.chip.ok{background:var(--teal-pale); color:#0C8457;}
.chip.warn{background:var(--amber-pale); color:#B4790F;}

table.sg-table{width:100%; border-collapse:collapse; font-size:12px;}
table.sg-table th{text-align:left; font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--muted); font-weight:600; padding:8px 6px; border-bottom:1px solid var(--border);}
table.sg-table td{padding:9px 6px; border-bottom:1px solid var(--border); font-family:'JetBrains Mono',monospace; font-size:12px;}
table.sg-table tr.selected td{background:var(--blue-pale);}
.sg-verdict{display:flex; align-items:center; gap:6px; font-weight:600;}
.sg-dot{width:7px;height:7px;border-radius:50%;display:inline-block;}
.sg-dot.g{background:var(--teal);} .sg-dot.a{background:var(--amber);} .sg-dot.r{background:var(--red);}

.sg-bars{display:flex; align-items:flex-end; gap:10px; height:130px; margin:14px 0 10px; padding:0 4px;}
.sg-bar-col{flex:1; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; height:100%;}
.sg-bar-val{font-family:'JetBrains Mono',monospace; font-size:10.5px; font-weight:700; margin-bottom:4px;}
.sg-bar{width:100%; border-radius:5px 5px 0 0; min-height:2px;}
.sg-bar-lbl{font-size:9px; color:var(--muted); margin-top:6px; font-family:'JetBrains Mono',monospace; text-align:center;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:70px;}

.price-tiles{display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-top:10px;}
.sg-price-tile{background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:12px; text-align:center;}
.sg-price-tile .l{font-size:9px; color:var(--muted); font-family:'JetBrains Mono',monospace;}
.sg-price-tile .v{font-family:'JetBrains Mono',monospace; font-weight:800; font-size:15px; margin-top:4px;}

.sg-heatmap{display:grid; grid-template-columns:36px repeat(24,1fr); gap:3px; font-family:'JetBrains Mono',monospace; margin-top:6px;}
.sg-heatmap .hlabel{font-size:9px; color:var(--muted); display:flex; align-items:center;}
.sg-heatmap .hcell{height:16px; border-radius:2px;}
.sg-heatmap .hhead{font-size:8px; color:var(--muted-2); text-align:center;}
.sg-peak-box{background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:12px; text-align:center;}
.sg-peak-box .h{font-size:9.5px; color:var(--muted); font-family:'JetBrains Mono',monospace;}
.sg-peak-box .n{font-family:'JetBrains Mono',monospace; font-weight:800; font-size:14px; margin:4px 0;}

.map-embed{width:100%; height:560px; border:none; border-radius:var(--radius);}

.modal{background:#fff; border-radius:16px; max-width:560px; padding:26px; box-shadow:var(--shadow); border:1px solid var(--border);}
.formula{display:flex; align-items:center; justify-content:center; gap:12px; margin-bottom:14px; font-family:'JetBrains Mono',monospace; flex-wrap:wrap;}
.formula .big-ring{width:64px;height:64px;border-radius:50%;border:5px solid var(--amber); display:flex;align-items:center;justify-content:center; font-weight:800; font-size:22px; color:var(--amber);}
.formula .term{text-align:center;}
.formula .term .n{font-size:20px; font-weight:800;}
.formula .term.blue .n{color:var(--blue);} .formula .term.teal .n{color:var(--teal);} .formula .term.red .n{color:var(--red);}
.formula .term .l{font-size:9px; color:var(--muted);}
.presets{display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-bottom:16px;}
.preset{border:1px solid var(--border-strong); border-radius:10px; padding:10px; font-size:11px; font-family:'JetBrains Mono',monospace; background:#fff; cursor:pointer;}
.preset.active{border-color:var(--blue); background:var(--blue-pale); color:var(--blue-dark);}
.preset b{display:block; font-size:11.5px; margin-bottom:2px;}
.slider-row{margin-bottom:16px;}
.slider-row .sl-head{display:flex; justify-content:space-between; font-size:11.5px; font-weight:600; margin-bottom:6px;}
input[type=range]{width:100%; accent-color:var(--blue);}

.coming-soon{text-align:center; padding:30px 20px; color:var(--muted); font-size:12.5px;
  background:var(--bg); border:1px dashed var(--border-strong); border-radius:10px;}
"""

JS_BLOCK = r"""
function showTab(id, el){
  document.querySelectorAll('.tabpanel').forEach(p=>p.style.display='none');
  document.getElementById('tab-'+id).style.display='block';
  document.querySelectorAll('.tabbar .tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
}
function deepDive(){
  const overviewBtn = document.querySelector('.tabbar .tab');
  showTab('overview', overviewBtn);
  const target = document.querySelector('#tab-overview .card');
  if(target) target.scrollIntoView({behavior:'smooth', block:'start'});
}
function goToDistrict(sel){
  const v = sel.value;
  window.location.href = '/dashboard' + (v === 'average' ? '' : ('?district=' + encodeURIComponent(v)));
}
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

def render_coming_soon(message: str) -> str:
    return f'<div class="coming-soon">🚧 <b style="color:var(--text)">Not built yet</b><br>{message}</div>'


def friction_word(friction: float) -> tuple[str, str]:
    if friction < 0.2:
        return "Easy", "#10B981"
    if friction < 0.5:
        return "Moderate", "#F5A524"
    return "Hard", "#EF4444"


def render_price_table(df, n: int = 8) -> str:
    if df is None or df.empty:
        return render_coming_soon("No price data available.")
    rows = ""
    for _, r in df.head(n).iterrows():
        rows += (f"<tr><td>{str(r['town']).title()}</td><td>S${r['avg_price']:,.0f}</td>"
                 f"<td>{int(r['num_transactions'])}</td></tr>")
    return f'<table class="sg-table"><tr><th>Town</th><th>Avg Price</th><th>Txns</th></tr>{rows}</table>'


def render_vfm_table(df, n: int = 10) -> str:
    if df is None or df.empty:
        return render_coming_soon("VFM ranking needs price + connectivity data.")
    rows = ""
    for _, r in df.head(n).iterrows():
        rows += (f"<tr><td>{str(r['town']).title()}</td><td>{r['vfm_score']:.1f}</td>"
                 f"<td>S${r['avg_price']:,.0f}</td><td>{r['vfm_verdict']}</td></tr>")
    return f'<table class="sg-table"><tr><th>Town</th><th>VFM</th><th>Avg Price</th><th>Verdict</th></tr>{rows}</table>'


def _verdict_class(score):
    return "g" if score >= 80 else ("a" if score >= 65 else "r")


def _verdict_label(score):
    return "Well connected" if score >= 80 else ("Moderate" if score >= 65 else "Poor")


def render_leaderboard(rank_list: list, highlight_district: str | None = None) -> str:
    if not rank_list:
        return render_coming_soon("No ranking data available.")
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


def render_heatmap(pattern) -> str:
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


def render_24h_line_chart(df) -> str:
    if df is None or df.empty:
        return render_coming_soon("Model needs at least 50 recent snapshots to predict.")
    vals = df["predicted_count"].tolist()
    if len(vals) < 2:
        return render_coming_soon(f"Only {len(vals)} forecast point available — need at least 2 to draw a line. "
                                  "The model needs more recent snapshot history for this district.")
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


def render_price_trend_chart(df) -> str:
    if df is None or df.empty:
        return render_coming_soon("No transaction history for this town/flat-type combination.")
    vals = df["avg_price"].tolist()
    if len(vals) < 2:
        return render_coming_soon(f"Only {len(vals)} month of price history available — need at least 2 to draw a trend.")
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
      <div class="price-tiles">
        <div class="sg-price-tile"><div class="l">LATEST AVG PRICE</div><div class="v">S${latest_price:,.0f}</div></div>
        <div class="sg-price-tile"><div class="l">PRICE CHANGE</div>
          <div class="v" style="color:{'var(--teal)' if change>=0 else 'var(--red)'}">
            {'+' if change>=0 else ''}S${change:,.0f} ({pct:+.1f}%)</div></div>
        <div class="sg-price-tile"><div class="l">TOTAL TRANSACTIONS</div><div class="v">{total_txn}</div></div>
      </div>"""


def render_alerts(alerts: list) -> str:
    if not alerts:
        return '<div class="chip ok" style="display:block; text-align:center; padding:10px;">✅ No alerts — all clear</div>'
    return "".join(f'<div class="chip warn" style="display:block; margin-bottom:6px;">⚠️ {a["alert_type"]} · {a["message"]}</div>' for a in alerts)


def render_local_snapshot(snapshot: dict | None) -> str:
    """snapshot: output of hdb.onemap_services.get_block_transport_profile() —
    real OneMap API data (nearest MRT, nearest bus stop, CBD commute time)."""
    if not snapshot:
        return render_coming_soon("Nearest MRT, bus coverage, and commute time need a valid "
                                  "ONEMAP_TOKEN and network access — couldn't reach OneMap for this district.")

    mrt = snapshot.get("nearest_mrt") or {}
    bus = snapshot.get("nearest_bus") or {}
    commute = snapshot.get("cbd_commute") or {}

    mrt_row = f"""<div class="local-row">
      <div><div class="local-title">🚇 Nearest MRT — {mrt.get('name', 'Unknown')}</div>
      <div class="local-sub">{mrt.get('distance_label','—')} · {mrt.get('walking_min','—')} min walk</div></div>
    </div>""" if mrt.get("name") and mrt.get("name") != "No MRT nearby" else render_coming_soon("No MRT within 2km.")

    bus_row = f"""<div class="local-row">
      <div><div class="local-title">🚌 Nearest Bus Stop — {bus.get('description','Unknown')}</div>
      <div class="local-sub">{bus.get('distance_label','—')} · {bus.get('num_stops','—')} stops within 500m</div></div>
    </div>""" if bus.get("stop_code") else render_coming_soon("No bus stop within 500m.")

    commute_row = f"""<div class="local-row">
      <div><div class="local-title">🏢 Commute to CBD</div>
      <div class="local-sub">{commute.get('total_time_min','—')} min by public transport
      {f"· {commute.get('num_transfers')} transfers" if commute.get('num_transfers') is not None else ''}</div></div>
    </div>""" if commute.get("total_time_min") is not None else render_coming_soon("Route to CBD unavailable right now.")

    return f'<div class="local-snapshot-list">{mrt_row}{bus_row}{commute_row}</div>'


def render_forecast_col(forecast: dict) -> str:
    if not forecast:
        return ('<div class="stat-line"><span class="l">+30 MIN</span><span class="v" style="color:var(--muted)">—</span></div>'
                '<div class="stat-line"><span class="l">+60 MIN</span><span class="v" style="color:var(--muted)">—</span></div>'
                '<div class="stat-line"><span class="l">+2 HR</span><span class="v" style="color:var(--muted)">—</span></div>')
    v30 = forecast.get(30, 0)
    v60 = forecast.get(60, 0)
    v120 = forecast.get(120, 0)
    return (f'<div class="stat-line"><span class="l">+30 MIN</span><span class="v" style="color:var(--teal)">{v30:.0f}</span></div>'
            f'<div class="stat-line"><span class="l">+60 MIN</span><span class="v" style="color:var(--amber)">{v60:.0f}</span></div>'
            f'<div class="stat-line"><span class="l">+2 HR</span><span class="v" style="color:var(--red)">{v120:.0f}</span></div>')

def build_full_page(selected_name: str, data: dict, extra: dict, district_names: list[str]) -> str:
    """Assemble the whole dashboard as one real HTML page.

    selected_name: "average" or a district name exactly as it appears in
                   district_names (title case, e.g. "Ang Mo Kio")
    data: dict with keys — live_taxis, avg_taxi, friction, alerts, alerts_list,
          conn_score, verdict, price, bus (dict or None), forecast (dict)
    extra: dict with keys — rank, town_summary, pattern, hourly_forecast,
           peaks, price_trend, vfm, trend_town
    district_names: all real district names, for the <select> dropdown
    """
    is_average = selected_name == "average"
    display_name = "Singapore Average" if is_average else selected_name
    try:
        now = datetime.now(SGT)
        hour12 = now.hour % 12 or 12
        now_str = f"{now.strftime('%a')} {hour12}:{now.strftime('%M%p').lower()}"
    except Exception:
        now_str = ""

    fw, fw_color = friction_word(data["friction"])
    price_txt = f"S${data['price']:,.0f}" if data["price"] else "—"
    raw_score = data["conn_score"]
    verdict_sentence = data["verdict"] or ""  # the full descriptive sentence, e.g. "❌ Poor connectivity — transit friction is high"

    if is_average:
        # Averaging 55 districts' scores together isn't very meaningful, and
        # right now most districts read near-0 anyway (bus data hasn't been
        # registered for most of them yet — see the monitored-stops issue).
        # Showing a misleading "0" here does more harm than good.
        score_txt = "—"
        short_verdict, verdict_color = "N/A", "#8B95A5"
        verdict_sentence = "Select a specific district above for a real connectivity score."
    elif raw_score is None:
        score_txt = "—"
        short_verdict, verdict_color = "N/A", "#8B95A5"
    else:
        score_txt = raw_score
        if raw_score >= 75:
            short_verdict, verdict_color = "GOOD", "#10B981"
        elif raw_score >= 50:
            short_verdict, verdict_color = "MODERATE", "#F5A524"
        else:
            short_verdict, verdict_color = "POOR", "#EF4444"

    verdict_txt = short_verdict  # short word — safe to put inside small badge pills
    scope_text = ("🇸🇬 Singapore Average · across 55 planning areas" if is_average
                  else f"📍 {selected_name} · district detail")

    # ── district dropdown ──
    options_html = f'<option value="average"{" selected" if is_average else ""}>🇸🇬 Singapore Average</option>'
    for name in district_names:
        sel = " selected" if name == selected_name else ""
        options_html += f'<option value="{name}"{sel}>{name}</option>'

    # ── Transport Timeliness / baseline for score-weights calculator ──
    if data.get("bus"):
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
        baseline = dict(bus=b['bus_frequency_score']/100, stability=b['taxi_stability_score']/100,
                        friction=min(1.0, data['friction']))
    else:
        timeliness_html = render_coming_soon("No bus data for this scope.")
        baseline = dict(bus=0.73, stability=0.87, friction=0.68)

    leaderboard_html = render_leaderboard(extra.get("rank") or [], highlight_district=None if is_average else selected_name)
    price_table_html = render_price_table(extra.get("town_summary"), n=8)
    alerts_html = render_alerts(data.get("alerts_list", []))

    # ── 24H Forecast tab ──
    if is_average:
        forecast_tab_html = render_coming_soon("Pick a specific district above — hourly forecasts and the "
                                                "weekly pattern are per-district, a citywide average wouldn't mean much here.")
    else:
        heatmap_html = render_heatmap(extra.get("pattern"))
        chart_html = render_24h_line_chart(extra.get("hourly_forecast"))
        peaks_html = render_peak_ratings(extra.get("peaks") or [])
        forecast_tab_html = f"""
        <div class="card"><h3>📅 Weekly Taxi Availability Heatmap · {selected_name}</h3>
          <div class="sub">Real historical average by hour × day of week.</div>{heatmap_html}</div>
        <div class="card"><h3>📈 24-Hour Forecast</h3>
          <div class="sub">Ridge model prediction for the next 24 hours.</div>{chart_html}</div>
        <div class="card"><h3>⏰ Peak Hour Ratings — Tomorrow</h3>{peaks_html}</div>"""

    # ── Map & Housing Prices tab ── (the live map itself is in the hero at the top of every page)
    trend_html = render_price_trend_chart(extra.get("price_trend"))
    town_table_html = render_price_table(extra.get("town_summary"), n=len(extra.get("town_summary", [])) or 8)
    vfm_html = render_vfm_table(extra.get("vfm")) if extra.get("vfm") is not None else render_coming_soon(
        "VFM ranking not available.")
    map_tab_html = f"""
        <div class="card"><h3>📈 Price Trend · {extra.get('trend_town','')}</h3>{trend_html}</div>
        <div class="grid-2">
          <div class="card"><h3>💰 Price by Town</h3>{town_table_html}</div>
          <div class="card"><h3>🏆 Value-for-Money Ranking</h3>{vfm_html}</div>
        </div>"""

    baseline_json = json.dumps(baseline)
    basis_note = "this district's live evaluation" if not is_average else "citywide average (illustrative)"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>SG Liveability</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS_TEXT}</style>
</head>
<body>
<header class="topnav">
  <div class="topnav-inner">
    <div class="brand"><div class="mark">A</div>SG Liveability</div>
    <div class="nav-right">
      <select class="district-select" onchange="goToDistrict(this)">{options_html}</select>
    </div>
  </div>
</header>

<main>
  <div class="hero-map-row">
    <iframe src="/sg_map.html" class="map-embed hero-map"></iframe>
    <div class="hero-summary hero-summary-side">
      <div class="fc-head">{display_name.upper()} · {now_str}</div>
      <div class="hero-ring" style="border-color:{verdict_color}; color:{verdict_color};">{score_txt}</div>
      <div>
        <div class="fc-verdict" style="color:{verdict_color};">{verdict_txt}</div>
        <div class="fc-verdict-sub">Connectivity Score</div>
        {f'<div class="fc-verdict-desc">{verdict_sentence}</div>' if verdict_sentence else ''}
      </div>
      <div class="hero-stats hero-stats-stacked">
        <div><span class="hero-stat-label">🚕 taxis nearby</span><span class="hero-stat-val">{data['live_taxis']}</span></div>
        <div><span class="hero-stat-label">🚌 bus stops</span><span class="hero-stat-val">{data['bus']['stops_in_bbox'] if data.get('bus') else '—'}</span></div>
        <div><span class="hero-stat-label">🚨 active alerts</span><span class="hero-stat-val">{data['alerts']}</span></div>
      </div>
      <div class="hero-missing-note">📍 Nearest MRT + bus stop now live in Local Snapshot below · specific bus route numbers still not wired.</div>
      <button class="deep-dive-btn" onclick="deepDive()">View Deep Dive →</button>
    </div>
  </div>

  <div class="scope-badge">{scope_text}</div>

  <div class="kpi-row">
    <div class="kpi"><div class="kpi-label">LIVE TAXIS</div><div class="kpi-val">{data['live_taxis']}</div><div class="kpi-sub">this minute</div></div>
    <div class="kpi"><div class="kpi-label">AVERAGE TAXI</div><div class="kpi-val">{data['avg_taxi']}</div><div class="kpi-sub">60-min rolling avg</div></div>
    <div class="kpi"><div class="kpi-label">GETTING A TAXI</div><div class="kpi-val" style="color:{fw_color}">{fw}</div><div class="kpi-sub">friction {data['friction']:.3f}</div></div>
    <div class="kpi"><div class="kpi-label">ALERTS</div><div class="kpi-val" style="color:var(--teal)">{data['alerts']}</div><div class="kpi-sub">recent anomaly events</div></div>
    <div class="kpi highlight" style="border-color:{verdict_color}; background:{verdict_color}1A;">
      <div class="kpi-label">CONNECTIVITY SCORE</div>
      <div class="kpi-val">{score_txt} <span class="badge-mod" style="background:{verdict_color}">{verdict_txt}</span></div>
      <div class="kpi-sub">/100</div></div>
    <div class="kpi"><div class="kpi-label">AVG HDB PRICE</div><div class="kpi-val">{price_txt}</div><div class="kpi-sub">last 12mo · 4 ROOM</div></div>
  </div>

  <div class="tabbar">
    <button class="tab active" onclick="showTab('overview',this)">Overview</button>
    <button class="tab" onclick="showTab('forecast',this)">24H Forecast</button>
    <button class="tab" onclick="showTab('weights',this)">⚖ Score Weights</button>
    <button class="tab" onclick="showTab('map',this)">💰 Housing Prices</button>
  </div>

  <div id="tab-overview" class="tabpanel">
    <div class="grid-2">
      <div>
        <div class="card"><h3>⏱ Transport Timeliness</h3>
          <div class="sub">Real-time bus + taxi service quality · {display_name}</div>
          {timeliness_html}
        </div>
        <div class="card"><h3>🏆 District Leaderboard</h3>
          <div class="sub">Connectivity score ranking across districts</div>{leaderboard_html}</div>
      </div>
      <div>
        <div class="card"><h3>📍 Local Snapshot</h3>
          {render_coming_soon("Pick a specific district above for nearest MRT, bus coverage, and commute time.") if is_average else render_local_snapshot(data.get('local_snapshot'))}</div>
        <div class="card"><h3>💰 Price Snapshot</h3>
          <div class="sub">Resale prices · {display_name}</div>{price_table_html}</div>
        <div class="card"><h3>🚨 Anomaly Alerts</h3>{alerts_html}</div>
      </div>
    </div>
  </div>

  <div id="tab-forecast" class="tabpanel" style="display:none;">{forecast_tab_html}</div>

  <div id="tab-weights" class="tabpanel" style="display:none;">
    <div class="card">
      <h3>⚖ Score Formula &amp; Weights</h3>
      <div class="sub">🧪 This is a <b>what-if calculator</b> — it does not change the real Connectivity Score shown at the top of the page.
      It shows what the score would be if the formula weighted Bus vs. Taxi differently. "Balanced (your real defaults)"
      matches your actual live formula (Bus 50% · Stability 30% · Friction 20%, from config.py) — moving sliders explores hypothetical alternatives.</div>
      <div class="sub">Baseline sub-scores from {basis_note}</div>
      <div class="modal" style="border:none; box-shadow:none; padding:0;">
        <div class="formula">
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
          <div class="preset active" onclick="setPreset(50,60,this)"><b>Balanced (your real defaults)</b>Bus 50% · Taxi 50%</div>
          <div class="preset" onclick="setPreset(25,60,this)"><b>Taxi-reliant</b>Bus 25% · Taxi 75%</div>
        </div>
        <div class="slider-row"><div class="sl-head"><span>🚌 Bus</span><span id="busPct">50%</span></div>
          <input type="range" id="busSlider" min="0" max="100" value="50" oninput="recalc()">
          <div class="sl-head" style="margin-top:2px;"><span style="color:var(--muted-2); font-weight:500;">🚕 Taxi (auto-balances)</span><span id="taxiPctTop" style="color:var(--muted-2); font-weight:500;">50%</span></div></div>
        <div class="slider-row"><div class="sl-head"><span>Taxi Stability (reward)</span><span id="stabPct">60%</span></div>
          <input type="range" id="stabSlider" min="0" max="100" value="60" oninput="recalc()">
          <div class="sl-head" style="margin-top:2px;"><span style="color:var(--muted-2); font-weight:500;">Friction (auto-balances)</span><span id="fricPctSub" style="color:var(--muted-2); font-weight:500;">40%</span></div></div>
      </div>
    </div>
  </div>

  <div id="tab-map" class="tabpanel" style="display:none;">{map_tab_html}</div>
</main>

<script>
const BASELINE = {baseline_json};
{JS_BLOCK}
</script>
</body></html>"""
