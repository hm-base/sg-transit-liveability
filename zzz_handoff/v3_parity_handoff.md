# SG Liveability — v1 → v3 Feature Parity & Theme Fix

**Task for Claude Code**: Fix the theme-inheritance bug in `dashboard/app_v3.py`, then port every feature that works in `dashboard/app.py` (v1) into v3, rebuilt in v3's light HTML/CSS style. Do NOT redesign v3 — v3's look is the approved design. v1 is the *feature* reference; v3 is the *style* reference.

---

## 0. Context you need before touching anything

- **v1** = `dashboard/app.py`. Streamlit-native widgets + Plotly charts, dark Streamlit theme. Everything works but looks like default Streamlit.
- **v3** = `dashboard/app_v3.py`. Python fetches the same real data, then builds one big HTML string per section and renders it via `st.markdown(..., unsafe_allow_html=True)`. Charts are hand-built inline **SVG** (see `render_24h_line_chart`, `render_price_trend_chart`), NOT Plotly. Keep it that way — Plotly widgets break the unified look (that's why v2/Streamlit-native was rejected).
- The only `components.html()` iframes allowed: the score-weights JS widget and the `sg_map.html` embed. Everything else is `st.markdown` HTML.
- Data layer is shared and already works: `storage.database`, `ml.forecaster`, `ml.extended_forecaster`, `hdb.analytics`, FastAPI at `http://127.0.0.1:8000` (`call_api` helper, may be offline — every section must degrade to `render_coming_soon(...)` style placeholders, never crash).
- Run with: `streamlit run dashboard/app_v3.py --server.port 8502` from project root. v1 stays untouched at `dashboard/app.py`.

---

## 1. CRITICAL BUG — fix first: white-on-white text under dark Streamlit theme

v3's HTML lives inside Streamlit's DOM via `st.markdown`. When the user's Streamlit theme is **dark**, Streamlit sets `color: white` on its containers, and every v3 element that doesn't declare its own `color` inherits white → invisible on white cards. The `html,body{color:var(--text)}` rule in `CSS_TEXT` never applies because in `st.markdown` mode our HTML has no `body` of its own.

**Fix**: replace the top style block (the `st.markdown("""<style> ... """)` right after `st.set_page_config`) with:

```python
st.markdown("""
<style>
/* Force a light shell regardless of the user's Streamlit theme setting. */
.stApp { background: #F3F6FA !important; }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
.block-container { padding-top: 1rem; max-width: 1500px; }

/* Streamlit's DARK theme sets color:white on its containers; our elements
   without an explicit color inherit it → white-on-white. Force dark ink. */
div[data-testid="stMarkdownContainer"] { color: #0F172A; }
div[data-testid="stMarkdownContainer"] p { color: inherit; }

/* Classes that previously relied on inheritance */
.kpi-val, .card h3, .card h4, .brand,
.stat-line .v, .bar-val, .sg-bar-val,
.row-title, .fc-row span:last-child,
.price-tile .v, .sg-price-tile .v,
table td, table.sg-table td,
.acc-head, .modal { color: #0F172A; }

/* Streamlit-native tab labels + captions also go invisible in dark theme */
button[data-baseweb="tab"] { color: #6B7686 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: #2F7DED !important; }
div[data-testid="stCaptionContainer"] { color: #6B7686 !important; }
div[data-testid="stExpander"] summary { color: #0F172A !important; }
div[data-testid="stExpander"] { background: #FFFFFF; border-color: #E4E9F0 !important; }

div[data-baseweb="select"] > div {
  background: #FFFFFF !important; border: 1px solid #D3DBE5 !important;
  border-radius: 10px !important; font-family: 'JetBrains Mono', monospace !important;
}
div[data-baseweb="select"] span { color: #0F172A !important; }
label { color: #6B7686 !important; font-family: 'JetBrains Mono', monospace !important; font-size: 11px !important; }
</style>
""", unsafe_allow_html=True)
```

**Rule going forward: every new element you add must declare its own `color` (or a listed ancestor class must). Never rely on inheritance from Streamlit.** Verify the fix with the Streamlit theme set to DARK — the dashboard must look identical in light and dark.

---

## 2. Style guide (v3 tokens — use these, nothing else)

CSS variables already defined in `CSS_TEXT` in app_v3.py:

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F3F6FA` | page + inset tile background |
| `--card` | `#FFFFFF` | card background |
| `--border` / `--border-strong` | `#E4E9F0` / `#D3DBE5` | hairlines |
| `--text` | `#0F172A` | primary ink |
| `--muted` / `--muted-2` | `#6B7686` / `#8B95A5` | labels, subs |
| `--blue` / `--blue-dark` / `--blue-pale` | `#2F7DED` / `#1A5FC4` / `#EAF2FE` | accents, active tab, chips |
| `--teal` / `--teal-pale` | `#10B981` / `#E6F9F1` | good / positive |
| `--amber` / `--amber-pale` | `#F5A524` / `#FEF3DE` | moderate |
| `--red` / `--red-pale` | `#EF4444` / `#FDEAEA` | poor / alerts |
| `--radius` | `14px` | card corners |

Conventions:
- Numbers, labels, table text: `'JetBrains Mono', monospace`. Body prose: Inter.
- Reuse existing classes: `.card` + `h3` + `.sub`, `.kpi`, `.stat-line`, `.chip.ok/.mid/.bad`, `.dot.g/.a/.r`, `table.sg-table`, `.fc-box`, `render_coming_soon()`.
- Charts = inline SVG in the v3 pattern: 900-wide viewBox, `preserveAspectRatio="none"`, gridlines `#E4E9F0`, series in `--blue`, bands as translucent blue fills, axis labels 9px mono `--muted`. Copy the structure of `render_24h_line_chart` / `render_price_trend_chart`.
- **SVG gotcha (known bug)**: a polyline with <2 distinct points renders nothing. Guard every chart: if fewer than 2 points → `render_coming_soon(...)`.
- Verdict colors: score ≥75 teal "Good", 50–74 amber "Moderate", <50 red "Poor" (match `_verdict_class/_verdict_label`).

---

## 3. Feature parity checklist (v1 → v3)

Work top to bottom. Each item names the v1 source (in `dashboard/app.py`) and where it lands in v3.

### 3.1 Taxi availability — history & forecast chart ✅ DONE
- v1: `go.Scatter` actual-taxis line + ±2σ normal-range band + ML prediction diamonds (+30/60/120 min), ~lines 133–162.
- v3 target: new card in the **Overview** tab (`build_overview_html`), full width above Transport Timeliness.
- Build as SVG: history line from `fetch_snapshots(slug, minutes=history_window)`, translucent band = mean±2σ of the window, 3 diamond markers (`--amber`, purple `#A855F7`, `--teal`) at the right edge from `TaxiForecaster(slug).predict()`.
- For `slug == "average"`: sum counts across districts per timestamp, or show `render_coming_soon` if too heavy — pick one, don't crash.
- Legend row under the chart: 9px mono chips matching v1's legend.

### 3.2 Taxi flux chart ✅ DONE
- v1: `px.bar` of last 30 flux values (~line 167).
- v3 target: same Overview card or a sibling card. SVG bar chart: positive bars `--teal`, negative `--red`, zero-line `--border-strong`. Caption: "Positive = taxis arriving · Negative = taxis leaving".

### 3.3 Anomaly alerts list ✅ DONE (24h-scoped, type chips)
- v1: right column list of alert rows: `LOW_TAXI · <district>: only N taxis (mean=X, threshold=Y)`.
- v3: `render_alerts` exists but shows in the Overview side column with invisible text (fixed by §1). Verify it shows type badge (`.chip.bad` for LOW_TAXI, `.chip.mid` for HIGH_FLUX / BUS_GAP), district, message, SGT timestamp via `to_sgt`-equivalent. Cap at 8 rows + "…and N more" line.
- **Data bug to fix while here**: the ALERTS KPI shows a raw total (e.g. 200) unscoped to district/time. Scope it: `fetch_alerts` for the selected slug within the last 24h; for "average" show the 24h citywide count. Label the KPI sub accordingly ("last 24h").

### 3.4 Model performance panel ✅ DONE (24H tab)
- v1: `fetch_latest_metrics` → per-horizon MAE with badges (Great/Good/OK) + "Off by ~N taxis on average".
- v3 target: small card in Overview side column, `.stat-line` rows: `+30 MIN / +60 MIN / +2 HR`, value = MAE, chip: MAE ≤3.5 `.chip.ok` "GREAT", ≤4.5 `.chip.mid` "GOOD", else "OK". Coming-soon fallback if no metrics rows.

### 3.5 Forecasts panel (next taxi counts) ✅ DONE (+trio card on 24H tab)
- `render_forecast_col` already does +30/+60/+2h. Just confirm visible after §1 and shows em-dash fallbacks when the model can't predict.

### 3.6 Bus connectivity breakdown ✅ DONE (3 progress bars when live)
- v1: bus stops count, avg frequency ("Every ~13 min" + status dot), bus score, route redundancy (+unique routes chip), connectivity score, then 3 labelled progress bars (Bus frequency / Taxi stability / Friction penalty) with score + verdict each.
- v3: the mini-grid in `build_overview_html` covers part of this when live. Add the **3 progress bars** row: track `--bg` with `--border`, fill `--blue`, height 6px radius 3px, label left / `NN/100 — <verdict>` right in mono. Requires live `/evaluate` data; otherwise the existing coming-soon placeholder stands.

### 3.7 District leaderboard ✅ DONE (re-weights with score-weight sliders; verdict thresholds fixed to 75/50)
- `render_leaderboard` bars + table already match v1's ranking. After §1, confirm bar values, district names, and table rows are visible; bar colors follow verdict colors (currently all red in screenshots because live scores were <50 — that's data, not a bug).

