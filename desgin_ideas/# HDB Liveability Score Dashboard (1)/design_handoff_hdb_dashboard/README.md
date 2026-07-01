# Handoff: HDB Liveability Score Dashboard

## Overview
A real-time Singapore HDB resale liveability dashboard that helps users decide whether a non-MRT district is worth moving into. It analyses live LTA taxi data, bus arrival data, and HDB resale prices to give each district a connectivity score (0–100). Users can tune score weights, search by postal code, view deep-dive transport metrics, and compare districts.

## About the Design Files
The files in this bundle (`HDB Liveability Dashboard.dc.html`) are **high-fidelity HTML design prototypes** — not production code. They show the intended look, layout, interactions, and data structure. Your task is to **recreate these designs inside the existing Streamlit prototype** (`kws7frp2-8501.asse.devtunnels.ms`) OR extract specific components/pages into the framework of your choice (React recommended for interactivity).

The existing working prototype already has the real data pipeline (LTA DataMall, DuckDB, sklearn ML). The design prototype replaces its UI with a polished, interactive frontend.

## Fidelity
**High-fidelity.** All colours, typography, spacing, card layouts, and interactions are final. Recreate pixel-accurately using the design token values listed below.

---

## Screens / Views

### 1. Onboarding Screen
**Purpose:** First-time landing page. Explains the app and gets users to "Start Exploring".

**Layout:** Full-viewport dark screen, vertically centred, max-width ~740px centred.
- Logo block (76×76px, sky-blue gradient, rounded 22px)
- Title: "SG Liveability Index" — 34px bold
- Subtitle: 2-line description — 13px, muted white
- 3 step cards in a row (gap 20px, each flex:1) with numbered blue boxes
- CTA button: "Start Exploring Singapore →" — pill shape, sky-blue gradient

**Colours:** Background `#080e1c` → `#0f172a` gradient. Cards `rgba(255,255,255,.03)` with `rgba(255,255,255,.08)` border.

---

### 2. Main Dashboard — Map Hero + Nav
**Purpose:** Primary screen. Real-time Leaflet map of Singapore with district connectivity markers, live metrics strip, tab navigation.

#### Top Nav Bar (height: 52px, bg: `#0f172a`)
- Logo (30×30px sky-blue rounded)
- Search bar (max-width 280px) — accepts district name OR 6-digit postal code
  - On 6-digit postal: shows Postal Result screen
  - On district name: shows Deep Dive screen
- District dropdown pill — lists all 18 districts with live scores
- Day picker dropdown — Mon/Tue/Wed/Thu/Fri
- Time picker dropdown — 7:30am / 8:30am / 12pm / 5pm / 7pm
- "Glossary" link → opens Glossary screen
- "Score Weights" link → opens Formula Modal overlay

#### Map Hero (height: ~52% of viewport, bg: `#cfdfe8`)
- **Leaflet map** centred on Singapore [1.352, 103.82], zoom 12
- Tile options (switcher pills bottom-left, z-index 1000):
  - Voyager: `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png`
  - Dark: `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`
  - Minimal: `https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png`
  - Street: `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`
  - Satellite: Esri World Imagery
- **District markers**: white card div-icons (district name + score number coloured by grade)
  - Green `#22c55e` = score ≥ 80
  - Amber `#f59e0b` = 65–79
  - Red `#ef4444` = < 65
  - Active district: thicker border, shadow glow, scale up
- **Hover**: marker hover → floating score card (right side, 210px wide) updates instantly
- **Floating score card** (position:absolute right:14 top:14):
  - Shows: district name, score ring, taxis nearby, bus stops, MRT distance, bus service pills
  - "Explore → " CTA navigates to Deep Dive
- **Live indicator** bottom-left: "Live · Updates every 30s"
- **Legend** bottom: Good ≥80, Moderate 65–79, Poor <65

#### Metrics Strip (bg: `#111927`, 6 cards)
| Card | Value | Source |
|------|-------|--------|
| Live Taxis | Real count + flux badge | LTA DataMall |
| Mean (window) | 60-min rolling avg | Computed |
| Connectivity Score | 0–100, colour-coded | Formula |
| Friction | 0.000–1.000 | demand/supply |
| Avg Price | From HDB data | data.gov.sg |
| Alerts | Count, 0 = all clear | Anomaly detection |

All metric cards: bg `#0f172a`, border `#1e293b`, radius 9px, padding 8px 12px.

#### Tab Bar (bg: `#fff`, border-bottom `#e2e8f0`)
Tabs: **Overview** | **24H Forecast** | **Price Trends** | **Compare** | Glossary | Score Weights

