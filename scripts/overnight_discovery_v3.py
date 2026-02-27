#!/usr/bin/env python3
"""
Overnight Discovery Scanner v3.
Fixes correlation window artifacts, improves Binance WS stability, adds multi-timeframe analysis.
Runs until 18:00 UTC. Analysis every 5 min. Hourly pair rotation + re-discovery.
"""
import json, time, threading, os, signal, sys, traceback
from collections import defaultdict
from datetime import datetime, timezone
from scipy.stats import spearmanr
import numpy as np
import requests
import websocket

DATA_DIR = "/home/tank/crypto-bot-data/cross-venue-lag/docker/data/overnight-scan"
END_UTC_HOUR = 18  # run until 18:00 UTC = 20:00 Warsaw (longer scan)
WINDOWS = [30, 60, 120, 300]  # Multiple correlation windows (seconds)
MIN_RETURNS = 20  # Increased from 12 to 20 for better correlation quality

# ============================================================
# GLOBALS
# ============================================================
prices = defaultdict(lambda: defaultdict(list))
lock = threading.Lock()
running = True
conn_status = {}
discovery_cache = {}
ws_threads = []
reconnect_attempts = defaultdict(int)  # Track reconnect attempts per exchange

def now():
    return datetime.now(timezone.utc).strftime('%H:%M:%S')

def add_price(exchange, pair, price):
    """Add mid-price tick. pair normalized to BTCUSDT format."""
    ts = time.time()
    with lock:
        prices[exchange][pair].append((ts, float(price)))
        # Keep more data for longer windows (15 min buffer)
        if len(prices[exchange][pair]) > 15000:
            cutoff = ts - 900  # 15 min
            prices[exchange][pair] = [(t,p) for t,p in prices[exchange][pair] if t >= cutoff]

def get_exponential_backoff(attempt):
    """Exponential backoff: 5s, 10s, 20s, 40s, max 60s"""
    return min(60, 5 * (2 ** min(attempt, 3)))

