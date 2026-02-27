#!/usr/bin/env python3
"""
Cross-Venue Lag Validator — Batch Testing Top 20 Candidates
Sequential testing with precise lag measurement for validated pairs
"""
import json, time, threading, sys, os
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
import uuid

# Ensure imports
try:
    import websocket
    import numpy as np
    import scipy.stats
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "numpy", "scipy", "-q"])
    import websocket
    import numpy as np
    import scipy.stats

# ============ CONFIG ============
CANDIDATES = [
    # (pair, exchange, expected_lag, source)
    ("WIFUSDT", "gateio", 28, "confirmed"),
    ("BONKUSDT", "gateio", 33, "confirmed"),
    ("ESPUSDT", "bybit", 37, "overnight_scan"),
    ("SKYUSDT", "gateio", 21, "overnight_scan"),
    ("MUBARAKUSDT", "gateio", 24, "overnight_scan"),
    ("ADAUSDT", "gateio", 6, "historical"),
    ("FLOWUSDT", "upbit", 13, "korean"),
    ("DOGEUSDT", "upbit", 28, "korean"),
    ("MOODENGUSDT", "upbit", 108, "korean"),
    ("CVXUSDT", "gateio", 40, "overnight_scan"),
    ("GOATUSDT", "gateio", 49, "overnight_scan"),
    ("CYBERUSDT", "gateio", 33, "overnight_scan"),
    ("CAKEUSDT", "bybit", None, "overnight_scan"),
    ("ALLOUSDT", "bybit", None, "overnight_scan"),
    ("FETUSDT", "gateio", None, "ai_sector"),
    ("RENDERUSDT", "gateio", None, "ai_sector"),
    ("NEARUSDT", "gateio", None, "l1_alt"),
    ("SUIUSDT", "gateio", None, "l1_alt"),
    ("AAVEUSDT", "gateio", None, "defi"),
    ("TRXUSDT", "bybit", None, "overnight_scan"),
]

TEST_DURATION = 180  # seconds per pair
LAG_WINDOW = 300     # ±300s lag window
RATE_LIMIT_WAIT = 5  # seconds between tests

RESULTS_DIR = Path("/home/tank/crypto-bot-data/cross-venue-lag/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Thread-safe data storage
lock = threading.Lock()
prices = defaultdict(dict)  # key -> {ts_s: mid_price}
connections_active = {}
test_id = str(uuid.uuid4())[:8]

def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)

def convert_krw_to_usd(krw_price):
    """Convert KRW price to USD using approximate rate (simplified)"""
    return krw_price / 1350.0  # Approximate KRW/USD rate

# ============ BINANCE FUTURES ============
def binance_ws():
    """Binance Futures BTCUSDT bookTicker"""
    url = "wss://fstream.binance.com/ws/btcusdt@bookTicker"
    
    def on_message(ws, message):
        try:
            data = json.loads(message)
            bid, ask = float(data.get("b", 0)), float(data.get("a", 0))
            ts = data.get("T", data.get("E", 0))
            if bid > 0 and ask > 0:
                mid = (bid + ask) / 2
                ts_s = int(ts / 1000)
                with lock:
                    prices["binance_futures:BTCUSDT"][ts_s] = mid
        except Exception as e:
            log(f"Binance parse error: {e}")

    def on_error(ws, error):
        log(f"BINANCE error: {error}")
    
    def on_close(ws, code, msg):
        log(f"BINANCE closed: {code} {msg}")
        connections_active["binance"] = False
    
    def on_open(ws):
        log("BINANCE connected ✅")
        connections_active["binance"] = True
    
    while True:
        try:
            ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
            ws.run_forever(ping_interval=20)
        except Exception as e:
            log(f"BINANCE exception: {e}")
        connections_active["binance"] = False
        log("BINANCE reconnecting in 3s...")
        time.sleep(3)