---

### 3. Overview Tab
**Layout:** flex column, gap 14px, bg `#f0f4f7`, padding 18px.

**Row 1:** `display:flex gap:14px`
- **Left main** (flex:1, flex row, gap:14px):
  - Score breakdown card (flex:1.2): formula ring + component boxes + progress bars + peak hour pills
  - Transport stack (flex:1): 4 transport cards (MRT, Bus, Taxi, CBD) + compact price card at bottom
- **Right panel** (width:224px, flex column, gap:12px):
  - Anomaly alerts card: green "No alerts" or coloured alert list
  - Model performance card: +30min/+60min/+2hr with Great/Good/OK ratings + MAE values
  - Forecasts card: +30/+60/+120min taxi count predictions in 3 boxes

**Row 2:** Bus Connectivity bar (full width):
- 5 KPIs inline: Bus Stops | Avg Bus Frequency (with emoji) | Bus Score | Route Redundancy | Connectivity Score

**Row 3:** District Leaderboard:
- Bar chart (height 80px, all districts sorted by score, active district highlighted)
- Verdict table: District | Score | Verdict (Well connected / Moderate / Poor)

---

### 4. 24H Forecast Tab
**Layout:** padding 18px, single card.
- Day picker: Mon / Tue / Wed pills
- Bar chart (height 120px, 24 bars): colour by severity (low=dark blue, moderate=amber, peak=red)
- Time axis labels
- Peak Hour Ratings: 5 time slots with colour-coded badge
- ML Taxi Forecast row: +30min, +60min, +120min count boxes + alert banner if BUS_GAP

---

### 5. Price Trends Tab
**Layout:** 3 stacked cards, padding 18px.

**Card 1 — Price by town table:**
Columns: Town | Avg Price | Median Price | Transactions
Real data (22 towns, sorted by price desc):
- Central Area: S$1,091,709 / S$1,194,444 / 72 txn
- Queenstown: S$1,003,366 / S$1,000,000 / 255 txn
- … (see PRICE_DATA in the DC file)

**Card 2 — VFM Ranking:**
Columns: Town | Avg Price | VFM Score | Verdict
Top 10 from real data (Jurong West 75.0 → Marine Parade 66.3).

**Card 3 — Price trend chart:**
- Marine Parade 4-ROOM monthly: S$615,333 latest, +S$56,333 (+10.1%), 349 transactions
- SVG line chart 2017–2026 with forecast dotted line

---

### 6. Compare Tab
**Layout:** single grid table comparing 3 districts side by side.
Rows: MRT Distance | Bus Headway | CBD Commute | Avg HDB Price | Value Score
Active district highlighted with blue tint column.

---

### 7. Deep Dive Screen
Triggered by clicking "Explore →" on map card or searching a district.
- Header: score ring + district name + gradient progress bar + value score
- Sub-tabs: Transport | 24H Forecast | Price History | Compare
- Transport tab: 3 metric cards (Bus, Taxi, MRT) + weekly heatmap (7×5 grid) + Block-Level Lookup panel

---

### 8. Postal Code Search Result Screen
Triggered when user types a 6-digit postal code in search + Enter.
- Header: postal code + resolved address + block
- Radius selector: 250m / 500m / 1km (toggle pills)
- **Big stats row** (3 cards): Live taxis count (green) | Bus stops count (blue) | District name + Deep Dive CTA
- **Bus arrivals list**: per stop, per service → 2 arrival times with colour-coded timing badges
  - Green ≤5min, Amber ≤10min, Grey >10min
- Hint: "Try these sample postal codes" pills: 825234, 820413, 570033, 730207, 150033

**Sample postal data structure:**
```js
{
  '825234': {
    block: 'Blk 234E Punggol Way', unit: '#10-234', district: 'Punggol',
    stops: [
      { id:'65189', name:'Punggol Rd (Opp Blk 267A)',
        services: [{no:'84',e1:4,e2:14},{no:'85',e1:9,e2:22},{no:'386E',e1:2,e2:17}] },
      { id:'65191', name:'Punggol Rd (Blk 270A)',
        services: [{no:'84',e1:6,e2:18},{no:'85',e1:11,e2:24}] }
    ],
    taxis: {250:3, 500:8, 1000:14},
    sc: {250:2, 500:5, 1000:9}
  }
}
```

---

### 9. Formula / Score Weights Modal
Overlay (520px wide, centred).
- Live formula display: score ring + component boxes (Bus, Taxi, Friction)
- Preset buttons: Commuter (Bus 60%, Taxi 30%) | Budget Buyer | Balanced (50/30/20)
- 3 range sliders (auto-rebalance to 100% total): Bus %, Taxi %, Friction %
- "Apply & Recalculate" CTA