# ============================================================
# DISCOVERY
# ============================================================
def discover_all():
    """REST API discovery on all exchanges. Returns {exchange: [pairs]}."""
    print(f"[{now()}] 🔍 DISCOVERY starting...", flush=True)
    result = {}
    
    # Binance Futures
    try:
        r = requests.get('https://fapi.binance.com/fapi/v1/exchangeInfo', timeout=15)
        pairs = [s['symbol'] for s in r.json()['symbols'] if s['status']=='TRADING' and s['symbol'].endswith('USDT')]
        result['binance'] = pairs
        print(f"[{now()}] Binance: {len(pairs)} futures", flush=True)
    except Exception as e:
        result['binance'] = []
        print(f"[{now()}] ❌ Binance discovery: {e}", flush=True)
    
    # Gate.io Futures
    try:
        r = requests.get('https://api.gateio.ws/api/v4/futures/usdt/contracts', timeout=15)
        pairs = [c['name'].replace('_','') for c in r.json() if not c.get('in_delisting')]
        result['gateio'] = [p for p in pairs if p.endswith('USDT')]
        print(f"[{now()}] Gate.io: {len(result['gateio'])} futures", flush=True)
    except Exception as e:
        result['gateio'] = []
        print(f"[{now()}] ❌ Gate.io: {e}", flush=True)
    
    # Bybit
    try:
        r = requests.get('https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000', timeout=15)
        pairs = [i['symbol'] for i in r.json()['result']['list'] if i['status']=='Trading' and i['symbol'].endswith('USDT')]
        result['bybit'] = pairs
        print(f"[{now()}] Bybit: {len(pairs)} futures", flush=True)
    except Exception as e:
        result['bybit'] = []
        print(f"[{now()}] ❌ Bybit: {e}", flush=True)
    
    # MEXC
    try:
        r = requests.get('https://contract.mexc.com/api/v1/contract/detail', timeout=15)
        pairs = [c['symbol'].replace('_','') for c in r.json().get('data',[]) if c.get('state')==0]
        result['mexc'] = [p for p in pairs if p.endswith('USDT')]
        print(f"[{now()}] MEXC: {len(result['mexc'])} futures", flush=True)
    except Exception as e:
        result['mexc'] = []
        print(f"[{now()}] ❌ MEXC: {e}", flush=True)
    
    # Bitget
    try:
        r = requests.get('https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES', timeout=15)
        pairs = [t['symbol'] for t in r.json().get('data',[])]
        result['bitget'] = [p for p in pairs if p.endswith('USDT')]
        print(f"[{now()}] Bitget: {len(result['bitget'])} futures", flush=True)
    except Exception as e:
        result['bitget'] = []
        print(f"[{now()}] ❌ Bitget: {e}", flush=True)
    
    # HTX
    try:
        r = requests.get('https://api.hbdm.com/linear-swap-api/v1/swap_contract_info', timeout=15)
        pairs = [c['contract_code'].replace('-','') for c in r.json().get('data',[]) if c.get('contract_status')==1]
        result['htx'] = [p for p in pairs if p.endswith('USDT')]
        print(f"[{now()}] HTX: {len(result['htx'])} futures", flush=True)
    except Exception as e:
        result['htx'] = []
        print(f"[{now()}] ❌ HTX: {e}", flush=True)
    
    # Phemex
    try:
        r = requests.get('https://api.phemex.com/public/products', timeout=15)
        pairs = []
        for p in r.json().get('data',{}).get('perpProductsV2',[]):
            if p.get('status')=='Listed' and 'USDT' in p.get('quoteCurrency',''):
                sym = p['symbol'].replace('PERP','')
                if sym.endswith('USDT'):
                    pairs.append(sym)
        result['phemex'] = pairs
        print(f"[{now()}] Phemex: {len(pairs)} futures", flush=True)
    except Exception as e:
        result['phemex'] = []
        print(f"[{now()}] ❌ Phemex: {e}", flush=True)
    
    # KOREAN: Upbit (KRW spot — no futures!)
    try:
        r = requests.get('https://api.upbit.com/v1/market/all', timeout=10)
        krw = [m['market'] for m in r.json() if m['market'].startswith('KRW-')]
        # Map KRW-BTC → BTCUSDT for overlap comparison
        upbit_mapped = [m.replace('KRW-','')+'USDT' for m in krw]
        result['upbit'] = upbit_mapped
        print(f"[{now()}] 🇰🇷 Upbit: {len(krw)} KRW spot pairs", flush=True)
    except Exception as e:
        result['upbit'] = []
        print(f"[{now()}] ❌ Upbit: {e}", flush=True)
    
    # KOREAN: Bithumb (KRW spot)
    try:
        r = requests.get('https://api.bithumb.com/public/ticker/ALL_KRW', timeout=10)
        d = r.json()
        if d.get('status') == '0000':
            coins = [k for k in d['data'].keys() if k != 'date']
            bithumb_mapped = [c+'USDT' for c in coins]
            result['bithumb'] = bithumb_mapped
            print(f"[{now()}] 🇰🇷 Bithumb: {len(coins)} KRW spot pairs", flush=True)
    except Exception as e:
        result['bithumb'] = []
        print(f"[{now()}] ❌ Bithumb: {e}", flush=True)
    
    # Compute overlaps
    binance_set = set(result.get('binance',[]))
    print(f"\n[{now()}] Overlaps with Binance:", flush=True)
    for ex in result:
        if ex == 'binance': continue
        overlap = set(result[ex]) & binance_set
        print(f"  {ex}: {len(result[ex])} total, {len(overlap)} overlap", flush=True)
    
    # Save
    with open(os.path.join(DATA_DIR, 'exchange_discovery.json'), 'w') as f:
        summary = {}
        for ex, pairs in result.items():
            overlap = set(pairs) & binance_set if ex != 'binance' else set()
            summary[ex] = {'count': len(pairs), 'overlap': len(overlap)}
        json.dump(summary, f, indent=1)
    
    return result