# ============ GATE.IO FUTURES ============
def gateio_ws(pair):
    """Gate.io Futures bookTicker for specific pair"""
    url = "wss://fx-ws.gateio.ws/v4/ws/usdt"
    
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if data.get("event") == "update" and data.get("channel") == "futures.book_ticker":
                r = data.get("result", {})
                symbol = r.get("s", "")
                if symbol.replace("_", "") != pair.upper():
                    return
                bid = float(r.get("b", 0))
                ask = float(r.get("a", 0))
                ts = int(r.get("t", time.time() * 1000))
                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                    ts_s = int(ts / 1000)
                    with lock:
                        prices[f"gateio_futures:{pair}"][ts_s] = mid
        except Exception as e:
            log(f"Gate.io parse error: {e}")

    def on_error(ws, error):
        log(f"GATE.IO error: {error}")
    
    def on_close(ws, code, msg):
        log(f"GATE.IO closed: {code} {msg}")
        connections_active["gateio"] = False
    
    def on_open(ws):
        log(f"GATE.IO connected ✅ for {pair}")
        connections_active["gateio"] = True
        # Subscribe to bookTicker
        gateio_pair = pair.replace("USDT", "_USDT")
        sub = {
            "time": int(time.time()),
            "channel": "futures.book_ticker",
            "event": "subscribe",
            "payload": [gateio_pair]
        }
        ws.send(json.dumps(sub))
        log(f"GATE.IO subscribed to {gateio_pair}")
    
    try:
        ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
        ws.run_forever(ping_interval=20)
    except Exception as e:
        log(f"GATE.IO exception: {e}")
        connections_active["gateio"] = False

# ============ BYBIT ============
def bybit_ws(pair):
    """Bybit linear tickers for specific pair"""
    url = "wss://stream.bybit.com/v5/public/linear"
    
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if data.get("topic", "").startswith("tickers."):
                d = data.get("data", {})
                symbol = d.get("symbol", "")
                if symbol != pair.upper():
                    return
                bid = float(d.get("bid1Price", 0))
                ask = float(d.get("ask1Price", 0))
                ts = int(d.get("ts", time.time() * 1000))
                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                    ts_s = int(ts / 1000)
                    with lock:
                        prices[f"bybit:{pair}"][ts_s] = mid
        except Exception as e:
            log(f"Bybit parse error: {e}")

    def on_error(ws, error):
        log(f"BYBIT error: {error}")
    
    def on_close(ws, code, msg):
        log(f"BYBIT closed: {code} {msg}")
        connections_active["bybit"] = False
    
    def on_open(ws):
        log(f"BYBIT connected ✅ for {pair}")
        connections_active["bybit"] = True
        # Subscribe to ticker
        sub = {
            "op": "subscribe",
            "args": [f"tickers.{pair.upper()}"]
        }
        ws.send(json.dumps(sub))
        log(f"BYBIT subscribed to tickers.{pair.upper()}")
    
    try:
        ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
        ws.run_forever(ping_interval=20)
    except Exception as e:
        log(f"BYBIT exception: {e}")
        connections_active["bybit"] = False

# ============ UPBIT (Korean) ============
def upbit_ws(pair):
    """Upbit KRW ticker for specific pair"""
    url = "wss://api.upbit.com/websocket/v1"
    
    def on_message(ws, message):
        try:
            import zlib
            if isinstance(message, bytes):
                message = zlib.decompress(message, zlib.MAX_WBITS | 32).decode('utf-8')
            data = json.loads(message)
            
            if data.get("type") == "ticker":
                symbol = data.get("code", "")
                # Convert pair to Upbit format (e.g., DOGEUSDT -> KRW-DOGE)
                base = pair.replace("USDT", "")
                expected_symbol = f"KRW-{base}"
                if symbol != expected_symbol:
                    return
                
                price_krw = float(data.get("trade_price", 0))
                ts = int(data.get("timestamp", time.time() * 1000))
                if price_krw > 0:
                    price_usd = convert_krw_to_usd(price_krw)
                    ts_s = int(ts / 1000)
                    with lock:
                        prices[f"upbit:{pair}"][ts_s] = price_usd
        except Exception as e:
            log(f"Upbit parse error: {e}")

    def on_error(ws, error):
        log(f"UPBIT error: {error}")
    
    def on_close(ws, code, msg):
        log(f"UPBIT closed: {code} {msg}")
        connections_active["upbit"] = False
    
    def on_open(ws):
        log(f"UPBIT connected ✅ for {pair}")
        connections_active["upbit"] = True
        # Subscribe to ticker
        base = pair.replace("USDT", "")
        sub = [
            {"ticket": test_id},
            {"type": "ticker", "codes": [f"KRW-{base}"]}
        ]
        ws.send(json.dumps(sub))
        log(f"UPBIT subscribed to KRW-{base}")
    
    try:
        ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
        ws.run_forever(ping_interval=20)
    except Exception as e:
        log(f"UPBIT exception: {e}")
        connections_active["upbit"] = False