**Formula:** `Score = Bus×(busW/100) + Taxi×(taxiW/100) − Friction×(frW/100)`

---

### 10. Glossary Screen
Full-page overlay triggered by "Glossary" in tab bar.
Sections (white cards, stacked):
1. What is this app?
2. Score formula + rating table (75–100 Well connected, 50–74 Moderate, 0–49 Poor)
3. Taxi metrics: Live Taxis, Taxi Flux, Friction Index with table
4. Bus metrics: Bus Frequency Score with headway table
5. Anomaly Alerts: LOW_TAX, HIGH_FLUX, BUS_GAP explanations
6. Data sources table: Taxi (60s), Bus arrivals (3min), Bus stops (startup), ML (30min)

---

## Score Formula & Weights

```
ConnectivityScore = (busFreqScore × busW%) + (taxiScore × taxiW%) − (frictionScore × frW%)
```

Default weights: Bus 50%, Taxi 30%, Friction 20%.

Per-district score modifiers by time of day:
- 7:30am: ×1.0 (baseline)
- 8:30am: ×0.82 (peak penalty)
- 12pm:   ×1.15 (off-peak bonus)
- 5pm:    ×0.94
- 7pm:    ×0.87

Score colouring:
- ≥ 80: `#22c55e` (Good)
- 65–79: `#f59e0b` (Moderate)
- < 65: `#ef4444` (Poor)

---

## District Data (18 districts)

| District | Base Score | Coords [lat, lng] |
|----------|-----------|-------------------|
| Woodlands | 65 | [1.437, 103.786] |
| Yishun | 71 | [1.429, 103.835] |
| Ang Mo Kio | 78 | [1.370, 103.849] |
| Sengkang | 74 | [1.392, 103.895] |
| Punggol | 72 | [1.405, 103.909] |
| Pasir Ris | 68 | [1.372, 103.949] |
| Jurong East | 79 | [1.333, 103.742] |
| Bishan | 88 | [1.351, 103.848] |
| Toa Payoh | 80 | [1.332, 103.847] |
| Tampines | 82 | [1.354, 103.944] |
| Bedok | 77 | [1.324, 103.930] |
| Marine Pde | 51 | [1.302, 103.906] |
| Jurong West | 71 | [1.340, 103.706] |
| Queenstown | 85 | [1.295, 103.806] |
| CBD | 94 | [1.287, 103.852] |
| Geylang | 63 | [1.318, 103.872] |
| Bedok South | 70 | [1.315, 103.932] |
| Kallang | 76 | [1.311, 103.862] |

Real live data from prototype (Ang Mo Kio, Jun 26 2026):
- Live taxis: 184, Mean window: 156.5, Friction: 0.000, Flux: +45
- Leaderboard: Marine Parade 72, Tengah 47, Downtown/CBD 33

---

## API Endpoints (existing prototype backend)

| Endpoint | Returns |
|----------|---------|
| GET /health | `{"status":"ok","snapshots":>0}` |
| GET /evaluate?bbox=... | Connectivity score 0–100 for a bbox |
| GET /rank | All districts sorted by score |
| GET /predictions/{district} | +30/+60/+120min taxi forecasts |
| GET /alerts | Anomaly alert list |
| GET /forecast/24h/{district} | 24 hourly predictions |
| GET /forecast/peaks/{district} | Peak hour ratings |
| GET /forecast/pattern/{district} | 7×24 heatmap data |
| GET /forecast/price/{TOWN} | 6-month price forecast |

**Wire these endpoints into the design** by replacing the simulated values in the DC with real API responses. The DC currently uses polling every 2.5s for taxi count — replace with the real /evaluate endpoint polling every 60s.

---

## Design Tokens

### Colours
```
Background:        #080e1c
Surface dark:      #0f172a
Surface mid:       #111927
Border dark:       #1e293b
Border accent:     #1a2e42

Surface light:     #f0f4f7
Card white:        #ffffff
Border light:      #e2e8f0
Muted bg:          #f8fafc

Sky blue (primary):  #0ea5e9
Sky blue light:      #38bdf8

Green (good):      #22c55e
Amber (moderate):  #f59e0b
Red (poor):        #ef4444
Purple (MRT):      #a855f7
Orange (bus line): #f97316

Text primary (dark bg):   #f8fafc
Text secondary (dark bg): rgba(255,255,255,0.45)
Text muted (dark bg):     #3d5166

Text primary (light bg):  #1e293b
Text secondary (light bg):#64748b
Text muted (light bg):    #94a3b8
```

