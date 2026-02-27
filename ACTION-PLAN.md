# 🎯 Cross-Venue Lag — Action Plan

*Created: 2026-02-27 07:40 UTC by Wiki*  
*Status: ✅ APPROVED by Bartosz — 2026-02-27 07:44 UTC*  
*Capital: $10,000 | Risk: Auto-optimize (Kelly/correlation-based) | Leverage: max available*

---

## Executive Summary

Mamy potwierdzonego championa: **WIF/Gate.io 28s lag, 0.88 corr**. Overnight scanner przeskanował 961 par na 6 giełdach, ale znalazł głównie artefakty okna (±120s). Potrzebujemy teraz **precyzyjnej walidacji** top kandydatów i **rozszerzenia** na nowe giełdy/DEXy.

---

## Phase 1: Fix & Validate (MOGĘ ZROBIĆ SAMA — 2-4h)

### 1.1 Scanner v3 — Fix Correlation Window
**Problem:** 120s okno = boundary artifacts (ALL 961 results at ±120s)  
**Fix:** Zwiększ okno do 300-600s, dodaj weighted correlation (bliższe ticki ważniejsze)  
**Output:** Nowy `overnight_discovery_v3.py` z lepszą metodyką

### 1.2 Focused Lag Validator — Top 20 Candidates
**Co:** Dedykowany skrypt do precyzyjnego pomiaru lagu na wybranych parach  
**Jak:** 5-min live WebSocket test per para (jak lag_test_v2 ale automatyczny batch)  
**Kandydaci:**
| # | Para | Giełda | Wstępny lag | Źródło |
|---|------|--------|-------------|--------|
| 1 | WIF | Gate.io | 28s | ✅ POTWIERDZONE |
| 2 | BONK | Gate.io | 33s | ✅ POTWIERDZONE |
| 3 | ESP | Bybit | 37s | overnight scan |
| 4 | SKY | Gate.io | 21s | overnight scan |
| 5 | MUBARAK | Gate.io | 24s | overnight scan |
| 6 | ADA | Gate.io | 6s | historical test |
| 7 | FLOW | Upbit 🇰🇷 | 13s | overnight scan |
| 8 | DOGE | Upbit 🇰🇷 | 28s | overnight scan |
| 9 | MOODENG | Upbit 🇰🇷 | 108s | overnight scan |
| 10 | CVX | Gate.io | 40s | overnight scan |
| 11 | GOAT | Gate.io | 49s | overnight scan |
| 12 | CYBER | Gate.io | 33s | overnight scan |
| 13 | CAKE | Bybit | ~high | overnight (seen 4x) |
| 14 | ALLO | Bybit | ~high | overnight (seen 4x) |
| 15-20 | AI coins: FET, RENDER, AGIX | Gate.io/MEXC | unknown | research hypothesis |

**Output:** Ranking z dokładnym lagiem, korelacją, wolumenem, spreadem

### 1.3 Binance WS Stability Fix
**Problem:** Binance disconnects every 1-2 min (ping/pong timeout)  
**Fix:** Persistent connection pool, heartbeat monitoring, graceful reconnect z zachowaniem danych  
**Impact:** Lepsza jakość danych = lepsza korelacja

---

## Phase 2: Exchange Expansion (MOGĘ ZROBIĆ SAMA — 4-8h)

### 2.1 Add Discovered But Unconnected Exchanges
Trzy giełdy już mamy odkryte (pair counts), ale nie podłączone do scannera:

| Giełda | Pary | Overlap z Binance | WS API | Priorytet |
|--------|------|-------------------|--------|-----------|
| **Phemex** | 508 | 477 | ✅ `wss://phemex.com/ws` | 🔴 HIGH — mały MM |
| **Bitget** | 536 | 477 | ✅ `wss://ws.bitget.com/v2/ws` | 🟡 MED |
| **HTX** | 206 | 188 | ✅ `wss://api.huobi.pro/ws` | 🟡 MED |

