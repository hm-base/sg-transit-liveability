# v3 Dashboard — Mockup Fidelity + v1 Feature Parity

**Date:** 2026-07-12
**Target file:** `dashboard/app_v3.py` (plus `dashboard/sg_map.html`, `api.py` already fixed)
**References:**
- Style/layout reference: `desgin_ideas/sg_liveability_v3_mockup.html` (the approved design)
- Feature reference: `dashboard/app.py` (v1) via `zzz_handoff/v3_parity_handoff.md`
- Style tokens + ground rules: `zzz_handoff/v3_parity_handoff.md` §2 and §4 apply verbatim to all work below

## Goal

Bring `app_v3.py` to (a) visual fidelity with the v3 mockup and (b) full feature
parity with v1. v3's light HTML/CSS look is the approved design; v1 is the
feature reference. Charts remain hand-built inline SVG; the only iframes are the
score-weights JS widget and the `sg_map.html` embed.

## Decisions made with the user

| Question | Decision |
|---|---|
| Landing/onboarding page from mockup | **Skip.** Dashboard loads directly. |
| Topnav search box | **Omit.** The district selectbox has built-in type-to-search; a second search input is redundant. |
| Day (📅 Tue) + time (7:30am) pills | **Wire to real forecasts** (see §Chrome). Not decorative. |
| Compare tab | **Build it** (overrides parity doc's "leave as coming-soon"). |
| Score Weights modal | **`st.popover`** — closest native analog; replaces the expander. |
| Architecture | Extend current v3 pattern (st.markdown HTML fragments + SVG). No mega-iframe rewrite. |

## Already done (this session, uncommitted)

- Dark-theme ink fixes incl. expander white background (§1 of parity doc).
- Top-of-page map strip + floating connectivity card (mockup layout restored).
- `sg_map.html`: `API_BASE` falls back to `http://127.0.0.1:8000` inside the
  srcdoc iframe; `#map` height is viewport-relative.
- `api.py`: CORS middleware registered (was imported, never added).

## Design

### 1. Chrome

- Topnav: brand + district pill (as-is).
- District selectbox labels show live scores — `"Ang Mo Kio · 78"` — built from
  the cached `/rank` response; plain names when offline. Selection still maps
  by slug, not label text.
- **Day + hour selectors** (two compact `st.selectbox`es) beside the district
  selector, defaulting to current SGT day/hour. They drive:
  - float-card header: `ANG MO KIO · TUE 7:30AM`;
  - an "expected taxis at this time" line in the float card from
    `DayPatternAnalyser.get_pattern()` (day×hour average);
  - the peak chips in Local Snapshot (`PeakHourPredictor`).
  - The KPI row is always live-now. For `slug == "average"` there is no
    per-district pattern: show a one-line caption instead of the pattern value.
- **History window slider** (`st.slider` 30–360 min, default 60) beside the
  selectors; feeds the taxi history + flux charts (§3).
- **Refresh control:** mono caption `Last refresh HH:MM SGT` + a small
  "↻ Refresh" button (`st.rerun`). No new dependencies.

### 2. Score Weights popover

`st.popover("⚖ Score Weights")` in a narrow right-aligned column on its own
row directly above the tab bar (Streamlit cannot inject widgets into the
native tab strip — this is the closest layout to the mockup's tabbar button). Contents: the existing `components.html` JS calculator (unchanged),
plus a footer row with the **Retrain model** button calling
`TaxiForecaster(district).train(lookback_min=1440)` with a spinner and
result caption. The expander is removed.

### 3. Overview tab

Order: history card (new, full width) → Transport Timeliness → Leaderboard on
the left; Local Snapshot → Price Snapshot → Alerts on the right.

- **Taxi availability — history & forecast** (parity 3.1): SVG line chart from
  `fetch_snapshots(slug, minutes=history_window)`; translucent blue ±2σ band
  (window rolling mean/std); 3 diamond markers at the right edge from
  `TaxiForecaster.predict()` in amber / `#A855F7` / teal; 9px mono legend row.
  **Rubric requirement:** also overlay *past* predictions whose target time
  falls inside the history window (`fetch_predictions`, `created_at +
  horizon`) as hollow diamonds on the actual line, so predicted-vs-actual is
  visible at a glance ("compare earlier predictions with actual taxi
  availability once the actual data becomes available" — grading rubric, ML &
  Real-Time Output, 30 marks).
  For `average`: sum counts across districts per timestamp; if the query is
  empty or too heavy, `render_coming_soon`. Guard: <2 distinct points →
  `render_coming_soon`.
- **Taxi flux** (3.2): SVG bar chart of last 30 flux values in the same card
  (stacked below the history chart). Positive bars `--teal`, negative `--red`,
  zero-line `--border-strong`. Caption: "Positive = taxis arriving · Negative =
  taxis leaving".
- **Local Snapshot** (mockup rows, replaces placeholder):
  - 🚇 MRT row: nearest station + distance via `hdb.onemap_services`
    (`get_nearest_mrt`) for the district bbox centroid; for `average` show the
    citywide static line ("6 lines · 134 stations citywide"). Row-level "—"
    fallback if OneMap token missing.
  - 🚌 Bus row: stops + avg headway from live `/evaluate`; badge = bus score.
  - 🚕 Taxi row: live count + friction; badge = verdict color. Peak chips row
    beneath from `PeakHourPredictor.predict_peaks()` (✓/~/✗ per hour).
  - 🏢 Commute to CBD row: only if OneMap routing is available in
    `onemap_services`; otherwise render the row with "—" badge and sub
    "needs OneMap routing". Never drop the whole card for one row.
- **Price Snapshot** (mockup style): 3 tiles (AVG / MEDIAN / TXNS for the
  selected district's town where matchable, else citywide) + "TOP 5
  VALUE-FOR-MONEY" `vfm-list`. Falls back to citywide tiles + list when the
  district has no HDB town match.
- **Anomaly Alerts** (3.3): `fetch_alerts` scoped to selected slug, last 24h
  (citywide for `average`). Type badge chips (`.chip.bad` LOW_TAXI, `.chip.mid`
  HIGH_FLUX/BUS_GAP), district, message, SGT time. Cap 8 rows + "…and N more".
  The ALERTS KPI uses the same scoped count, sub-label "last 24h".
- **Bus connectivity bars** (3.6): inside Transport Timeliness when live —
  3 labelled progress bars (Bus frequency / Taxi stability / Friction penalty),
  track `--bg`, fill `--blue`, 6px/r3, `NN/100 — verdict` right-aligned mono.

### 4. 24H Forecast tab

Match mockup layout: heatmap card (existing, keep citywide-average note line),
24h line chart card **with peak shading** — `--red-pale` rects behind 7–9am and
5–7pm regions + "Peak" label (3.8) — then a `grid-2`:
- left: Anomaly Alerts (same renderer as Overview) + alert-type legend rows;
  Peak Hour Ratings boxes (existing renderer).
- right: **Model Performance** card (3.4): `.stat-line` rows +30/+60/+2HR, chip
  by MAE (≤3.5 GREAT ok / ≤4.5 GOOD mid / else OK), from `fetch_latest_metrics`
  filtered to district, falling back to the v1 static training numbers with the
  "training accuracy" note; plus the blue MAE explainer box from the mockup.
  **Taxi Forecast trio** card (existing `render_forecast_col` data in `fc-box`
  form).

### 5. Compare tab

Two `st.selectbox` pickers (default Ang Mo Kio vs Bishan), independent of the
main district selector. One v3 `sg-table`: Connectivity Score, Bus Score, Taxi
Stability, Friction, Avg Price (HDB town match), Nearest MRT (OneMap, "—" if
unavailable). Values colored by verdict where scored. Each metric row degrades
to "—" independently; whole tab never crashes offline.

### 6. Map & Housing Prices tab

- Keep: full-size map iframe (560px), Price by Town + VFM tables.
- **Controls card** (mockup): flat-type `st.selectbox` (`get_flat_types()`),
  months-of-data `st.slider` (1–24, default 12), transport-vs-affordability
  `st.slider` (0–100, default 50). Months + flat type re-query
  `get_town_summary`; the weight slider re-ranks VFM via
  `get_value_for_money`'s weight params.
- **Price Trend** (3.9): town `st.selectbox` + flat-type (shared with controls
  card) above the card; re-renders `render_price_trend_chart` + the 3 tiles.
- **Block Transport Profile** (3.10): postal `st.text_input` + radius
  `st.slider` + Fetch `st.button` (dark-ink style). Results as v3 card:
  nearest-stop `.stat-line`s, nearby HDB avg price tile, connectivity chip.
  Same backend as v1 (`onemap_services`, geocoder). Coming-soon if no token.

### 7. Ground rules (inherited from parity doc §4, restated)

1. Never crash on missing data — try/except per card → `render_coming_soon`.
2. SVG only in content areas; no Plotly/Streamlit-native charts.
3. Native widgets allowed: district/day/hour/town/flat-type selectors, history +
   months + weight + radius sliders, postal input, refresh + retrain + fetch
   buttons, compare pickers, tabs, popover.
4. Every new element declares its own `color`.
5. No new heavyweight dependencies.
6. Test both Streamlit themes (`--theme.base dark|light`) and both pipeline
   states (offline/online) per commit.

### 8. Commit plan

One commit per numbered design section (splitting §3 into 3.1+3.2 / snapshot
cards / alerts if diffs get large), messages like
`v3: taxi history+forecast SVG chart (parity 3.1)`. The already-done fixes
commit first as the §1 checkpoint.

## Rubric alignment (project_instructions.pdf)

The dashboard is graded under "ML and Real-Time Output" (30 marks). Items in
this spec that map directly to rubric examples:

- Live/regularly refreshed dashboard → refresh stamp + ↻ control (§1), live
  KPI row, live map.
- "Generate predictions for the next two hours" → forecast diamonds + trio.
- "Compare earlier predictions with actual" → past-prediction overlay (§3).
- "Evaluate the prediction model every day at 8:00 AM" → Model Performance
  card surfaces `fetch_latest_metrics` with the 08:00 SGT note (§4).
- "Detect unusually high or low taxi availability and trigger an alert" →
  scoped Anomaly Alerts card + alert-type legend (§3, §4).

## Definition of done

- [ ] Zero invisible text in dark AND light Streamlit themes
- [ ] Top strip: live map + float card with day/time-aware header
- [ ] District dropdown shows live scores when pipeline is up
- [ ] Overview: history ±2σ + forecast diamonds, flux bars, real Local
      Snapshot, tile-style Price Snapshot + VFM top 5, 24h-scoped alerts,
      3 bus progress bars when live
- [ ] 24H tab: peak-shaded chart, model performance, forecast trio, alert legend
- [ ] Compare tab: two-district live table
- [ ] Map tab: controls row, town-selector price trend, block transport profile
- [ ] Score Weights in a popover with retrain button
- [ ] Refresh stamp + history slider present
- [ ] App never throws with pipeline offline
