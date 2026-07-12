# v3 Mockup Fidelity + v1 Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `dashboard/app_v3.py` to visual fidelity with `desgin_ideas/sg_liveability_v3_mockup.html` and full feature parity with v1, per `docs/superpowers/specs/2026-07-12-v3-mockup-fidelity-design.md`.

**Architecture:** Extend the existing v3 pattern — Python assembles real data, renders HTML fragments via `st.markdown(..., unsafe_allow_html=True)` with inline-SVG charts; the only iframe left is the `sg_map.html` embed. Pure logic (weights, chart SVG, geojson injection) moves into small testable modules.

**Tech Stack:** Streamlit, FastAPI, SQLite (`storage.database`), DuckDB (`hdb.analytics`), OneMap (`hdb.onemap_services`), Ridge models (`ml.forecaster`, `ml.extended_forecaster`), pytest (new dev dep).

## Global Constraints (from spec §7)

- Never crash on missing data — try/except per card → `render_coming_soon(...)`.
- SVG only in content areas; no Plotly / Streamlit-native charts.
- Native widgets allowed: district/day/hour/town/flat-type selectors, history + months + weight + radius sliders, postal input, refresh/retrain/fetch buttons, compare pickers, tabs, popover.
- Every new element declares its own `color` — never rely on inheritance.
- Style tokens: `--bg #F3F6FA`, `--card #FFF`, `--border #E4E9F0`, `--border-strong #D3DBE5`, `--text #0F172A`, `--muted #6B7686`, `--blue #2F7DED`, `--teal #10B981`, `--amber #F5A524`, `--red #EF4444`; mono = `'JetBrains Mono', monospace`.
- SVG guard: any polyline with <2 distinct points → `render_coming_soon`.
- Verdicts: score ≥75 GOOD teal · 50–74 MODERATE amber · <50 POOR red.
- Test both themes (`--theme.base dark|light`) and both pipeline states per task.
- Run app: `.venv/Scripts/streamlit.exe run dashboard/app_v3.py --server.port 8502`.
- Tests: `.venv/Scripts/python.exe -m pytest tests/ -v` (pytest installed via `uv pip install pytest --python .venv/Scripts/python.exe`; add `pytest` to requirements.txt flagged as dev).
- Compile gate for every task: `.venv/Scripts/python.exe -m py_compile dashboard/app_v3.py api.py`.

---

### Task 0: Commit pending look-and-feel fixes (§1 checkpoint)

**Files:** already-modified working tree: `api.py`, `dashboard/app_v3.py`, `dashboard/sg_map.html`, `dashboard/app.py`, `dashboard/render.py`, new `dashboard/planning_areas.geojson`, `zzz_handoff/` move.

- [ ] Compile gate, then commit everything pending as
  `v3: theme fix, top map strip + float card, map API/CORS fixes (parity §1)`.

### Task 1: Test scaffold + `dashboard/scoring.py` (pure weight/verdict/alert logic)

**Files:** Create `dashboard/scoring.py`, `tests/test_scoring.py`; modify `requirements.txt`.

**Produces (used by Tasks 2, 4, 6, 7, 9, 12):**
- `DEFAULT_WEIGHTS = {"bus": 50, "stab": 60}` (bus share %, stability share % of the taxi term; taxi share = 100−bus, friction share = 100−stab). Defaults reproduce the canonical Bus×0.5 + Stab×0.3 − Fric×0.2.
- `apply_weights(components: dict, weights: dict) -> float | None` — components needs keys `bus_frequency_score` (0–100), `taxi_stability_score` (0–100), `friction_ratio` (0–1); returns clamped 0–100 score, `None` if any component missing.
- `verdict_for(score: float | None) -> tuple[str, str]` — ("GOOD", "#10B981") / ("MODERATE", "#F5A524") / ("POOR", "#EF4444") / ("OFFLINE", "#8B95A5") for None.
- `alert_kpi_color(n: int) -> str` — teal `#10B981` at 0, amber `#F5A524` 1–5, red `#EF4444` ≥6.
- `is_custom(weights) -> bool`.

- [ ] Install pytest, add `pytest` line to requirements.txt with `# dev/test only` comment.
- [ ] Write failing tests: default weights reproduce 0.5/0.3/0.2 (e.g. bus=80, stab=90, fric=0.5 → 80·0.5 + 90·0.3 − 50·0.2 = 57.0); clamping at 0 and 100; None on missing key; verdict boundaries 75/50; alert colors 0/1/5/6.
- [ ] Run tests → FAIL (module missing). Implement `dashboard/scoring.py`. Tests PASS. Commit `feat: scoring helpers for reactive weights (spec §2, §6b)`.

