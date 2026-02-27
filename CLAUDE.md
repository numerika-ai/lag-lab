# Lag Lab — Project Context for Claude Code

## What this is
Cross-venue crypto price lag research project. We discover that Binance Futures BTC leads all markets, and other exchanges/pairs react with measurable delay (1s to 108s). This lag = tradeable edge.

## Task: Build Unified Dashboard Site
Create `index.html` — a single-page unified dashboard that combines ALL research into one cohesive site.

### Design
- Dark Bloomberg/cyberpunk theme (see docs/existing-report-reference.html for CSS)
- Monospace font (Consolas/Monaco)
- CSS variables: --bg-primary:#0a0a0f, --accent-cyan:#00ffff, --accent-green:#00ff88
- Chart.js for charts, pure CSS for layouts
- Single self-contained HTML file
- Responsive, mobile-friendly
- Animated counters, hover effects, professional quality

### Sections Required

1. **Hero/Header** — "Lag Lab: Cross-Venue Price Lag Research" with key stats (9 exchanges, 1046 tests, 28s champion lag)

2. **Action Plan Status** — Visual progress tracker showing 6 phases:
   - Phase 1: Fix & Validate ✅ IN PROGRESS (scanner v3 ready, validator running)
   - Phase 2: Exchange Expansion 🔄 IN PROGRESS (adding Phemex, Bitget, HTX)
   - Phase 5: Paper Trading Bot ⬜ PLANNED
   - Phase 3: DEX Integration ⬜ PLANNED
   - Phase 4: Alternative Signals ⬜ PLANNED
   - Phase 6: GH Pages Updates 🔄 CONTINUOUS
   Use progress bars or step indicators.

3. **Signal Propagation Chain** — Visual flow: Binance BTC (t=0) → Spot (+1s) → Gate.io BTC (+0s) → Alts (+6-33s) → Korean (+13-108s). CSS animated nodes with glow.

4. **Exchange Universe** — Chart.js horizontal bar chart of 9 exchanges (pair counts + overlap). Color-code by status (connected/discovered). Flags for Korean 🇰🇷.

5. **Top Verified Signals** — Table with color-coded rows:
   - WIF/Gate.io: 28s, 0.88 corr ✅ CONFIRMED
   - BONK/Gate.io: 33s, 0.82 ✅ CONFIRMED  
   - ADA/Gate.io: 6s, 0.71 ✅ CONFIRMED
   - FLOW/Upbit: 13s, 0.74 (Korean)
   - DOGE/Upbit: 28s, 0.73 (Korean)
   - MOODENG/Upbit: 108s, 0.74 (Korean)
   Include validation status badge per signal.

6. **Monte Carlo Simulation** — 5 scenario cards (Safe→Max Degen) with median, P5-P95 range, profit probability. Bar chart. Starting capital $10,000 (note: simulation was with $1K, scale applies).

7. **Scanner Status** — Live status panel:
   - Scanner v2: Running (PID info)
   - Scanner v3: Ready (9 exchanges)
   - Validator: Testing 20 pairs
   - Cron: Research thinking every 15 min
   Show connections per exchange.

8. **Research Insights** — Key findings cards:
   - "Less MM × less popular = more lag"
   - "120s correlation window = boundary artifacts"
   - "Korean exchanges show 13-108s extreme lag"
   - "aggTrades insufficient for low-cap pairs"

9. **Methodology** — Compact section: Spearman rank, multi-timeframe (30/60/120/300s), forward-fill, WebSocket bookTicker

10. **Activity Log** — Recent actions timeline (read from ACTIVITY-LOG.md context)

11. **Navigation Footer** — Links to: GitHub repo, existing reports on crypto-data-coverage

### Data files available in repo:
- results/wif_simulation.json — Monte Carlo results
- data/exchange_discovery.json — exchange pair counts
- results/lag_registry.db — SQLite with all test data (read schema from ACTION-PLAN.md)
- ACTION-PLAN.md — full plan with phases
- ACTIVITY-LOG.md — chronological action log
- docs/RESEARCH.md — full research document

### After building:
```bash
git add index.html
git commit -m "Unified Lag Lab dashboard — all research in one page"
git push origin main
```

Site will be live at: https://numerika-ai.github.io/lag-lab/