# ============ MEXC ============
def mexc_ws(pair):
    """MEXC futures ticker for specific pair"""
    url = "wss://contract.mexc.com/edge"
    
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "data" in data and "symbol" in data:
                d = data["data"]
                symbol = data["symbol"]
                mexc_pair = pair.replace("USDT", "_USDT")
                if symbol != mexc_pair:
                    return
                bid = float(d.get("bid1", 0))
                ask = float(d.get("ask1", 0))
                ts = d.get("timestamp", int(time.time() * 1000))
                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                    ts_s = int(ts / 1000)
                    with lock:
                        prices[f"mexc_futures:{pair}"][ts_s] = mid
        except Exception as e:
            log(f"MEXC parse error: {e}")

    def on_error(ws, error):
        log(f"MEXC error: {error}")
    
    def on_close(ws, code, msg):
        log(f"MEXC closed: {code} {msg}")
        connections_active["mexc"] = False
    
    def on_open(ws):
        log(f"MEXC connected ✅ for {pair}")
        connections_active["mexc"] = True
        mexc_pair = pair.replace("USDT", "_USDT")
        ws.send(json.dumps({"method": "sub.ticker", "param": {"symbol": mexc_pair}}))
        log(f"MEXC subscribed to {mexc_pair}")
    
    try:
        ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
        ws.run_forever(ping_interval=20)
    except Exception as e:
        log(f"MEXC exception: {e}")
        connections_active["mexc"] = False

# ============ CROSS-CORRELATION ANALYSIS ============
def cross_correlation(master, target, max_lag=LAG_WINDOW):
    """Compute cross-correlation with forward-fill for low-liquidity pairs"""
    # Get the full time range
    all_ts = sorted(set(master.keys()) | set(target.keys()))
    if len(all_ts) < 30:
        return None
    
    min_ts, max_ts = min(all_ts), max(all_ts)
    
    # Forward-fill both series to 1s resolution
    m_filled, t_filled = {}, {}
    last_m, last_t = None, None
    for ts in range(min_ts, max_ts + 1):
        if ts in master:
            last_m = master[ts]
        if ts in target:
            last_t = target[ts]
        if last_m is not None:
            m_filled[ts] = last_m
        if last_t is not None:
            t_filled[ts] = last_t
    
    # Get common timestamps after forward-fill
    common = sorted(set(m_filled.keys()) & set(t_filled.keys()))
    if len(common) < 30:
        return None
    
    # Create returns series (consecutive seconds guaranteed by forward-fill)
    m_ret, t_ret = [], []
    for i in range(1, len(common)):
        if common[i] - common[i-1] == 1 and m_filled[common[i-1]] > 0 and t_filled[common[i-1]] > 0:
            mr = (m_filled[common[i]] - m_filled[common[i-1]]) / m_filled[common[i-1]]
            tr = (t_filled[common[i]] - t_filled[common[i-1]]) / t_filled[common[i-1]]
            m_ret.append(mr)
            t_ret.append(tr)
    
    if len(m_ret) < 20:
        return None
    
    m_arr = np.array(m_ret)
    t_arr = np.array(t_ret)
    results = {}
    
    # Compute correlations at different lags
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            m = m_arr[:len(m_arr)-lag] if lag > 0 else m_arr
            t = t_arr[lag:] if lag > 0 else t_arr
        else:
            m = m_arr[-lag:]
            t = t_arr[:len(t_arr)+lag]
        
        if len(m) < 30:
            continue
        
        # Spearman rank correlation
        try:
            spear_corr, _ = scipy.stats.spearmanr(m, t)
            if not np.isnan(spear_corr):
                results[lag] = round(float(spear_corr), 6)
        except:
            continue
    
    if not results:
        return None
    
    # Find best and second best lags
    sorted_lags = sorted(results.items(), key=lambda x: -abs(x[1]))
    best_lag, best_corr = sorted_lags[0]
    second_best_lag, second_best_corr = sorted_lags[1] if len(sorted_lags) > 1 else (None, 0)
    
    # Confidence ratio
    confidence = abs(best_corr) / max(abs(second_best_corr), 0.01) if second_best_corr != 0 else 10.0
    confidence = min(confidence, 10.0)  # cap at 10.0
    
    # Additional metrics
    spread_pct = np.mean([abs(master[ts] - target[ts]) / master[ts] for ts in common[:50] if master[ts] > 0])
    tick_frequency = len(m_ret) / len(common) if len(common) > 0 else 0
    
    return {
        "peak_lag_seconds": best_lag,
        "peak_correlation": best_corr,
        "second_best_lag": second_best_lag,
        "second_best_correlation": second_best_corr,
        "confidence": round(confidence, 3),
        "samples": len(m_ret),
        "common_seconds": len(common),
        "spread_pct": round(spread_pct, 6),
        "tick_frequency": round(tick_frequency, 3),
        "top_lags": {str(k): v for k, v in sorted_lags[:10]}
    }