# ============================================================
# IMPROVED WEBSOCKETS WITH STABILITY
# ============================================================
def run_ws_binance(pairs):
    """Binance Futures master - improved with ping/pong and graceful reconnect."""
    exchange = 'binance'
    
    def attempt_connection():
        try:
            rmap = {}
            mapped = []
            for p in pairs:
                if p == 'PEPEUSDT': m = '1000PEPEUSDT'
                elif p == 'BONKUSDT': m = '1000BONKUSDT'
                elif p == 'FLOKIUSDT': m = '1000FLOKIUSDT'
                elif p == 'SHIBUSDT': m = '1000SHIBUSDT'
                else: m = p
                mapped.append(m.lower())
                rmap[m] = p
            
            streams = '/'.join(f"{s}@bookTicker" for s in mapped[:200])
            url = f"wss://fstream.binance.com/stream?streams={streams}"
            
            # Save current data before reconnect
            saved_data = {}
            if reconnect_attempts[exchange] > 0:
                with lock:
                    saved_data = {p: list(prices[exchange][p]) for p in prices[exchange]}
                    print(f"[{now()}] Binance reconnect: saving {len(saved_data)} pairs data", flush=True)
            
            ping_thread = None
            
            def on_msg(ws, msg):
                try:
                    d = json.loads(msg)
                    if 'data' in d:
                        s = d['data']['s']
                        mid = (float(d['data']['b']) + float(d['data']['a'])) / 2
                        add_price(exchange, rmap.get(s,s), mid)
                except Exception as e:
                    pass
            
            def on_open(ws):
                nonlocal ping_thread
                conn_status[exchange] = True
                reconnect_attempts[exchange] = 0
                print(f"[{now()}] ✅ Binance: {min(len(mapped),200)} streams", flush=True)
                
                # Restore saved data
                if saved_data:
                    with lock:
                        for p, data in saved_data.items():
                            prices[exchange][p] = data
                    print(f"[{now()}] Binance: restored {len(saved_data)} pairs data", flush=True)
                
                # Start ping thread (send ping frame manually)
                def ping_loop():
                    while conn_status.get(exchange, False) and running:
                        try:
                            time.sleep(30)  # Ping every 30s
                            if conn_status.get(exchange, False) and hasattr(ws, 'sock') and ws.sock:
                                ws.sock.ping()
                        except Exception as e:
                            print(f"[{now()}] Binance ping failed: {e}", flush=True)
                            break
                
                ping_thread = threading.Thread(target=ping_loop, daemon=True)
                ping_thread.start()
            
            def on_close(ws, *args):
                conn_status[exchange] = False
                reconnect_attempts[exchange] += 1
                backoff = get_exponential_backoff(reconnect_attempts[exchange])
                print(f"[{now()}] Binance WS closed, reconnect #{reconnect_attempts[exchange]} in {backoff}s...", flush=True)
                
                if running and reconnect_attempts[exchange] < 20:  # Max 20 attempts
                    time.sleep(backoff)
                    if running:
                        attempt_connection()
                else:
                    print(f"[{now()}] Binance: max reconnect attempts reached", flush=True)
            
            def on_error(ws, error):
                print(f"[{now()}] Binance error: {error}", flush=True)
            
            websocket.enableTrace(False)
            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_msg, 
                                      on_close=on_close, on_error=on_error)
            ws.run_forever(ping_interval=None, ping_timeout=None)  # We handle ping manually
            
        except Exception as e:
            print(f"[{now()}] Binance WS fatal: {e}", flush=True)
            reconnect_attempts[exchange] += 1
            if running and reconnect_attempts[exchange] < 20:
                backoff = get_exponential_backoff(reconnect_attempts[exchange])
                print(f"[{now()}] Binance: retry in {backoff}s", flush=True)
                time.sleep(backoff)
                if running:
                    attempt_connection()
    
    attempt_connection()

def run_ws_gateio(pairs):
    """Gate.io with improved reconnect logic."""
    exchange = 'gateio'
    
    def attempt_connection():
        try:
            gateio_pairs = [p.replace('USDT','_USDT') for p in pairs]
            url = "wss://fx-ws.gateio.ws/v4/ws/usdt"
            
            def on_msg(ws, msg):
                try:
                    d = json.loads(msg)
                    if d.get('channel')=='futures.book_ticker' and 'result' in d:
                        r = d['result']
                        mid = (float(r['b'])+float(r['a']))/2
                        add_price(exchange, r['s'].replace('_',''), mid)
                except: pass
            
            def on_open(ws):
                conn_status[exchange] = True
                reconnect_attempts[exchange] = 0
                ws.send(json.dumps({"time":int(time.time()),"channel":"futures.book_ticker","event":"subscribe","payload":gateio_pairs}))
                print(f"[{now()}] ✅ Gate.io: {len(gateio_pairs)} pairs", flush=True)
            
            def on_close(ws, *args):
                conn_status[exchange] = False
                reconnect_attempts[exchange] += 1
                if running and reconnect_attempts[exchange] < 15:
                    backoff = get_exponential_backoff(reconnect_attempts[exchange])
                    print(f"[{now()}] Gate.io: reconnect #{reconnect_attempts[exchange]} in {backoff}s", flush=True)
                    time.sleep(backoff)
                    if running:
                        attempt_connection()
            
            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_msg, on_close=on_close)
            ws.run_forever(ping_interval=20, ping_timeout=10)
            
        except Exception as e:
            print(f"[{now()}] Gate.io error: {e}", flush=True)
            if running:
                time.sleep(5)
                attempt_connection()
    
    attempt_connection()

def run_ws_bybit(pairs):
    """Bybit with improved reconnect logic."""
    exchange = 'bybit'
    
    def attempt_connection():
        try:
            url = "wss://stream.bybit.com/v5/public/linear"
            
            def on_msg(ws, msg):
                try:
                    d = json.loads(msg)
                    if d.get('topic','').startswith('tickers.') and 'data' in d:
                        dd = d['data']
                        b1 = dd.get('bid1Price','0')
                        a1 = dd.get('ask1Price','0')
                        if b1 and a1 and float(b1)>0 and float(a1)>0:
                            add_price(exchange, dd['symbol'], (float(b1)+float(a1))/2)
                except: pass
            
            def on_open(ws):
                conn_status[exchange] = True
                reconnect_attempts[exchange] = 0
                ws.send(json.dumps({"op":"subscribe","args":[f"tickers.{p}" for p in pairs]}))
                print(f"[{now()}] ✅ Bybit: {len(pairs)} pairs", flush=True)
            
            def on_close(ws, *args):
                conn_status[exchange] = False
                reconnect_attempts[exchange] += 1
                if running and reconnect_attempts[exchange] < 15:
                    backoff = get_exponential_backoff(reconnect_attempts[exchange])
                    print(f"[{now()}] Bybit: reconnect #{reconnect_attempts[exchange]} in {backoff}s", flush=True)
                    time.sleep(backoff)
                    if running:
                        attempt_connection()
            
            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_msg, on_close=on_close)
            ws.run_forever(ping_interval=20, ping_timeout=10)
            
        except Exception as e:
            print(f"[{now()}] Bybit error: {e}", flush=True)
            if running:
                time.sleep(5)
                attempt_connection()
    
    attempt_connection()

