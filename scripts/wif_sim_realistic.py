#!/usr/bin/env python3
"""
Realistic WIF lag trading sim — fixed position sizes (no compounding insanity).
Gate.io WIF_USDT Futures: max 50x, taker 0.075%, funding 0.005%/8h.
Lag: 28s, corr: 0.88, WIF beta: ~4x BTC.
"""
import random, statistics, json

N = 5000

def sim(capital0, leverage, pos_fixed_usd, sl_pct, tp_pct, days=30, slip_bps=20):
    """Fixed position size per trade — no compounding."""
    fee_rt = 0.00075 * 2         # round-trip taker
    slip_rt = slip_bps / 10000 * 2
    cost_pct = fee_rt + slip_rt  # ~0.19%
    corr = 0.88
    beta_mu, beta_std = 4.0, 1.5
    capture = 0.65

    results = []
    for _ in range(N):
        cap = capital0
        peak = cap
        max_dd = 0
        wins = 0
        losses = 0
        total_pnl = 0
        total_fees = 0
        trade_pnls = []

        for d in range(days):
            n_sig = max(0, int(random.gauss(12, 5)))
            for _ in range(n_sig):
                btc = random.gauss(0, 0.005)
                if abs(btc) < 0.003:
                    continue
                if cap < pos_fixed_usd / leverage:
                    break  # not enough margin

                notional = pos_fixed_usd  # FIXED, not compounding
                beta = max(0.5, random.gauss(beta_mu, beta_std))
                follows = random.random() < corr

                if follows:
                    wif = abs(btc) * beta * capture * (1 + random.gauss(0, 0.25))
                    wif = min(wif, tp_pct)
                else:
                    wif = random.gauss(0, abs(btc) * beta * 0.3)
                    wif = max(wif, -sl_pct)
                    wif = min(wif, tp_pct)

                gross = notional * wif
                costs = notional * cost_pct
                net = gross - costs
                
                cap += net
                total_pnl += net
                total_fees += costs
                trade_pnls.append(net)
                if net > 0: wins += 1
                else: losses += 1

                if cap <= 0:
                    cap = 0; break
            
            if cap <= 0: break
            # funding (only on active position time, assume ~4h/day in position)
            cap -= pos_fixed_usd * 0.00005 * 1.5  # ~1.5 funding periods worth
            if cap > peak: peak = cap
            dd = (peak - cap) / peak if peak > 0 else 0
            if dd > max_dd: max_dd = dd

        n_trades = wins + losses
        results.append({
            "final": round(cap, 2),
            "pnl": round(total_pnl, 2),
            "fees": round(total_fees, 2),
            "dd": round(max_dd * 100, 1),
            "trades": n_trades,
            "wr": round(wins / max(1, n_trades) * 100, 1),
            "bust": cap <= 0,
            "avg_trade": round(total_pnl / max(1, n_trades), 2),
        })
    return results

def report(results, label, capital0):
    finals = sorted([r["final"] for r in results])
    pnls = sorted([r["pnl"] for r in results])
    n = len(finals)
    busts = sum(1 for r in results if r["bust"])
    wrs = [r["wr"] for r in results]
    trades = [r["trades"] for r in results]
    fees = [r["fees"] for r in results]
    avgt = [r["avg_trade"] for r in results]
    dds = [r["dd"] for r in results]

    print(f"\n{'='*65}")
    print(f"  {label}")
    print(f"{'='*65}")
    print(f"  Start: ${capital0:,}  |  Sims: {n}  |  30 days")
    print(f"  Avg trades/month: {statistics.mean(trades):.0f}  |  Win rate: {statistics.mean(wrs):.1f}%")
    print(f"  Avg P&L per trade: ${statistics.mean(avgt):.2f}")
    print(f"  Total fees/month: ${statistics.mean(fees):,.0f}")
    print()
    
    pct = lambda v: (v - capital0) / capital0 * 100
    
    print(f"  {'Outcome':16} {'Capital':>12} {'P&L':>12} {'Return':>8}")
    print(f"  {'─'*52}")
    print(f"  {'P5 (worst)':16} ${finals[int(n*0.05)]:>11,.0f} ${pnls[int(n*0.05)]:>11,.0f} {pct(finals[int(n*0.05)]):>+7.0f}%")
    print(f"  {'P10':16} ${finals[int(n*0.10)]:>11,.0f} ${pnls[int(n*0.10)]:>11,.0f} {pct(finals[int(n*0.10)]):>+7.0f}%")
    print(f"  {'P25':16} ${finals[int(n*0.25)]:>11,.0f} ${pnls[int(n*0.25)]:>11,.0f} {pct(finals[int(n*0.25)]):>+7.0f}%")
    print(f"  {'MEDIAN':16} ${statistics.median(finals):>11,.0f} ${statistics.median(pnls):>11,.0f} {pct(statistics.median(finals)):>+7.0f}%")
    print(f"  {'MEAN':16} ${statistics.mean(finals):>11,.0f} ${statistics.mean(pnls):>11,.0f} {pct(statistics.mean(finals)):>+7.0f}%")
    print(f"  {'P75':16} ${finals[int(n*0.75)]:>11,.0f} ${pnls[int(n*0.75)]:>11,.0f} {pct(finals[int(n*0.75)]):>+7.0f}%")
    print(f"  {'P90':16} ${finals[int(n*0.90)]:>11,.0f} ${pnls[int(n*0.90)]:>11,.0f} {pct(finals[int(n*0.90)]):>+7.0f}%")
    print(f"  {'P95 (best)':16} ${finals[int(n*0.95)]:>11,.0f} ${pnls[int(n*0.95)]:>11,.0f} {pct(finals[int(n*0.95)]):>+7.0f}%")
    print()
    print(f"  Max Drawdown: {statistics.mean(dds):.1f}% avg, {sorted(dds)[int(n*0.95)]:.1f}% P95")
    print(f"  Bust rate: {busts/n*100:.1f}%")
    print(f"  Profit prob: {sum(1 for f in finals if f > capital0)/n*100:.1f}%")
    
    return {"label": label, "median": statistics.median(finals), "mean": statistics.mean(finals),
            "p5": finals[int(n*0.05)], "p95": finals[int(n*0.95)],
            "profit_prob": sum(1 for f in finals if f > capital0)/n*100,
            "bust_rate": busts/n*100}