# ============ SINGLE PAIR TEST ============
def test_single_pair(pair, exchange, expected_lag, source):
    """Test a single pair for lag measurement"""
    log(f"🔬 TESTING: {pair} on {exchange} (expected: {expected_lag}s, source: {source})")
    
    # Clear previous data
    with lock:
        prices.clear()
        connections_active.clear()
    
    # Start Binance (master) connection
    binance_thread = threading.Thread(target=binance_ws, daemon=True)
    binance_thread.start()
    
    # Start target exchange connection
    target_thread = None
    if exchange == "gateio":
        target_thread = threading.Thread(target=gateio_ws, args=(pair,), daemon=True)
    elif exchange == "bybit":
        target_thread = threading.Thread(target=bybit_ws, args=(pair,), daemon=True)
    elif exchange == "upbit":
        target_thread = threading.Thread(target=upbit_ws, args=(pair,), daemon=True)
    elif exchange == "mexc":
        target_thread = threading.Thread(target=mexc_ws, args=(pair,), daemon=True)
    else:
        log(f"❌ Unknown exchange: {exchange}")
        return None
    
    target_thread.start()
    
    # Wait for connections
    log("Waiting for WebSocket connections...")
    for i in range(30):  # 30 seconds timeout
        time.sleep(1)
        if connections_active.get("binance") and connections_active.get(exchange):
            break
        if i % 5 == 0:
            log(f"  Waiting for connections... {connections_active}")
    else:
        log("❌ Failed to establish connections")
        return None
    
    log(f"✅ Connections established. Collecting {TEST_DURATION}s of data...")
    
    # Collect data
    start_time = time.time()
    for i in range(TEST_DURATION):
        time.sleep(1)
        elapsed = int(time.time() - start_time)
        if elapsed % 30 == 0:
            with lock:
                binance_pts = len(prices.get("binance_futures:BTCUSDT", {}))
                target_key = f"{exchange}:{pair}" if exchange != "gateio" else f"gateio_futures:{pair}"
                target_pts = len(prices.get(target_key, {}))
            log(f"  {elapsed}s: Binance {binance_pts} pts, {exchange} {target_pts} pts")
    
    log("📊 Data collection complete. Analyzing...")
    
    # Analyze
    with lock:
        master = prices.get("binance_futures:BTCUSDT", {})
        target_key = f"{exchange}:{pair}" if exchange != "gateio" else f"gateio_futures:{pair}"
        target = prices.get(target_key, {})
    
    if len(master) < 30 or len(target) < 15:
        log(f"❌ Insufficient data: master={len(master)}, target={len(target)}")
        return {
            "pair": pair,
            "exchange": exchange,
            "expected_lag": expected_lag,
            "measured_lag": None,
            "correlation": None,
            "n_points": 0,
            "confidence": 0,
            "spread_pct": None,
            "tick_rate": None,
            "status": "INSUFFICIENT_DATA",
            "source": source,
            "test_duration": TEST_DURATION
        }
    
    cc = cross_correlation(master, target)
    if not cc:
        log(f"❌ Cross-correlation failed")
        return {
            "pair": pair,
            "exchange": exchange,
            "expected_lag": expected_lag,
            "measured_lag": None,
            "correlation": None,
            "n_points": len(target),
            "confidence": 0,
            "spread_pct": None,
            "tick_rate": None,
            "status": "CORRELATION_FAILED",
            "source": source,
            "test_duration": TEST_DURATION
        }
    
    # Determine status
    measured_lag = cc["peak_lag_seconds"]
    correlation = cc["peak_correlation"]
    
    if expected_lag is not None:
        lag_diff = abs(measured_lag - expected_lag)
        if lag_diff <= 5 and abs(correlation) > 0.5:
            status = "CONFIRMED"
        elif lag_diff <= 10 and abs(correlation) > 0.3:
            status = "PARTIAL_MATCH"
        else:
            status = "REJECTED"
    else:
        if abs(correlation) > 0.5 and abs(measured_lag) > 5:
            status = "NEW_DISCOVERY"
        elif abs(correlation) > 0.3:
            status = "WEAK_SIGNAL"
        else:
            status = "NO_LAG"
    
    result = {
        "pair": pair,
        "exchange": exchange,
        "expected_lag": expected_lag,
        "measured_lag": measured_lag,
        "correlation": correlation,
        "n_points": cc["samples"],
        "confidence": cc["confidence"],
        "spread_pct": cc["spread_pct"],
        "tick_rate": cc["tick_frequency"],
        "status": status,
        "source": source,
        "test_duration": TEST_DURATION,
        "second_best_lag": cc["second_best_lag"],
        "second_best_correlation": cc["second_best_correlation"],
        "common_seconds": cc["common_seconds"]
    }
    
    log(f"✅ RESULT: {status} — lag={measured_lag}s (exp: {expected_lag}s), corr={correlation:.3f}, conf={cc['confidence']:.2f}")
    
    return result

