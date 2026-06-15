#!/usr/bin/env python3
"""Kickbacks Dashboard — real-time financial overview."""
import json, os, sys
from datetime import datetime

LEDGER     = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')
GROSS_CPM  = float(os.environ.get('KICKBACKS_CPM', '5.0'))
SPLIT      = 0.50

def fmt_usd(n): return f"${n:.6f}" if abs(n) < 1 else f"${n:.2f}"

def main():
    lines = []
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            lines = [json.loads(l) for l in f if l.strip()]
    if not lines:
        print("No data yet. Proxy has not processed any queries."); return

    n            = len(lines)
    total_cost   = sum(l.get('cost_usd', 0)     for l in lines)
    total_ms     = sum(l.get('thinking_ms', 0)  for l in lines)
    total_input  = sum(l.get('input_tokens', 0)  for l in lines)
    total_output = sum(l.get('output_tokens', 0) for l in lines)
    free_count   = sum(1 for l in lines if l.get('free'))

    impressions  = total_ms / 5000.0
    est_revenue  = impressions * (GROSS_CPM / 1000.0)
    est_earnings = est_revenue * SPLIT
    margin       = ((est_earnings - total_cost) / est_earnings * 100) if est_earnings > 0 else 0

    models = {}
    for l in lines:
        m = l.get('model_actual', 'unknown')
        models.setdefault(m, {'q': 0, 'ms': 0, 'cost': 0.0})
        models[m]['q']    += 1
        models[m]['ms']   += l.get('thinking_ms', 0)
        models[m]['cost'] += l.get('cost_usd', 0)

    first_ts = lines[0].get('ts', '')
    last_ts  = lines[-1].get('ts', '')

    print(f"\n{'='*52}")
    print(f"  Kickbacks Arbitrage Dashboard")
    print(f"{'='*52}")
    print(f"  Queries:          {n}  ({free_count} free / {n-free_count} paid)")
    print(f"  Thinking:         {total_ms/1000:.1f}s total  ({total_ms/n/1000:.1f}s avg)")
    print(f"  Impressions:      {impressions:.0f}  (@5s each, CPM ${GROSS_CPM:.2f})")
    print()
    print(f"  Revenue (est.):")
    print(f"    Gross:          {fmt_usd(est_revenue)}")
    print(f"    Your 50%:       {fmt_usd(est_earnings)}")
    print()
    print(f"  Cost:             {fmt_usd(total_cost)}  (avg {fmt_usd(total_cost/n)}/query)")
    print(f"  Arbitrage Margin: {margin:.0f}%")
    print()
    print(f"  Tokens:           {total_input:,} in + {total_output:,} out")
    print(f"  Period:           {first_ts[:19]} to {last_ts[:19]}")
    print()

    if models:
        print(f"  Models:")
        for m, d in sorted(models.items(), key=lambda x: -x[1]['ms']):
            tag = "free" if d['cost'] == 0 else "paid"
            pct = d['q'] / n * 100
            print(f"    [{tag}] {m[:42]:42s} {d['q']:3d}x ({pct:3.0f}%)  {d['ms']/1000:7.1f}s  {fmt_usd(d['cost'])}")
        print()

    if n >= 3:
        elapsed_h       = (datetime.fromisoformat(last_ts) - datetime.fromisoformat(first_ts)).total_seconds() / 3600
        rate            = n / elapsed_h if elapsed_h > 0 else 0
        projected_daily = rate * 24
        daily_rev       = projected_daily * (total_ms / n / 1000 / 5 * (GROSS_CPM / 1000) * SPLIT)
        print(f"  Projections:")
        print(f"    Queries/day:         {projected_daily:.0f}")
        print(f"    Est. daily earnings: {fmt_usd(daily_rev)}")
        print(f"    Est. monthly:        {fmt_usd(daily_rev * 30)}")
        print()

if __name__ == '__main__':
    main()