def run_ws_mexc(pairs):
    """MEXC with improved reconnect logic."""
    exchange = 'mexc'
    
    def attempt_connection():
        try:
            url = "wss://contract.mexc.com/edge"
            
            def on_msg(ws, msg):
                try:
                    d = json.loads(msg)
                    dd = d.get('data',{})
                    if isinstance(dd, dict) and 'bidPrice' in dd and 'askPrice' in dd:
                        mid = (float(dd['bidPrice'])+float(dd['askPrice']))/2
                        sym = dd.get('symbol','').replace('_','')
                        if sym: add_price(exchange, sym, mid)
                except: pass
            
            def on_open(ws):
                conn_status[exchange] = True
                reconnect_attempts[exchange] = 0
                for p in pairs:
                    ws.send(json.dumps({"method":"sub.ticker","param":{"symbol":p.replace('USDT','_USDT')}}))
                print(f"[{now()}] ✅ MEXC: {len(pairs)} pairs", flush=True)
                
                def ping():
                    while running and conn_status.get(exchange):
                        try: 
                            ws.send('{"method":"ping"}')
                            time.sleep(10)
                        except: 
                            break
                threading.Thread(target=ping, daemon=True).start()
            
            def on_close(ws, *args):
                conn_status[exchange] = False
                reconnect_attempts[exchange] += 1
                if running and reconnect_attempts[exchange] < 15:
                    backoff = get_exponential_backoff(reconnect_attempts[exchange])
                    print(f"[{now()}] MEXC: reconnect #{reconnect_attempts[exchange]} in {backoff}s", flush=True)
                    time.sleep(backoff)
                    if running:
                        attempt_connection()
            
            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_msg, on_close=on_close)
            ws.run_forever()
            
        except Exception as e:
            print(f"[{now()}] MEXC error: {e}", flush=True)
            if running:
                time.sleep(5)
                attempt_connection()
    
    attempt_connection()

def run_ws_upbit(pairs):
    """Upbit KRW spot via WebSocket with improved stability."""
    exchange = 'upbit'
    
    def attempt_connection():
        try:
            url = "wss://api.upbit.com/websocket/v1"
            upbit_pairs = [f"KRW-{p.replace('USDT','')}" for p in pairs if p.replace('USDT','') != '']
            
            def on_msg(ws, msg):
                try:
                    if isinstance(msg, bytes):
                        d = json.loads(msg.decode())
                    else:
                        d = json.loads(msg)
                    code = d.get('code','')
                    tp = d.get('trade_price',0)
                    if code and tp:
                        pair = code.replace('KRW-','') + 'USDT'
                        add_price(exchange, pair, tp)
                except: pass
            
            def on_open(ws):
                conn_status[exchange] = True
                reconnect_attempts[exchange] = 0
                sub = [{"ticket":"lag-scanner-v3"},{"type":"ticker","codes":upbit_pairs,"isOnlyRealtime":True}]
                ws.send(json.dumps(sub))
                print(f"[{now()}] 🇰🇷 Upbit: {len(upbit_pairs)} KRW pairs", flush=True)
            
            def on_close(ws, *args):
                conn_status[exchange] = False
                reconnect_attempts[exchange] += 1
                if running and reconnect_attempts[exchange] < 15:
                    backoff = get_exponential_backoff(reconnect_attempts[exchange])
                    print(f"[{now()}] Upbit: reconnect #{reconnect_attempts[exchange]} in {backoff}s", flush=True)
                    time.sleep(backoff)
                    if running:
                        attempt_connection()
            
            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_msg, on_close=on_close)
            ws.run_forever()
            
        except Exception as e:
            print(f"[{now()}] Upbit error: {e}", flush=True)
            if running:
                time.sleep(5)
                attempt_connection()
    
    attempt_connection()