# ============ MAIN VALIDATION LOOP ============
def main():
    log("=" * 80)
    log("CROSS-VENUE LAG VALIDATOR — Top 20 Candidates")
    log(f"Test duration per pair: {TEST_DURATION}s")
    log(f"Total estimated time: {len(CANDIDATES)} × {TEST_DURATION + RATE_LIMIT_WAIT}s = {(len(CANDIDATES) * (TEST_DURATION + RATE_LIMIT_WAIT)) // 60} minutes")
    log("=" * 80)
    
    start_time = time.time()
    results = []
    
    for i, (pair, exchange, expected_lag, source) in enumerate(CANDIDATES, 1):
        log(f"\n[{i:2d}/{len(CANDIDATES)}] Starting {pair} on {exchange}")
        
        result = test_single_pair(pair, exchange, expected_lag, source)
        if result:
            results.append(result)
            # Save incremental results
            with open(RESULTS_DIR / "validation_results_partial.json", "w") as f:
                json.dump(results, f, indent=2)
        
        # Rate limiting between tests
        if i < len(CANDIDATES):
            log(f"⏱️  Waiting {RATE_LIMIT_WAIT}s before next test...")
            time.sleep(RATE_LIMIT_WAIT)
    
    # Summary statistics
    confirmed = sum(1 for r in results if r["status"] == "CONFIRMED")
    new_discovery = sum(1 for r in results if r["status"] == "NEW_DISCOVERY")
    rejected = sum(1 for r in results if r["status"] in ["REJECTED", "NO_LAG", "WEAK_SIGNAL"])
    failed = sum(1 for r in results if r["status"] in ["INSUFFICIENT_DATA", "CORRELATION_FAILED"])
    
    summary = {
        "confirmed": confirmed,
        "new_discovery": new_discovery,
        "rejected": rejected,
        "failed": failed,
        "total_tested": len(results),
        "success_rate": round((confirmed + new_discovery) / max(len(results), 1), 3)
    }
    
    # Final results
    final_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_id": test_id,
        "test_duration_per_pair": TEST_DURATION,
        "lag_window": LAG_WINDOW,
        "total_runtime_minutes": round((time.time() - start_time) / 60, 1),
        "results": results,
        "summary": summary
    }
    
    # Save JSON results
    results_file = RESULTS_DIR / "validation_results.json"
    with open(results_file, "w") as f:
        json.dump(final_results, f, indent=2)
    
    # Generate markdown report
    generate_markdown_report(final_results)
    
    log("=" * 80)
    log(f"🎉 VALIDATION COMPLETE!")
    log(f"Total time: {final_results['total_runtime_minutes']} minutes")
    log(f"Results: {confirmed} confirmed, {new_discovery} new, {rejected} rejected, {failed} failed")
    log(f"Success rate: {summary['success_rate']:.1%}")
    log(f"Saved to: {results_file}")
    log(f"Report: {RESULTS_DIR}/VALIDATION-REPORT.md")
    log("=" * 80)