### 3.8 Extended forecasts: 24H chart / peak ratings / day heatmap ✅ DONE (peak shading added)
- `render_24h_line_chart`, `render_peak_ratings`, `render_heatmap` exist in the 24H Forecast tab. Verify against v1: 24h chart should mark the Peak region like v1 does (shaded band + "Peak" label); heatmap 7×24 with day labels; peak pills 🟢🟡🔴. Add the peak shading if absent. Guard the <2-points SVG bug.

### 3.9 Price trend — town selector ✅ DONE (+flat type, months, VFM weight controls)
- v1: dropdown to pick any town, chart updates, plus tiles: Latest avg price / Price change (+% chip) / Total transactions.
- v3: hardcodes `towns[0]`. Fix: add a Streamlit `st.selectbox` for town (and one for flat type: reuse `get_flat_types()`) above the price-trend card inside the Map & Housing Prices tab, styled by the existing `div[data-baseweb="select"]` overrides. Re-render `render_price_trend_chart` + the 3 `.price-tile`s from the selection.

### 3.10 Block transport profile (postal code + radius) ✅ DONE
- v1: postal-code text input + search-radius slider + Fetch → real-time transport + HDB prices near that block.
- v3 target: card at the bottom of Map & Housing Prices tab. Native `st.text_input` + `st.slider` + `st.button` (style the button dark-ink like `.deep-dive`), results rendered as a v3 HTML card: nearest stops `.stat-line`s, nearby HDB avg price tile, connectivity chip. Uses the same backend v1 calls (see v1 ~lines 470+ / `onemap_services`, `geocoder`). Coming-soon fallback if API/OneMap token unavailable.