def run_ws_bithumb(pairs):
    """Bithumb KRW spot via WebSocket with improved stability."""
    exchange = 'bithumb'
    
    def attempt_connection():
        try:
            url = "wss://pubwss.bithumb.com/pub/ws"
            coins = [p.replace('USDT','') for p in pairs]
            
            def on_msg(ws, msg):
                try:
                    d = json.loads(msg)
                    if d.get('type') == 'ticker' and 'content' in d:
                        c = d['content']
                        sym = c.get('symbol','')  # BTC_KRW
                        price = float(c.get('closePrice',0))
                        if sym and price:
                            pair = sym.split('_')[0] + 'USDT'
                            add_price(exchange, pair, price)
                except: pass
            
            def on_open(ws):
                conn_status[exchange] = True
                reconnect_attempts[exchange] = 0
                sub = {"type":"ticker","symbols":[f"{c}_KRW" for c in coins],"tickTypes":["MID"]}
                ws.send(json.dumps(sub))
                print(f"[{now()}] 🇰🇷 Bithumb: {len(coins)} KRW pairs", flush=True)
            
            def on_close(ws, *args):
                conn_status[exchange] = False
                reconnect_attempts[exchange] += 1
                if running and reconnect_attempts[exchange] < 15:
                    backoff = get_exponential_backoff(reconnect_attempts[exchange])
                    print(f"[{now()}] Bithumb: reconnect #{reconnect_attempts[exchange]} in {backoff}s", flush=True)
                    time.sleep(backoff)
                    if running:
                        attempt_connection()
            
            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_msg, on_close=on_close)
            ws.run_forever()
            
        except Exception as e:
            print(f"[{now()}] Bithumb error: {e}", flush=True)
            if running:
                time.sleep(5)
                attempt_connection()
    
    attempt_connection()

# ============================================================
# IMPROVED MULTI-WINDOW ANALYSIS
# ============================================================
def compute_lag_multi_window(master_data, target_data):
    """Compute lag across multiple time windows with weighted correlation."""
    results = {}
    
    for window in WINDOWS:
        max_lag = min(int(window * 0.9), window - 10)  # Filter: |lag| < 0.9 × window_size
        
        # Get recent data within window
        now_ts = time.time()
        cutoff = now_ts - window
        
        master_recent = [(ts, p) for ts, p in master_data if ts >= cutoff]
        target_recent = [(ts, p) for ts, p in target_data if ts >= cutoff]
        
        if len(master_recent) < MIN_RETURNS or len(target_recent) < MIN_RETURNS:
            results[f'lag_{window}s'] = None
            results[f'corr_{window}s'] = None
            results[f'n_{window}s'] = 0
            continue
        
        # Convert to returns with timestamp alignment
        def to_weighted_returns(data, window_size):
            by_sec = {}
            for ts, price in data:
                by_sec[int(ts)] = price
            
            secs = sorted(by_sec.keys())
            returns = {}
            weights = {}
            
            for i in range(1, len(secs)):
                if secs[i] - secs[i-1] == 1 and by_sec[secs[i-1]] != 0:
                    ret = (by_sec[secs[i]] - by_sec[secs[i-1]]) / by_sec[secs[i-1]]
                    returns[secs[i]] = ret
                    # Weight: more recent = higher weight (exponential decay)
                    age = now_ts - secs[i]
                    weight = np.exp(-age / (window_size / 3))  # Decay over 1/3 of window
                    weights[secs[i]] = weight
            
            return returns, weights
        
        master_returns, master_weights = to_weighted_returns(master_recent, window)
        target_returns, target_weights = to_weighted_returns(target_recent, window)
        
        if len(master_returns) < MIN_RETURNS or len(target_returns) < MIN_RETURNS:
            results[f'lag_{window}s'] = None
            results[f'corr_{window}s'] = None
            results[f'n_{window}s'] = 0
            continue
        
        best_lag, best_corr, best_n = 0, 0, 0
        
        # Test different lag values
        for lag in range(-max_lag, max_lag + 1):
            # Align returns with lag
            pairs = []
            total_weight = 0
            
            for ts in master_returns:
                if ts + lag in target_returns:
                    weight = (master_weights[ts] + target_weights[ts + lag]) / 2
                    pairs.append((master_returns[ts], target_returns[ts + lag], weight))
                    total_weight += weight
            
            if len(pairs) < MIN_RETURNS:
                continue
            
            # Weighted Spearman correlation
            master_vals = [p[0] for p in pairs]
            target_vals = [p[1] for p in pairs]
            weights = [p[2] for p in pairs]
            
            if np.std(master_vals) < 1e-12 or np.std(target_vals) < 1e-12:
                continue
            
            try:
                # Weighted Spearman: rank the values, then compute weighted Pearson on ranks
                master_ranks = np.argsort(np.argsort(master_vals))
                target_ranks = np.argsort(np.argsort(target_vals))
                
                # Weighted Pearson on ranks
                def weighted_pearson(x, y, w):
                    w = np.array(w)
                    w = w / np.sum(w)  # Normalize weights
                    
                    x_mean = np.sum(w * x)
                    y_mean = np.sum(w * y)
                    
                    x_var = np.sum(w * (x - x_mean) ** 2)
                    y_var = np.sum(w * (y - y_mean) ** 2)
                    xy_cov = np.sum(w * (x - x_mean) * (y - y_mean))
                    
                    if x_var * y_var == 0:
                        return 0
                    
                    return xy_cov / np.sqrt(x_var * y_var)
                
                corr = weighted_pearson(master_ranks, target_ranks, weights)
                
                if abs(corr) > abs(best_corr):
                    best_corr = corr
                    best_lag = lag
                    best_n = len(pairs)
                    
            except Exception:
                continue
        
        results[f'lag_{window}s'] = best_lag if best_corr != 0 else None
        results[f'corr_{window}s'] = round(best_corr, 4) if best_corr != 0 else None
        results[f'n_{window}s'] = best_n
    
    return results