### 2.2 Nowe Giełdy do Zbadania
| Giełda | Region | Pary (est.) | Dlaczego lag? | API |
|--------|--------|-------------|---------------|-----|
| **BingX** | Global | ~300 | Growing, thin MM | ✅ REST+WS |
| **CoinEX** | China | ~200 | Chinese heritage | ✅ REST+WS |
| **BitMEX** | Global | ~100 | Old infra | ✅ REST+WS |
| **AscendEX** | Global | ~150 | Lower tier | ✅ REST+WS |
| **BtcTurk** | 🇹🇷 Turkey | ~50 | TRY pairs, regulatory | ⚠️ REST only? |
| **WazirX** | 🇮🇳 India | ~200 | INR pairs, Binance-compat | ✅ REST+WS |
| **Indodax** | 🇮🇩 Indonesia | ~100 | IDR pairs | ⚠️ Limited |
| **Zondacrypto** | 🇵🇱 Poland | ~20 | PLN pairs, spot only | ✅ REST+WS |

### 2.3 Korean Deep Dive
Upbit i Bithumb już podłączone ale z ograniczoną liczbą par:
- **Upbit:** 92 streamów aktywnych (z 242 dostępnych)
- **Bithumb:** 31 streamów (z 451 dostępnych)
- **Action:** Zwiększ do pełnej puli, dodaj KRW→USD konwersję w real-time

---

## Phase 3: DEX Integration (MOGĘ ZROBIĆ SAMA — 4-8h)

### 3.1 Perpetual DEXy
| DEX | Chain | Block time | Typ | Oczekiwany lag | Implementacja |
|-----|-------|------------|-----|----------------|---------------|
| **Hyperliquid** | L1 | ~1s | Orderbook | 1-2s | REST API, prosty |
| **dYdX v4** | Cosmos | ~6s | Orderbook | 1-6s | REST + WS |
| **GMX V2** | Arbitrum | ~0.25s | Oracle | 1-5s oracle | Subgraph/RPC |
| **Vertex** | Arbitrum | ~0.25s | Hybrid | 2-8s | REST API |
| **Drift** | Solana | ~0.4s | VAMM | 1-4s | REST API |

### 3.2 DEX vs CEX Lag Measurement
- GMX price feed (Chainlink oracle) vs Binance spot → oracle lag
- Hyperliquid mid-price vs Binance futures → orderbook DEX lag
- **Kluczowe:** DEXy mają transparentne orderbooki on-chain — łatwiej mierzyć

---

## Phase 4: Alternative Signals (MOGĘ ZROBIĆ SAMA — 2-4h)

### 4.1 Funding Rate Divergence
- Monitor 8h funding rate na Binance vs Gate.io vs Bybit vs OKX
- Divergence >0.01% = signal
- **Implementacja:** REST poll co 5 min

### 4.2 Basis Trading (Futures-Spot Spread)
- Track contango/backwardation per exchange
- Cross-exchange basis divergence = signal
- **Implementacja:** WS spot + futures feeds, delta calculation

### 4.3 Open Interest Anomalies
- Sudden OI spike on one exchange before others = informed flow
- **Dane:** Już zbieramy OI na Sparku (collector)

### 4.4 Liquidation Cascade Detection
- Large liquidation on Binance → predict cascade on smaller exchanges
- **Dane:** Już zbieramy liquidations na Sparku

---

## Phase 5: Paper Trading Bot (MOGĘ ZROBIĆ SAMA — 4-6h)

### 5.1 Automated Signal Detection
- Monitor Binance Futures BTC mid-price w real-time
- Detect moves >0.3% w 10s oknie
- Generate LONG/SHORT signal

### 5.2 Simulated Execution
- Otwórz pozycję na Gate.io WIF (simulated, nie real)
- Track PNL z uwzględnieniem slippage i fees
- Log do DuckDB/SQLite

### 5.3 Dashboard
- Live web UI na porcie 8097
- Otwarte pozycje, historia tradów, cumulative PNL
- Equity curve chart

---

## Phase 6: GH Pages Update (MOGĘ ZROBIĆ SAMA — 1-2h per update)

Po każdej fazie → nowy raport na stronie:
- `validation-results.html` — wyniki Phase 1
- `exchange-universe.html` — mapa giełd z lagami
- `paper-trading-dashboard.html` — live wyniki paper tradingu

---

## Timeline (propozycja)

```
Dzisiaj (27.02):
  ├── Phase 1.1: Fix scanner correlation window
  ├── Phase 1.2: Run focused validator on top 20
  └── Phase 1.3: Fix Binance WS stability

Weekend (28.02-01.03):
  ├── Phase 2.1: Add Phemex, Bitget, HTX
  ├── Phase 2.3: Korean exchange full coverage
  └── Phase 3.1: Hyperliquid + dYdX integration

Next week:
  ├── Phase 4: Funding rate + basis + OI signals
  ├── Phase 5: Paper trading bot
  └── Phase 6: GH Pages comprehensive update
```