if __name__ == "__main__":
    C = 1000
    print("🎲 WIF LAG TRADING SIMULATION — Gate.io 50x")
    print(f"   Signal: BTC Futures (Binance) → WIF Futures (Gate.io)")
    print(f"   Lag: 28s | Corr: 0.88 | WIF β: ~4× BTC")
    print(f"   Capital: ${C:,} | Fixed position per trade")

    # $500 notional per trade (10x effective on $1000)
    r1 = sim(C, leverage=50, pos_fixed_usd=500, sl_pct=0.03, tp_pct=0.04, slip_bps=15)
    s1 = report(r1, "SAFE: $500/trade (10x eff.), SL 3%, TP 4%", C)

    # $2500 notional (50x on half capital)
    r2 = sim(C, leverage=50, pos_fixed_usd=2500, sl_pct=0.025, tp_pct=0.04, slip_bps=20)
    s2 = report(r2, "MODERATE: $2,500/trade (50x × 50%), SL 2.5%, TP 4%", C)

    # $5000 notional (50x on full capital)
    r3 = sim(C, leverage=50, pos_fixed_usd=5000, sl_pct=0.02, tp_pct=0.04, slip_bps=20)
    s3 = report(r3, "AGGRESSIVE: $5,000/trade (50x × 100%), SL 2%, TP 4%", C)

    # $25000 notional (max leverage, $500 margin)
    r4 = sim(C, leverage=50, pos_fixed_usd=25000, sl_pct=0.015, tp_pct=0.05, slip_bps=25)
    s4 = report(r4, "YOLO: $25,000/trade (50x × $500 margin), SL 1.5%, TP 5%", C)

    # $50000 notional (max leverage on full $1000)
    r5 = sim(C, leverage=50, pos_fixed_usd=50000, sl_pct=0.01, tp_pct=0.05, slip_bps=30)
    s5 = report(r5, "MAX DEGEN: $50,000/trade (full 50x), SL 1%, TP 5%", C)

    # Per-trade breakdown
    print(f"\n{'='*65}")
    print(f"  💰 PER-TRADE P&L (single trade, WIF follows signal)")
    print(f"{'='*65}")
    
    for pos_label, notional in [("$500", 500), ("$2,500", 2500), ("$5,000", 5000), 
                                 ("$25,000", 25000), ("$50,000", 50000)]:
        margin = notional / 50
        print(f"\n  Position: {pos_label} notional (${margin:.0f} margin at 50x)")
        for btc_label, btc in [("0.3%", 0.003), ("0.5%", 0.005), ("1.0%", 0.01)]:
            wif = btc * 4 * 0.65  # beta × capture
            gross = notional * wif
            costs = notional * 0.0019  # fees + slip
            net = gross - costs
            print(f"    BTC {btc_label} → WIF {wif*100:.1f}%: net ${net:+,.0f} (margin ${margin:.0f})")
    
    print(f"\n  ⚠️  LIQUIDATION: WIF 2% adverse = 100% loss at 50x")
    print(f"  ⚠️  BTC 0.5% wrong → WIF ~2% wrong → LIQUIDATED at 50x")
    print(f"  ⚠️  WIF spread on Gate.io: 0.1-0.5% (thin book!)")
    
    # Realistic daily estimate
    print(f"\n{'='*65}")
    print(f"  📊 REALISTIC DAILY ESTIMATE")
    print(f"{'='*65}")
    print(f"  Assumptions: 6 tradeable signals/day, 88% hit rate")
    print(f"  avg BTC signal: 0.4%, WIF response: ~1.0% (after capture)")
    print()
    
    for pos_label, notional in [("$2,500", 2500), ("$5,000", 5000), ("$25,000", 25000)]:
        margin = notional / 50
        avg_gross = notional * 0.01 * 0.88  # 1% move × 88% hit rate
        avg_loss = notional * 0.005 * 0.12  # 0.5% avg loss × 12% miss rate
        costs = notional * 0.0019 * 6       # 6 trades
        daily_net = (avg_gross - avg_loss) * 6 - costs
        monthly = daily_net * 30
        print(f"  {pos_label} position (${margin:.0f} margin):")
        print(f"    Daily: ~${daily_net:+,.0f}  |  Monthly: ~${monthly:+,.0f}")
        print(f"    Monthly ROI on $1000 capital: {monthly/1000*100:+.0f}%")
        print()

    all_res = {"safe": s1, "moderate": s2, "aggressive": s3, "yolo": s4, "max_degen": s5}
    with open("/home/tank/crypto-bot-data/cross-venue-lag/results/wif_simulation_results.json", "w") as f:
        json.dump(all_res, f, indent=2)
    print(f"  Saved → wif_simulation_results.json ✅")