### Typography
```
Font family: 'Space Mono', monospace (Google Fonts)
Load: https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700

Sizes used:
  7px  — uppercase labels, legends
  8px  — body/subtext
  9px  — ui labels, table cells
  10px — nav items
  11px — card titles
  12px — section headings
  13px — nav title
  14px — page headings
  16px — large labels
  18px — score ring numbers
  20px — score breakdown ring
  22px — KPI values
  26px — bus KPI numbers
  30px — price headline
  34px — onboarding title
  48px — postal result big stat
```

### Spacing
```
Nav height:     52px
Map hero:       ~52% viewport height
Metrics strip:  ~90px
Tab bar:        40px
Content pad:    18px
Card radius:    12px (large), 10px (medium), 9px (small), 7-8px (micro)
Gap standard:   14px (between cards), 10px (between items), 8px (tight)
```

### Shadows & Borders
```
Floating card:  0 12px 40px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.05)
Score ring glow: 0 0 16px {colour}44
Active marker:  0 4px 20px {colour}55
```

---

## Interactions & Behaviour

### Map
- District marker hover → floating card previews that district (no click required)
- District marker click → locks selection, updates all tabs and metrics
- Hover out → card reverts to selected district
- Map style switcher (Voyager/Dark/Minimal/Street/Satellite) — live tile swap

### Time/Day pickers
- Dropdown selects change ALL district scores simultaneously (time-of-day multipliers apply)
- Scores update markers on map in real time

### Score Weights
- 3 sliders auto-rebalance: adjusting one redistributes remainder to others proportionally
- Formula ring and component boxes update live as sliders move
- Preset buttons snap to predefined weight combinations

### Postal code search
- Detect 6-digit number in search → show Postal Result screen
- Detect district name → show Deep Dive screen
- Radius toggle (250m/500m/1km) → re-filters stops and taxi count without re-fetching

### Live taxis
- Poll LTA DataMall every 60s (prototype uses 2.5s simulation)
- Flux badge = current − previous count
- Mean window = 60-min rolling average

---

## State Management

```js
state = {
  screen: 'onboarding' | 'dashboard' | 'deepdive' | 'postalresult' | 'glossary',
  district: string,           // selected district name
  hoverD: string | null,      // hovered district (map)
  dayIdx: 0–4,                // Mon–Fri
  timeIdx: 0–4,               // 7:30am–7pm
  busW: 10–80,                // bus weight %
  taxiW: 5–70,                // taxi weight %
  frW: 5–60,                  // friction weight %
  preset: 'commuter'|'budget'|'default'|'custom',
  liveTaxis: number,          // from LTA API
  tab: 'overview'|'forecast'|'price'|'compare',
  showFormula: boolean,
  ddTab: 'transport'|'24h'|'price'|'compare',
  fcDayIdx: 0–2,
  searchQ: string,
  radius: 250|500|1000,
  postalResult: object | null,
  postalQ: string,
  showDayPicker: boolean,
  showTimePicker: boolean,
  showDistrictPicker: boolean,
  mapStyle: 'voyager'|'dark'|'light'|'street'|'satellite',
  tick: number,               // increments every poll cycle
}
```

---

## Files in This Bundle

| File | Description |
|------|-------------|
| `HDB Liveability Dashboard.dc.html` | Full hi-fi interactive prototype (all screens, all interactions) |
| `HDB Liveability Wireframes.dc.html` | Original wireframes (reference for layout intent) |

Open `HDB Liveability Dashboard.dc.html` directly in a browser to see the full interactive prototype. No build step required.

---

## Notes for Claude Code

1. **Start Exploring button** → transitions to dashboard screen
2. **Real API integration**: Replace all simulated data with live calls to the existing backend endpoints listed above. The backend already produces all the data this UI needs.
3. **Leaflet map**: Already wired in the prototype using CDN. In production use the same Leaflet + CartoDB tiles.
4. **Postal code lookup**: In prototype uses hardcoded sample data. Wire to OneMap geocode → LTA BusArrivalv2 + taxi bbox query.
5. **District leaderboard**: In prototype computed from base scores. Wire to GET /rank.
6. **Forecasts panel**: Currently shows static +30/+60/+120 values. Wire to GET /predictions/{district}.
7. **Anomaly alerts**: Currently always "No alerts". Wire to GET /alerts, poll every 60s.
8. **Score weights**: The formula is the same as the backend — keep frontend and backend in sync.
