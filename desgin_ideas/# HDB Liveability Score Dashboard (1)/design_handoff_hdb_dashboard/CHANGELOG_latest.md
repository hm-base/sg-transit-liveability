## Changelog — Latest Session (Jun 27 2026)

### Layout Changes
- **Transport Timeliness** moved to TOP of Overview tab (first card below metrics strip)
- Removed duplicate Transport Timeliness block
- **Leaderboard + Price Snapshot** now side-by-side in bottom row of Overview

### Score Card
- Removed formula equation boxes (bus/taxi/friction tiles) — decluttered
- Score card now shows ring + label only; formula accessible via Score Weights tab
- "Formula ↓" expand button removed

### Transport Timeliness Strip
- Connectivity score column now uses pastel tint + coloured border matching overall theme
- Score ring centred between Bus and Taxi sections

### Peak Hour Pills
- Moved into Taxi Availability card (right panel)
- Sun 🌤 grouping: 7am 8am 9am — Moon 🌙 grouping: 5pm 6pm 7pm
- Copy: "Past 24 hours availability"

### Forecast Tab (24H)
- Replaced old bar chart with full 7×24 heatmap (green=plentiful, red=scarce)
- Peak Hour Ratings + Taxi Forecast cards side by side below heatmap
- Anomaly alert chip moved into Forecast tab

### Formula Numbers
- Fixed: busComp + taxiComp − frComp now always equals selScore exactly
- Removed duplicate const declarations that caused eval errors

### Price Data
- PRICE_DATA and VFM_DATA moved to top of class (were unreachable before)
- Price Trends tab now loads correctly with all 22 towns
- Price Snapshot on Overview shows avg/median/txn for selected district + top 5 VFM

### Misc
- "Stops" label → "Stops in zone" with "bus stops" subtext
- Floating district card on map: reverted to white bg + sky-blue border (as wireframe)
- ML label removed from Taxi Forecast card
- Cards tab z-index raised to 1000 (was being clipped)
