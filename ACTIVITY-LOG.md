# 📋 Activity Log — Lag Lab

*Chronological log of all actions, discoveries, and cron outputs.*

---

## 2026-02-27

### 07:40 UTC — Action Plan Created & Approved
- **ACTION-PLAN.md** created with 6 phases
- Bartosz approved: $10K capital, auto risk management, max leverage
- Priority: Phase 1→2→5→3→4

### 07:48 UTC — Phase 1 Started (Fix & Validate)
- **Scanner v3** created (`overnight_discovery_v3.py`, 975 lines)
  - Fix: correlation window 120s→300s
  - Multi-timeframe: 30s, 60s, 120s, 300s sub-windows
  - Boundary artifact filter: |lag| < 0.9 × window_size
  - Binance WS stability: manual ping/pong, exponential backoff
- **Lag validator** created (`lag_validator.py`)
  - Sequential testing of 20 candidates, 180s per pair
  - Bug found: required consecutive-second ticks (impossible for low-cap)
  - Fix: forward-fill to continuous 1s series, lowered thresholds
  - Restarted PID 342153, running until ~09:05 UTC

### 07:50 UTC — Master Database Created
- **lag_registry.db** (SQLite): 1046 lag tests, 9 exchanges, 5 simulations
- Tables: `lag_tests`, `exchanges`, `simulations`, `paper_trades`
- Imported from: bonk_vs_bonk, live WS tests, historical aggTrades, overnight scanner, Monte Carlo

### 07:35 UTC — Overnight Discovery Report Published
- **URL:** https://numerika-ai.github.io/crypto-data-coverage/overnight-discovery-report.html
- 35KB, dark Bloomberg theme, Chart.js
- Sections: exchange universe, signal chain, top lags, Korean analysis, Monte Carlo, roadmap

### 06:54 UTC — Scanner v2 Restarted
- PID 325985, running until 18:00 UTC
- 6 exchanges: Binance, Gate.io, Bybit, MEXC, Upbit, Bithumb
- 10 scans completed (7 overnight + 3 post-restart)
- Finding: ALL results at ±120s boundary = window artifacts → led to v3 fix

### 00:25-01:26 UTC — Original Overnight Scan
- 7 scans, 905 pair-exchange combos
- Reconnect bug at hourly re-discovery → fixed

---

## 2026-02-26

### 23:30-23:50 UTC — Live WebSocket Tests
- WIF/Gate.io: **28s lag, 0.88 correlation** → CHAMPION ✅
- BONK/Gate.io: 33-35s lag, 0.58-0.82 correlation ✅
- ADA/Gate.io: 6s lag, 0.71 correlation ✅
- BTC Gate.io: 0s (MM synced) ✅
- DOGE Gate.io: 0-3s (MM synced) ✅

### 22:00-23:50 UTC — Full Research Session
- Exchange discovery: 9 exchanges, pair overlap analysis
- Signal propagation chain mapped
- Gate.io API: WIF max leverage 50x, taker 0.075%, maker -0.005%
- Monte Carlo: 5000 sims, 5 scenarios, $1K starting capital
- Research document: CROSS-VENUE-LAG-RESEARCH.md (245 lines)

---

## Cron Jobs Active

| Job | Frequency | Purpose | Status |
|-----|-----------|---------|--------|
| `lag-research-think` | 15 min | Creative thinking: new exchanges, strategies, ideas | ✅ Running |
| `collector-health-check` | 1h | Verify Spark collectors + Tank Docker | ✅ Running |
| `spark-training-monitor` | 2h | Check training processes + DuckDB | ✅ Running |

---

*Auto-updated by Wiki after each action*