def compute_confidence_score(lag_results):
    """Compute confidence score based on agreement across windows."""
    valid_lags = []
    valid_corrs = []
    
    for window in WINDOWS:
        lag = lag_results.get(f'lag_{window}s')
        corr = lag_results.get(f'corr_{window}s')
        n = lag_results.get(f'n_{window}s', 0)
        
        if lag is not None and corr is not None and n >= MIN_RETURNS:
            valid_lags.append(lag)
            valid_corrs.append(abs(corr))
    
    if len(valid_lags) < 2:
        return 0.0
    
    # Agreement score: how similar are the lags?
    lag_std = np.std(valid_lags)
    max_agreement = max(WINDOWS) * 0.1  # 10% of max window
    lag_agreement = max(0, 1 - lag_std / max_agreement)
    
    # Correlation strength score
    avg_corr = np.mean(valid_corrs)
    
    # Number of confirming windows
    window_score = len(valid_lags) / len(WINDOWS)
    
    # Combined confidence
    confidence = (lag_agreement * 0.4 + avg_corr * 0.4 + window_score * 0.2)
    return round(min(1.0, confidence), 3)

def run_analysis(scan_num):
    ts = now()
    results = []
    
    with lock:
        btc_master = list(prices['binance'].get('BTCUSDT', []))
        snap = {}
        for ex in prices:
            if ex == 'binance':
                snap[ex] = {p: list(d) for p,d in prices[ex].items() if len(d) > MIN_RETURNS and p != 'BTCUSDT'}
            else:
                snap[ex] = {p: list(d) for p,d in prices[ex].items() if len(d) > MIN_RETURNS}
    
    if len(btc_master) < MIN_RETURNS:
        print(f"[{ts}] Waiting for BTC data ({len(btc_master)} pts)...", flush=True)
        return
    
    for ex in snap:
        if ex == 'binance': continue
        for pair, data in snap[ex].items():
            # Same-pair: Binance pair vs other exchange pair
            if pair in snap.get('binance', {}):
                lag_results = compute_lag_multi_window(snap['binance'][pair], data)
                confidence = compute_confidence_score(lag_results)
                
                # Find best single window for summary
                best_window = None
                best_corr_abs = 0
                for window in WINDOWS:
                    corr = lag_results.get(f'corr_{window}s')
                    if corr and abs(corr) > best_corr_abs:
                        best_corr_abs = abs(corr)
                        best_window = window
                
                if best_window:
                    result = {
                        'p': pair, 'ex': ex, 
                        'lag': lag_results[f'lag_{best_window}s'], 
                        'c': lag_results[f'corr_{best_window}s'], 
                        'n': lag_results[f'n_{best_window}s'],
                        'confidence': confidence,
                        'best_window': best_window,
                        't': 'xpair'
                    }
                    # Add all window results
                    for window in WINDOWS:
                        result[f'lag_{window}s'] = lag_results[f'lag_{window}s']
                        result[f'corr_{window}s'] = lag_results[f'corr_{window}s']
                        result[f'n_{window}s'] = lag_results[f'n_{window}s']
                    
                    results.append(result)
            
            # BTC signal → pair on other exchange
            lag_results = compute_lag_multi_window(btc_master, data)
            confidence = compute_confidence_score(lag_results)
            
            # Find best single window for summary
            best_window = None
            best_corr_abs = 0
            for window in WINDOWS:
                corr = lag_results.get(f'corr_{window}s')
                if corr and abs(corr) > best_corr_abs:
                    best_corr_abs = abs(corr)
                    best_window = window
            
            if best_window:
                result = {
                    'p': pair, 'ex': ex, 
                    'lag': lag_results[f'lag_{best_window}s'], 
                    'c': lag_results[f'corr_{best_window}s'], 
                    'n': lag_results[f'n_{best_window}s'],
                    'confidence': confidence,
                    'best_window': best_window,
                    't': 'btcsig'
                }
                # Add all window results
                for window in WINDOWS:
                    result[f'lag_{window}s'] = lag_results[f'lag_{window}s']
                    result[f'corr_{window}s'] = lag_results[f'corr_{window}s']
                    result[f'n_{window}s'] = lag_results[f'n_{window}s']
                
                results.append(result)
    
    # Sort by confidence first, then by lag magnitude
    results.sort(key=lambda r: (r['confidence'], abs(r['lag']) if r['lag'] else 0), reverse=True)
    
    # Append to history (compact)
    with open(os.path.join(DATA_DIR, 'scan_history.jsonl'), 'a') as f:
        entry = {'ts': ts, '#': scan_num, 'n': len(results), 'top': results[:10],
                 'conn': {k: v for k,v in conn_status.items()}}
        f.write(json.dumps(entry) + '\n')
    
    # Cumulative best with multi-window data
    best_file = os.path.join(DATA_DIR, 'cumulative_best.json')
    try:
        with open(best_file) as f: cum = json.load(f)
    except: cum = {}
    
    # Only keep results with high confidence and significant lag
    lag_found = [r for r in results if abs(r['lag']) >= 3 and r['confidence'] >= 0.2]
    for r in lag_found:
        k = f"{r['p']}_{r['ex']}_{r['t']}"
        prev = cum.get(k, {})
        # Update if higher confidence or (same confidence but higher correlation)
        if (r['confidence'] > prev.get('confidence', 0) or 
            (r['confidence'] == prev.get('confidence', 0) and abs(r['c']) > abs(prev.get('c', 0)))):
            cum[k] = {**r, 'first': prev.get('first', ts), 'last': ts, 'seen': prev.get('seen', 0) + 1}
    
    with open(best_file, 'w') as f:
        json.dump(cum, f, indent=1)
    
    # Enhanced STATE.md with multi-window info
    top = sorted(cum.values(), key=lambda r: (r['confidence'], abs(r['lag'])), reverse=True)[:25]
    pair_counts = {ex: len(d) for ex, d in snap.items()}
    
    md = [
        f"# Overnight Discovery — State v3",
        f"*{ts} UTC | scan #{scan_num}*\n",
        "## Connections",
        ' '.join(f"{k}:{'OK' if v else 'X'}" for k,v in conn_status.items()),
        f"BTC: {len(btc_master)} pts | Streams: {pair_counts}\n",
        "## Top Laggers (multi-window analysis)",
        "| Pair | Exchange | Type | Lag | Corr | Confidence | Best Window | Seen |",
        "|------|----------|------|-----|------|------------|-------------|------|",
    ]
    for r in top:
        best_win = r.get('best_window', '?')
        md.append(f"| {r['p']} | {r['ex']} | {r['t']} | {r['lag']}s | {r['c']} | {r['confidence']} | {best_win}s | {r.get('seen',1)} |")
    if not top:
        md.append("| scanning... | | | | | | | |")
    
    md.append(f"\n## Scan #{scan_num}: {len(results)} combos, {len(lag_found)} with lag>=3s + confidence>=0.2")
    
    # Show windows breakdown for top results
    if results:
        md.append(f"\n## Multi-Window Breakdown (top 5)")
        for r in results[:5]:
            md.append(f"### {r['p']} @ {r['ex']} ({r['t']})")
            window_info = []
            for window in WINDOWS:
                lag = r.get(f'lag_{window}s')
                corr = r.get(f'corr_{window}s')
                n = r.get(f'n_{window}s', 0)
                if lag is not None:
                    window_info.append(f"{window}s: {lag:+3d}s ({corr:.3f}, n={n})")
                else:
                    window_info.append(f"{window}s: --")
            md.append(f"- {' | '.join(window_info)} | **Confidence: {r['confidence']}**")
    
    # Korean exchange highlight
    korean = [r for r in results if r['ex'] in ('upbit', 'bithumb') and abs(r['lag']) >= 1]
    if korean:
        md.append(f"\n## 🇰🇷 Korean Exchange Lags")
        for r in korean[:10]:
            md.append(f"- {r['p']} on {r['ex']}: {r['lag']}s lag, corr {r['c']}, confidence {r['confidence']} ({r['t']})")
    
    md.append("\n## v3 Features: Multi-window analysis (30s/60s/120s/300s), weighted correlation, boundary artifact filtering")
    md.append("## Phase 1 baseline: WIF/Gate.io 28s(0.88), BONK/Gate.io 33s(0.58)")
    
    with open(os.path.join(DATA_DIR, 'STATE.md'), 'w') as f:
        f.write('\n'.join(md) + '\n')
    
    print(f"[{ts}] scan #{scan_num}: {len(results)} combos, {len(lag_found)} lag>=3s+conf>=0.2", flush=True)
    for r in results[:5]:
        flag = '🇰🇷' if r['ex'] in ('upbit','bithumb') else '  '
        print(f"  {flag} {r['p']:16} {r['ex']:10} lag={r['lag']:+4d}s corr={r['c']:.3f} conf={r['confidence']:.3f}", flush=True)

