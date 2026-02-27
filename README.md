# 🔬 Lag Lab — Cross-Venue Crypto Price Lag Research

**Live Dashboard:** [numerika-ai.github.io/crypto-data-coverage](https://numerika-ai.github.io/crypto-data-coverage/)

---

## What is this?

Binance Futures BTC is the fastest crypto market in the world. Every other exchange and asset reacts with a measurable delay — from 1 second (Binance Spot) to **108 seconds** (Korean exchanges). This lag creates a tradeable edge.

**We're building tools to find, validate, and exploit these lags.**

## 🏆 Champion Signal

| Pair | Exchange | Lag | Correlation | Type |
|------|----------|-----|-------------|------|
| **WIF/USDT** | Gate.io Futures | **28s** | **0.88** | Pure exchange lag |
| BONK/USDT | Gate.io Futures | 33s | 0.82 | Exchange + asset lag |
| ADA/USDT | Gate.io Futures | 6s | 0.71 | Exchange lag |
| FLOW/USDT | Upbit 🇰🇷 | 13s | 0.74 | Korean isolation |

## 📡 Signal Propagation Chain

```
Binance Futures BTC (t=0, master clock)
    │
    ├──→ Binance Spot BTC (+1s, corr 0.62)
    ├──→ Gate.io Futures BTC (+0s, MM synced)
    │     ├──→ Gate.io ADA (+6s, corr 0.71)
    │     ├──→ Gate.io WIF (+28s, corr 0.88) 🏆
    │     └──→ Gate.io BONK (+33s, corr 0.82)
    ├──→ Upbit 🇰🇷 FLOW (+13s, corr 0.74)
    └──→ Upbit 🇰🇷 MOODENG (+108s, corr 0.74)
```

**Rule:** Less market makers × less popular coin = more lag.

## 🌐 Exchange Universe (9 discovered)

| Exchange | Pairs | Overlap w/ Binance | Status | Region |
|----------|-------|--------------------|--------|--------|
| Binance | 553 | — (master) | ✅ Connected | Global |
| MEXC | 746 | 511 | ✅ Connected | Global |
| Gate.io | 642 | 510 | ✅ Connected | Global |
| Bybit | 552 | 476 | ✅ Connected | Global |
| Bitget | 536 | 477 | 🔍 Discovered | Global |
| Phemex | 508 | 477 | 🔍 Discovered | Global |
| Bithumb 🇰🇷 | 451 | 318 | ✅ Connected | Korea |
| Upbit 🇰🇷 | 242 | 193 | ✅ Connected | Korea |
| HTX | 206 | 188 | 🔍 Discovered | China |

## 💰 Monte Carlo Simulation (WIF, 50x leverage, $1K, 30 days)

| Scenario | Median Return | P5-P95 Range | Profit Prob | Bust Rate |
|----------|--------------|--------------|-------------|-----------|
| 🟢 Safe (10x eff.) | $1,866 | $1,694 — $2,055 | 100% | 0% |
| 🟡 Moderate (50x×50%) | $4,855 | $4,061 — $5,693 | 100% | 0% |
| 🟠 Aggressive (50x×100%) | $8,707 | $7,105 — $10,402 | 100% | 0% |
| 🔴 YOLO ($500 margin) | $35,445 | $26,893 — $43,995 | 97.8% | 0% |
| 💀 Max Degen (full 50x) | $52,963 | $380 — $74,685 | 59.3% | 0% |

## 📊 Reports (GitHub Pages)

- [Overnight Discovery Report](https://numerika-ai.github.io/crypto-data-coverage/overnight-discovery-report.html) — 9 exchanges, Korean analysis, Monte Carlo
- [Initial Research Report](https://numerika-ai.github.io/crypto-data-coverage/cross-venue-lag-report.html) — methodology, signal chain, test results
- [Lead-Lag Dashboard](https://numerika-ai.github.io/crypto-data-coverage/lead-lag-dashboard.html) — correlation heatmap, network diagram
- [Data Coverage Gantt](https://numerika-ai.github.io/crypto-data-coverage/index.html) — 36 datasets, 9.7M rows

## 🗂️ Repository Structure

```
lag-lab/
├── README.md                    ← you are here
├── ACTION-PLAN.md               ← execution roadmap (6 phases)
├── ACTIVITY-LOG.md              ← all actions, linked to cron jobs
├── docs/
│   ├── RESEARCH.md              ← full research document
│   ├── RESEARCH-IDEAS.md        ← ideas from thinking crons
│   └── METHODOLOGY.md           ← how we measure lag
├── results/
│   ├── lag_registry.db          ← master SQLite (all tests)
│   ├── validation_results.json  ← focused validator output
│   └── wif_simulation.json      ← Monte Carlo results
├── scripts/
│   ├── overnight_discovery_v3.py ← multi-exchange scanner
│   ├── lag_validator.py          ← focused pair validator
│   └── wif_sim_realistic.py      ← Monte Carlo simulator
└── data/
    └── exchange_discovery.json   ← exchange pair counts
```

## 🔄 Action Plan Status

| Phase | Description | Status | ETA |
|-------|-------------|--------|-----|
| 1 | Fix scanner + validate top 20 | 🔄 In Progress | Today |
| 2 | Add Phemex, Bitget, HTX + regional | ⬜ Next | Weekend |
| 5 | Paper trading bot ($10K, auto risk) | ⬜ Planned | Next week |
| 3 | DEX integration (Hyperliquid, dYdX) | ⬜ Planned | Next week |
| 4 | Alternative signals (funding, basis) | ⬜ Planned | Next week |
| 6 | GH Pages comprehensive update | 🔄 Continuous | Per phase |

## 🤖 Automated Research

A cron job runs every 15 minutes, generating new research ideas:
- New exchanges to test
- DeFi/DEX lag opportunities  
- Regional exchange analysis
- Alternative signal types (funding rates, basis trading, liquidation cascades)

## 📐 Methodology

- **Data:** WebSocket bookTicker (best bid/ask) → mid_price → 1s returns
- **Correlation:** Spearman rank (robust to outliers)
- **Lag window:** ±300s, multi-timeframe (30s, 60s, 120s, 300s)
- **Minimum:** 20+ common seconds, forward-fill for low-liquidity pairs
- **Confidence:** Cross-window agreement scoring

## 🛡️ Infrastructure

| Machine | Role | GPU |
|---------|------|-----|
| Tank (AMD Ryzen 9 7900X) | Gateway, scanners, analysis | RTX 3090 24GB |
| Spark (NVIDIA Grace) | Training, collectors | GB10 Blackwell 128GB |

---

*Research by [Numerika AI](https://numerika.ai) — Wiktoria Sterling (Wiki)*  
*Data: Binance, Gate.io, Bybit, MEXC, Upbit, Bithumb + 3 more*  
*Last updated: 2026-02-27*