### 3.11 Auto-refresh + last-refresh stamp ✅ DONE (stamp + manual ↻)
- v1: sidebar "Auto-refresh every 60s" checkbox + "Last refresh HH:MM:SS SGT".
- v3 target: small mono caption right-aligned next to the district selector: `Last refresh 21:12 SGT · auto 60s`. Implement with `st.checkbox` (default on) + `time.sleep`-free approach: `st.autorefresh` isn't core Streamlit, so use `st_autorefresh` from `streamlit-extras`/`streamlit-autorefresh` if already in requirements; otherwise a manual "↻ Refresh" button is acceptable — do not add heavy new dependencies without noting it in requirements.txt.

### 3.12 Retrain model button ✅ DONE (Score Weights popover footer)
- v1 sidebar "Retrain model now". v3: put inside the Score Weights expander or Glossary tab footer as a small outline button; call the same retrain function v1 calls. Skip if it complicates layout — mark as TODO comment instead.

### 3.13 History window slider ✅ DONE (30–360 min)
- v1: "History (minutes)" slider controls chart window. v3: `st.slider(30–360, default 60)` next to the district selector; feed it into 3.1/3.2 queries.

### 3.14 Compare tab ✅ DONE (built per mockup — user overrode the leave-as-is note)

---

## 4. Ground rules

1. **Never crash on missing data.** Every section wraps its data access in try/except and falls back to `render_coming_soon("<what it needs>")` — same as existing code.
2. **No Plotly, no Streamlit-native charts** in v3 content areas. SVG only, per §2.
3. **No new heavyweight dependencies** without adding them to `requirements.txt` and flagging it in your summary.
4. Keep the district selector → full-page rerun architecture. Native Streamlit controls are only allowed for: district selector, town/flat-type selectors, history slider, postal input, refresh control, tabs, expander.
5. Prefer full-function replacements over inline surgical edits when a builder function changes substantially.
6. After changes, test BOTH themes: Streamlit menu → Settings → Theme → Dark, then Light. Zero invisible text in either.
7. Test with `python main.py` NOT running (offline fallbacks) and running (live data).
8. Commit checkpoints: one commit for §1 theme fix, then one commit per §3 item (or small groups), messages like `v3: port taxi history+forecast chart (parity 3.1)`.

## 5. Definition of done

- [x] Dark Streamlit theme shows zero invisible text anywhere in v3
- [x] Overview: history+forecast SVG chart, flux chart, alerts (scoped 24h), model performance, forecasts all visible with real data
- [x] Bus connectivity shows the 3 score-breakdown bars when live
- [x] 24H tab has peak shading, heatmap, peak pills
- [x] Price trend has town + flat-type selectors with tiles updating
- [x] Block transport profile works end-to-end (or clean coming-soon if OneMap token missing)
- [x] Refresh stamp + history slider present
- [x] App never throws with pipeline offline