# ============================================================
# MAIN
# ============================================================
def main():
    global running
    
    print(f"[{now()}] === OVERNIGHT DISCOVERY SCANNER v3 ===", flush=True)
    print(f"[{now()}] Features: Multi-window analysis, weighted correlation, WS stability", flush=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Discovery
    disc = discover_all()
    binance_set = set(disc.get('binance', []))
    
    # Compute what to subscribe per exchange
    # Priority: meme/low-cap first, then rotate
    priority_coins = ['WIFUSDT','BONKUSDT','PEPEUSDT','FLOKIUSDT','MEMEUSDT','BOMEUSDT',
                      'DOGSUSDT','NOTUSDT','TURBOUSDT','MEWUSDT','POPCATUSDT','PNUTUSDT',
                      'ACTUSDT','GOATUSDT','MOODENGUSDT','DEGENUSDT','BANUSDT','BRETTUSDT',
                      'FARTCOINUSDT','AIXBTUSDT','COOKIEUSDT','SWARMSUSDT','VIRTUALUSDT',
                      'GRIFFAINUSDT','ZEREBROUSDT','HIPPOUSDT','CHILLGUYUSDT',
                      'ADAUSDT','DOGEUSDT','SOLUSDT','BTCUSDT','ETHUSDT']
    
    # For each exchange: overlap pairs, priority first
    def get_pairs(ex_key, max_pairs=500):
        ex_pairs = set(disc.get(ex_key, []))
        overlap = ex_pairs & binance_set
        # Priority pairs first
        ordered = [p for p in priority_coins if p in overlap]
        rest = sorted(overlap - set(ordered))
        return (ordered + rest)[:max_pairs]
    
    # Korean exchanges: map to coins they actually have
    def get_korean_pairs(ex_key, max_pairs=100):
        ex_pairs = set(disc.get(ex_key, []))
        overlap = ex_pairs & binance_set
        ordered = [p for p in priority_coins if p in overlap]
        rest = sorted(overlap - set(ordered))
        return (ordered + rest)[:max_pairs]
    
    # Binance master: union of all target pairs
    all_targets = set()
    for ex_key in ['gateio','bybit','mexc','upbit','bithumb']:
        if ex_key in ('upbit','bithumb'):
            all_targets.update(get_korean_pairs(ex_key))
        else:
            all_targets.update(get_pairs(ex_key, 200))
    all_targets.add('BTCUSDT')
    all_targets.add('ETHUSDT')
    binance_sub = sorted(all_targets)[:200]
    
    print(f"\n[{now()}] Starting WebSockets with improved stability:", flush=True)
    print(f"  Binance master: {len(binance_sub)} pairs", flush=True)
    
    # Start all WebSocket threads
    ws_configs = [
        ('binance', run_ws_binance, binance_sub),
        ('gateio', run_ws_gateio, get_pairs('gateio')),
        ('bybit', run_ws_bybit, get_pairs('bybit')),
        ('mexc', run_ws_mexc, get_pairs('mexc', 200)),
        ('upbit', run_ws_upbit, get_korean_pairs('upbit')),
        ('bithumb', run_ws_bithumb, get_korean_pairs('bithumb')),
    ]
    
    for name, fn, pairs in ws_configs:
        if pairs:
            print(f"  {name}: {len(pairs)} pairs", flush=True)
            t = threading.Thread(target=fn, args=(pairs,), daemon=True)
            t.start()
            ws_threads.append(t)
            time.sleep(0.5)
    
    # Wait for connections with progress
    print(f"\n[{now()}] Waiting for connections...", flush=True)
    for i in range(40):  # 20s total
        time.sleep(0.5)
        connected = sum(1 for v in conn_status.values() if v)
        if connected == len(ws_configs):
            break
        if i % 10 == 9:  # Print every 5s
            print(f"[{now()}] Connected: {connected}/{len(ws_configs)} exchanges", flush=True)
    
    print(f"\n[{now()}] Final connections: {conn_status}", flush=True)
    
    # Main analysis loop
    scan_num = 0
    hour_mark = time.time()
    
    while running:
        # Time check
        h = datetime.now(timezone.utc).hour
        if h >= END_UTC_HOUR and scan_num > 0:
            print(f"[{now()}] Reached {END_UTC_HOUR}:00 UTC — done", flush=True)
            break
        
        # Wait (3 min first scan, 5 min after)
        wait_s = 180 if scan_num == 0 else 300
        deadline = time.time() + wait_s
        while running and time.time() < deadline:
            time.sleep(1)
        if not running:
            break
        
        scan_num += 1
        try:
            run_analysis(scan_num)
        except Exception as e:
            print(f"[{now()}] Analysis error: {e}", flush=True)
            traceback.print_exc()
        
        # Hourly re-discovery (just REST, don't restart WebSockets)
        if time.time() - hour_mark > 3600:
            hour_mark = time.time()
            print(f"\n[{now()}] HOURLY RE-DISCOVERY (REST only, WS stays)", flush=True)
            try:
                discover_all()
            except Exception as e:
                print(f"[{now()}] Discovery error (non-fatal): {e}", flush=True)
    
    # Final
    print(f"[{now()}] Final analysis...", flush=True)
    try:
        run_analysis(scan_num + 1)
    except:
        pass
    print(f"[{now()}] DONE. {scan_num} scans.", flush=True)

def stop(sig, frame):
    global running
    running = False
    print(f"[{now()}] Signal received, stopping...", flush=True)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", flush=True)
        traceback.print_exc()