def generate_markdown_report(data):
    """Generate human-readable markdown summary"""
    results = data["results"]
    summary = data["summary"]
    
    md = f"""# Cross-Venue Lag Validation Report

**Test ID:** `{data["test_id"]}`  
**Timestamp:** {data["timestamp"]}  
**Runtime:** {data["total_runtime_minutes"]} minutes  
**Test Duration:** {data["test_duration_per_pair"]}s per pair  

## Summary

| Metric | Value |
|--------|-------|
| Total Tested | {summary["total_tested"]} |
| ✅ Confirmed | {summary["confirmed"]} |
| 🆕 New Discovery | {summary["new_discovery"]} |
| ❌ Rejected | {summary["rejected"]} |
| 💥 Failed | {summary["failed"]} |
| 📈 Success Rate | {summary["success_rate"]:.1%} |

## Results by Status

### ✅ Confirmed Lags
"""
    
    confirmed_results = [r for r in results if r["status"] == "CONFIRMED"]
    if confirmed_results:
        md += "\n| Pair | Exchange | Expected | Measured | Correlation | Confidence |\n"
        md += "|------|----------|----------|----------|-------------|------------|\n"
        for r in confirmed_results:
            md += f"| {r['pair']} | {r['exchange']} | {r['expected_lag']}s | {r['measured_lag']}s | {r['correlation']:.3f} | {r['confidence']:.2f} |\n"
    else:
        md += "\nNo confirmed lags found.\n"
    
    md += "\n### 🆕 New Discoveries\n"
    new_results = [r for r in results if r["status"] == "NEW_DISCOVERY"]
    if new_results:
        md += "\n| Pair | Exchange | Measured Lag | Correlation | Confidence | Source |\n"
        md += "|------|----------|--------------|-------------|------------|--------|\n"
        for r in new_results:
            md += f"| {r['pair']} | {r['exchange']} | {r['measured_lag']}s | {r['correlation']:.3f} | {r['confidence']:.2f} | {r['source']} |\n"
    else:
        md += "\nNo new discoveries.\n"
    
    md += "\n### ❌ Rejected/Weak Signals\n"
    rejected_results = [r for r in results if r["status"] in ["REJECTED", "NO_LAG", "WEAK_SIGNAL"]]
    if rejected_results:
        md += "\n| Pair | Exchange | Expected | Measured | Correlation | Status | Reason |\n"
        md += "|------|----------|----------|----------|-------------|--------|--------|\n"
        for r in rejected_results:
            reason = f"corr={r['correlation']:.3f}" if r['correlation'] else "no correlation"
            md += f"| {r['pair']} | {r['exchange']} | {r['expected_lag']}s | {r['measured_lag']}s | {r['correlation']:.3f} | {r['status']} | {reason} |\n"
    else:
        md += "\nNo rejected signals.\n"
    
    md += "\n### 💥 Failed Tests\n"
    failed_results = [r for r in results if r["status"] in ["INSUFFICIENT_DATA", "CORRELATION_FAILED"]]
    if failed_results:
        md += "\n| Pair | Exchange | Status | N Points |\n"
        md += "|------|----------|--------|---------|\n"
        for r in failed_results:
            md += f"| {r['pair']} | {r['exchange']} | {r['status']} | {r['n_points']} |\n"
    else:
        md += "\nNo failed tests.\n"
    
    md += f"""
## Full Results Table

| # | Pair | Exchange | Expected | Measured | Correlation | Status | Source |
|---|------|----------|----------|----------|-------------|--------|--------|
"""
    for i, r in enumerate(results, 1):
        exp = f"{r['expected_lag']}s" if r['expected_lag'] is not None else "N/A"
        meas = f"{r['measured_lag']}s" if r['measured_lag'] is not None else "N/A"
        corr = f"{r['correlation']:.3f}" if r['correlation'] is not None else "N/A"
        md += f"| {i:2d} | {r['pair']} | {r['exchange']} | {exp} | {meas} | {corr} | {r['status']} | {r['source']} |\n"
    
    md += f"""
## Test Configuration

- **Master Signal:** Binance Futures BTCUSDT bookTicker
- **Lag Window:** ±{data["lag_window"]}s
- **Cross-Correlation:** Spearman rank correlation
- **Minimum Data:** 60 common seconds, 30 returns
- **Rate Limiting:** 5s between tests

## Exchange WebSocket Endpoints

- **Binance Futures:** `wss://fstream.binance.com/ws/btcusdt@bookTicker`
- **Gate.io Futures:** `wss://fx-ws.gateio.ws/v4/ws/usdt`
- **Bybit Linear:** `wss://stream.bybit.com/v5/public/linear`
- **Upbit KRW:** `wss://api.upbit.com/websocket/v1`
- **MEXC Futures:** `wss://contract.mexc.com/edge`

*Generated by lag_validator.py on {data["timestamp"]}*
"""
    
    report_file = RESULTS_DIR / "VALIDATION-REPORT.md"
    with open(report_file, "w") as f:
        f.write(md)

if __name__ == "__main__":
    main()