### Task 2: API — RankEntry components + shared weights

**Files:** Modify `api.py` (`RankEntry` at :82, `rank_districts` at :105).

**Produces:** `/rank` entries gain `bus_frequency_score: float`, `taxi_stability_score: float`, `friction_ratio: float` (defaults 0.0 so old clients unaffected). `rank_districts` copies them from `compute_metrics` result `m` (attributes confirmed at api.py:302-316).

- [ ] Add the three fields to `RankEntry` with `= 0.0` defaults; extend the `results.append({...})` dict in `rank_districts` with `m.bus_frequency_score`, `m.taxi_stability_score`, `m.friction_ratio`.
- [ ] Compile gate. With pipeline running, `curl http://127.0.0.1:8000/rank` shows new keys; offline, skip live check. Commit `feat(api): expose score components in /rank for client-side re-weighting`.

### Task 3: Map embed — inline geojson injection

**Files:** Create `dashboard/map_embed.py`, `tests/test_map_embed.py`; modify `dashboard/sg_map.html` (script top + `loadDistricts`), `dashboard/app_v3.py` (MAP_HTML load site).

**Produces:** `load_map_html(map_path: Path, geojson_path: Path) -> str | None` — reads sg_map.html, replaces the literal line `let INLINE_GEOJSON = null; /*__INLINE_GEOJSON__*/` with `let INLINE_GEOJSON = <file contents>;` when the geojson file exists; returns None if map file missing.

- [ ] Add to sg_map.html script (below `const API_BASE...`): `let INLINE_GEOJSON = null; /*__INLINE_GEOJSON__*/`.
- [ ] In `loadDistricts()` step 2, before the fetch: `const geojson = INLINE_GEOJSON || await (async () => { ...existing fetch/parse..., return parsed or null })();` — polygons draw from inline data even when the API is down; score colors still only from `/rank`.
- [ ] TDD `load_map_html` (placeholder replaced, geojson content present, None on missing map). app_v3.py uses it for `MAP_HTML`.
- [ ] Compile gate + tests + visual check (map shows 55 bordered polygons with `python main.py` stopped). Commit `feat: district polygons always visible via inline geojson`.

### Task 4: Chrome — controls row, scored selector labels, offline banner, refresh, spinner

**Files:** Modify `dashboard/app_v3.py` (selector block ~:700, `get_scope_snapshot` untouched).

**Produces:** `st.session_state` keys: `sel_day` (Mon..Sun), `sel_hour` (0–23), `history_min` (30–360). Selector row = `st.columns([3,1,1,1.4,1])`: district / day / hour / history slider / ↻ Refresh + `Last refresh HH:MM SGT` caption.

- [ ] District labels: from `call_rank_cached()` (inside `st.spinner("Scoring 55 districts…")`), build `label_with_score = f"{label} · {score:.0f}"` matching `r["district"].lower() == option label.lower()`; map selection back via index, not label text.
- [ ] Offline banner directly under topnav when `call_api("/health") is None`: full-width `.card`-style div, text `🔌 Live pipeline offline — showing stored data only. Run python main.py for live scores.` in `--muted`, amber-pale background.
- [ ] Float-card header becomes `{LABEL} · {DAY} {H}:00` and gains an `expected ~N taxis` `.fc-row` from `DayPatternAnalyser.get_pattern()` (day_name/hour/avg_count match), try/except → row shows `—`; skipped for `average` with caption.
- [ ] ALERTS KPI: value color via `alert_kpi_color(n)`; sub-label `last 24h` (count itself scoped in Task 8). Tooltips: add `title="…"` (v1 help texts) to every `.kpi-label` and `.mini-col-title`.
- [ ] Compile gate + visual check both pipeline states. Commit `feat(v3): control row, scored selector, offline banner, honest alert colors, tooltips`.

### Task 5: Score Weights popover — reactive, native controls

**Files:** Modify `dashboard/app_v3.py`: delete `JS_BLOCK` + `build_score_weights_widget` + the expander; add `render_formula_card(components, weights, score)` HTML builder; popover in right column of a `st.columns([5,1.2])` row above the tabs.

