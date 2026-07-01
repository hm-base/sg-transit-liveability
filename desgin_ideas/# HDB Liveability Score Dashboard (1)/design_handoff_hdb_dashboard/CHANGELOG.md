## Changelog — What's New Since First Handoff Package

### Screens Added
- **Glossary screen** — full plain-English explainer (score formula, taxi/bus metrics, anomaly alerts, data sources table)
- **Postal code search result** — 6-digit postal → taxis within radius + bus stops + live arrivals per stop (250m/500m/1km toggle)
- **Postal code sample data** — 5 working codes: 825234, 820413, 570033, 730207, 150033

### Overview Tab — Major Additions
- **Right panel** (224px) — Anomaly alerts + Model performance (+30/+60/+2hr with Great/Good/OK) + Forecasts (+30/+60/+120min taxi counts)
- **Transport Timeliness strip** — Bus (stops, frequency, score, redundancy) + Taxi (live count, flux badge, friction, mean window) combined in one row, Connectivity Score highlighted dark at end
- **District Leaderboard** — live bar chart sorted by score + verdict table (Well connected/Moderate/Poor)
- **Score breakdown** — now collapsible (collapsed by default, click "Formula ↓" to expand)

### Metrics Strip (Changed)
- Bus Headway → **Mean (window)** (60-min rolling avg, real value 156.5 from prototype)
- CBD Commute → **Alerts** (count, green when 0)
- Live Taxis now shows **flux badge** (+45 from prototype)
- New **Friction** tile (0.000–1.000 demand/supply ratio)
- Cards changed from dark (`#0f172a`) to **white with dark text** on dark navy strip

### 24H Forecast Tab (Replaced)
- Old: Mon/Tue/Wed bar chart (was broken/blank)
- New: **7-day × 24-hour heatmap** (green=plentiful, red=scarce) + Peak Hour Ratings + ML Forecast side by side

### Price Trends Tab (Added Real Data)
- **Price by town table** — 22 towns with real S$ avg/median/transactions from prototype screenshot
- **VFM Ranking** — top 10 towns with real VFM scores (Jurong West 75.0 → Marine Parade 66.3)
- **Price trend chart** — Marine Parade: S$615,333, +S$56,333 (+10.1%), 349 transactions

### Map
- Now **scrollable** — not sticky, map is above fold, user scrolls down to tab content
- **Tab bar is sticky** (position:sticky;top:0;z-index:15) — stays visible as user scrolls
- **5 map style options** — Voyager, Dark, Minimal, Street, Satellite (toggle pills on map)
- Hover over district marker → floating card previews that district instantly
- **District dropdown** in nav — jump to any of 18 districts
- **Day + Time dropdowns** — proper dropdowns replacing cycle buttons

### Deep Dive Screen (Fixed)
- Was blank — fixed dark background and invisible text
- Transport/24H/Price/Compare sub-tabs all working
- Dark header, light content cards

### Compare Tab (Fixed)
- Was blank — fixed invisible white text on light background
- Grid borders changed from dark to light

### Navigation
- **Glossary** link added to tab bar
- Separate Day picker + Time picker dropdowns (Mon–Fri, 7:30am–7pm)

### Real Data Wired In (from prototype screenshot Jun 26 2026)
- Starting district: Ang Mo Kio (not Punggol)
- Live taxis: 184 (not 14)
- Mean window: 156.5, Friction: 0.000, Flux: +45
- All 22 town prices from screenshot
- VFM ranking from screenshot

### Score Formula
Bus×(busW%) + Taxi×(taxiW%) − Friction×(frW%)
Default: Bus 50%, Taxi 30%, Friction 20%
Score colours: ≥80 #22c55e, 65–79 #f59e0b, <65 #ef4444
Time-of-day multipliers: 7:30am×1.0, 8:30am×0.82, 12pm×1.15, 5pm×0.94, 7pm×0.87

### Still To Do (Next Session)
- Wireframe: Frame G (onboarding splash) + Block Transport Profile frame
- Hi-fi: prominent alert banner when anomaly active (big coloured banner)
- Hi-fi: card layout reference page (all card variations side by side)