---

## 🔴 POTRZEBUJĘ OD BARTOSZA

### Decyzje
1. **Priorytet faz** — które najpierw? (proponuję: 1→2→5→3→4)
2. **Paper trading parametry** — jaki starting capital symulować? ($1K? $10K?)
3. **Risk appetite** — Safe/Moderate/Aggressive z Monte Carlo?

### Zasoby (opcjonalne, ale przyspieszą)
4. **VPS w Azji** — $5-20/mies na DigitalOcean Singapore/Tokyo dla niższego latency do Upbit/Bithumb. Bez tego Korean data ma +100ms RTT overhead z Europy.
5. **OKX konto** — OKX ma dobre futures API i jest 3. giełda pod względem wolumenu. Przydałby się do Phase 2.
6. **API keys** — Niektóre giełdy (BtcTurk, WazirX) mogą wymagać konta do WS access. Czy zakładamy?

### Nic nie potrzebuję do:
- Phase 1 (fix + validate) ✅
- Phase 2.1 (add discovered exchanges) ✅  
- Phase 3 (DEX integration — publiczne API) ✅
- Phase 4 (funding + basis — publiczne API) ✅
- Phase 5 (paper trading — local simulation) ✅

---

## Phase 1.x: Master Database — Test Registry

### Cel
Jedna SQLite baza ze WSZYSTKIMI testami, wynikami, walidacjami — single source of truth.

**Plik:** `/home/tank/crypto-bot-data/cross-venue-lag/lag_registry.db`

### Schema
```sql
-- Każdy test/pomiar lagu
CREATE TABLE lag_tests (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,           -- ISO 8601
    pair TEXT,                -- np. WIFUSDT
    exchange TEXT,            -- np. gateio
    master TEXT DEFAULT 'binance_futures:BTCUSDT',
    test_type TEXT,           -- live_ws, historical, overnight_scan, validation
    lag_seconds REAL,
    correlation REAL,
    n_points INTEGER,
    test_duration_s INTEGER,
    confidence REAL,          -- 0-1
    spread_pct REAL,
    tick_rate REAL,           -- ticks/sec
    status TEXT,              -- confirmed, candidate, rejected, noise
    source_file TEXT,         -- plik z którego importowane
    notes TEXT
);

-- Exchange discovery/capabilities
CREATE TABLE exchanges (
    name TEXT PRIMARY KEY,
    total_pairs INTEGER,
    overlap_binance INTEGER,
    ws_endpoint TEXT,
    status TEXT,              -- connected, discovered, untested
    region TEXT,              -- global, korea, turkey, india, etc.
    last_tested TEXT
);

-- Monte Carlo simulation results
CREATE TABLE simulations (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    pair TEXT,
    exchange TEXT,
    scenario TEXT,            -- safe, moderate, aggressive, yolo, max_degen
    starting_capital REAL,
    leverage REAL,
    sl_pct REAL,
    tp_pct REAL,
    median_return REAL,
    mean_return REAL,
    p5 REAL,
    p95 REAL,
    profit_prob REAL,
    bust_rate REAL,
    n_sims INTEGER,
    days INTEGER
);

-- Paper trading log (Phase 5)
CREATE TABLE paper_trades (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    pair TEXT,
    exchange TEXT,
    direction TEXT,           -- LONG/SHORT
    signal_type TEXT,         -- btc_move, funding_div, basis_spread
    entry_price REAL,
    exit_price REAL,
    position_size REAL,
    leverage REAL,
    pnl REAL,
    fees REAL,
    slippage REAL,
    lag_at_entry REAL,
    corr_at_entry REAL,
    duration_s REAL,
    status TEXT               -- open, closed_tp, closed_sl, closed_manual
);
```

### Import
Zaimportuj WSZYSTKIE dotychczasowe wyniki z JSON files do lag_tests table.

---

## Metryki Sukcesu

| Metric | Teraz | Target |
|--------|-------|--------|
| Giełdy podłączone | 6 | 12+ |
| Pary z potwierdzonym lagiem (5-60s) | 2 (WIF, BONK) | 10+ |
| DEXy przetestowane | 0 | 3+ |
| Paper trading days | 0 | 7+ |
| Alternative signal types | 1 (price lag) | 4+ (funding, basis, OI, liquidation) |

---

*Plan created by Wiki — 2026-02-27 07:40 UTC*  
*Ready for Bartosz approval → then execution*