- [ ] Popover contents: preset `st.radio` (Bus-reliant 75/100 · Balanced 50/60 · Taxi-reliant 25/60 → sets sliders), `st.slider("🚌 Bus share %", 0, 100)` + `st.slider("Taxi stability share %", 0, 100)` bound to `st.session_state["weights"]`; static formula card (mockup `.formula` HTML with big-ring + Bus/Stability/Friction terms) computed from the **selected district's** components via `apply_weights`; `Reset to default` button; `🔁 Retrain model` button → `TaxiForecaster(district).train(lookback_min=1440)` in a spinner with result caption.
- [ ] Wire `apply_weights` into every score display: KPI CONNECTIVITY tile, float-card ring, `render_leaderboard` (re-score + re-sort entries that carry components; fall back to `r["score"]` otherwise), VFM (`get_value_for_money(..., transport_weight=w, price_weight=1−w)` when Task 13's slider exists — until then default). When `is_custom(weights)`: `CUSTOM WEIGHTS` chip (`.chip.mid`) beside KPI score and float-card verdict.
- [ ] Compile gate; visual: moving a slider changes KPI + ring + leaderboard order live. Commit `feat(v3): reactive score-weights popover re-scores whole page (spec §2)`.

### Task 6: `dashboard/v3_charts.py` — history ±2σ + prediction overlay, flux bars

**Files:** Create `dashboard/v3_charts.py`, `tests/test_v3_charts.py`; modify `dashboard/app_v3.py` `build_overview_html` (new full-width card above Transport Timeliness).

**Produces:**
- `render_history_chart(snaps: list[dict], preds: list[dict]) -> str` — 900×220 viewBox SVG: blue actual line from `taxi_count`, translucent `rgba(47,125,237,.12)` polygon band = rolling(5) mean ±2σ, right-edge future diamonds for latest +30/60/120 predictions (`#F5A524`/`#A855F7`/`#10B981`), **hollow diamonds** (fill white, colored stroke) for past predictions whose `created_at + horizon` lands inside the window — plotted at that time vs the actual line (rubric: predicted-vs-actual). 9px mono legend row below.
- `render_flux_chart(snaps: list[dict]) -> str` — 900×120 SVG bars, last 30 flux values, teal/red around a `--border-strong` zero line, caption `Positive = taxis arriving · Negative = taxis leaving`.
- Both return `""` sentinel when <2 distinct points; caller substitutes `render_coming_soon`.

- [ ] TDD: band polygon present with ≥2 points; `""` with 0/1 points; diamond count matches predictions in window; flux bar colors by sign.
- [ ] Overview card `📈 Taxi availability — history & forecast · {label}` uses `history_min` window: `fetch_snapshots(slug, minutes=history_min)`, `fetch_predictions(slug, limit=50)`. `average`: sum per-timestamp across districts if ≤ 60 timestamps, else coming-soon.
- [ ] Compile + tests + visual. Commit `feat(v3): taxi history ±2σ + predicted-vs-actual + flux SVG charts (parity 3.1, 3.2)`.

### Task 7: Overview — Local Snapshot card (real)

**Files:** Modify `dashboard/app_v3.py` (`build_overview_html` right column).

- [ ] Rows per mockup, each independently guarded: 🚇 nearest MRT via `get_nearest_mrt_summary(centroid_lat, centroid_lng)` (bbox centre; `average` → static citywide line `6 lines · 134 stations citywide`); 🚌 stops + `~{headway:.0f} min` from live `bus` dict, badge = bus score verdict; 🚕 live count + friction, badge = verdict color, peak chips row from `PeakHourPredictor.predict_peaks()` (`Good→.chip.ok ✓`, `Mod→.chip.mid ~`, else `.chip.bad ✗`); 🏢 CBD commute via `get_pt_commute_time(lat, lng)` (exists in `hdb/onemap_services.py`), `—` on failure.
- [ ] Compile + visual (token present and absent). Commit `feat(v3): real Local Snapshot card (MRT/bus/taxi/CBD rows)`.

### Task 8: Overview — Price Snapshot tiles + VFM top 5; alerts scoped 24h

**Files:** Modify `dashboard/app_v3.py` (`render_alerts`, `get_scope_snapshot` alert counting, Price Snapshot card).

- [ ] Price Snapshot: 3 `.price-tile`s (AVG / MEDIAN — needs `median_price` if present in `get_town_summary` df else omit tile / TXNS) for the matched town else citywide; `TOP 5 VALUE-FOR-MONEY` `vfm-list` rows from `get_value_for_money` (weights-aware).
- [ ] Alerts: filter `fetch_alerts(slug or None, limit=200)` rows to `triggered_at >= now−24h` (string compare on ISO works); render type chip (`LOW_TAXI→.chip.bad`, else `.chip.mid`), district, message, `HH:MM SGT`; cap 8 + `…and N more`; KPI + float-card counts use the same filtered count.
- [ ] Compile + visual. Commit `feat(v3): price snapshot tiles + VFM top5, alerts scoped to 24h (parity 3.3)`.

### Task 9: Transport Timeliness — 3 progress bars (parity 3.6)

**Files:** Modify `dashboard/app_v3.py` (`build_overview_html` timeliness card, live branch only).

- [ ] Under the mini-grid: 3 bars (Bus frequency / Taxi stability / Friction penalty = `friction_ratio*100`), track `--bg` border `--border`, fill `--blue`, 6px h / 3px r, label left, `NN/100 — verdict` right, all mono with explicit colors.
- [ ] Compile + visual live. Commit `feat(v3): bus connectivity score-breakdown bars (parity 3.6)`.

### Task 10: 24H Forecast tab — peak shading + right column

**Files:** Modify `dashboard/app_v3.py` (`build_forecast_html`, `render_24h_line_chart`).

- [ ] `render_24h_line_chart`: `--red-pale` rects behind 7–9am and 5–7pm x-ranges (computed from the prediction timestamps) + 9px `Peak` label; keep <2-point guard.
- [ ] After the existing cards, `grid-2`: left = Anomaly Alerts (same renderer) + static alert-type legend rows (LOW_TAXI / HIGH_FLUX / BUS_GAP one-liners from mockup) + existing peak boxes; right = **Model Performance** card — `fetch_latest_metrics()` row for district → MAE/RMSE stat-lines; fallback static v1 horizon table (3.08/3.92/5.03) with `Training accuracy · live eval daily 08:00 SGT` note; chip: MAE ≤3.5 `.chip.ok GREAT`, ≤4.5 `.chip.mid GOOD`, else `OK`; blue MAE explainer box; **Taxi Forecast trio** `fc-box` card from `data["forecast"]`.
- [ ] Compile + visual. Commit `feat(v3): 24H tab peak shading, model performance, forecast trio (parity 3.4, 3.8)`.

### Task 11: Compare tab

**Files:** Modify `dashboard/app_v3.py` (compare tab block).

- [ ] Two `st.selectbox`es (defaults Ang Mo Kio / Bishan, independent keys `cmp_a`, `cmp_b`); per side `call_api("/evaluate", bbox)` + `get_avg_price(slug)` + `get_nearest_mrt_summary(centroid)`; one `sg-table` with rows Connectivity (re-weighted via `apply_weights`), Bus Score, Taxi Stability, Friction, Avg Price, Nearest MRT — each cell `—` on missing data, score cells colored by `verdict_for`.
- [ ] Compile + visual both pipeline states. Commit `feat(v3): compare tab with live two-district table`.

### Task 12: Map & Housing tab — controls, town price trend, block transport profile

**Files:** Modify `dashboard/app_v3.py` (map tab block, `build_map_and_prices_html` signature gains `town`, `flat_type`, `months`, `weight`).

- [ ] Controls card: `st.selectbox("Flat type", get_flat_types())`, `st.slider("Months of data", 1, 24, 12)`, `st.slider("Transport importance %", 0, 100, 50)`; re-query `get_town_summary(flat_type, months)`; VFM via `get_value_for_money(summary, scores, transport_weight=w/100, price_weight=1−w/100)`.
- [ ] Price Trend: `st.selectbox("Town", get_available_towns())` → `get_price_trend(town, flat_type)`; re-render chart + 3 tiles (existing renderer).
- [ ] Block Transport Profile card: `st.text_input("Postal code")` + `st.slider("Search radius", 100, 1000, 500, step=100)` + `st.button("🔍 Fetch")` → `get_area_transport_profile(postal, radius_m, lta_api_key=cfg.lta_api_key)`; render address, nearest-MRT stat-line, up to 5 bus-stop stat-lines with services, CBD commute, nearby HDB avg price tile (town match from address), connectivity chip via `/evaluate` around the point (±0.005°). `error` key or exception → coming-soon.
- [ ] Compile + visual. Commit `feat(v3): map tab controls, town price trend, block transport profile (parity 3.9, 3.10)`.

### Task 13: Final sweep — definition of done

- [ ] Run full pytest suite; compile gate; app boots with pipeline OFF (zero exceptions, banners/fallbacks everywhere) and ON.
- [ ] Both themes launched via `--theme.base dark` / `light` — zero invisible text (expanders, popover, selectboxes, tables).
- [ ] Tick every Definition-of-done box in the spec; update `zzz_handoff/v3_parity_handoff.md` checklist marks ⬜→✅.
- [ ] Commit `docs: mark v3 parity checklist complete` and final summary to user.
