#!/usr/bin/env python3
"""Quick current cost & revenue snapshot."""
import json, os, sys
from collections import defaultdict

LEDGER    = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')
GROSS_CPM = float(os.environ.get('KICKBACKS_CPM', '5.0'))

if not os.path.exists(LEDGER):
    sys.stderr.write(f"Ledger not found: {LEDGER}\n"); sys.exit(1)

entries = []
with open(LEDGER) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try: entries.append(json.loads(line))
        except: continue

if not entries:
    print('No entries in ledger.'); sys.exit(0)

total_q        = len(entries)
total_in       = sum(e.get('input_tokens',0)  for e in entries)
total_out      = sum(e.get('output_tokens',0) for e in entries)
total_cost     = sum(e.get('cost_usd',0.0)   for e in entries)
total_think_ms = sum(e.get('thinking_ms',0)   for e in entries)

impressions  = total_think_ms / 5000.0
revenue_usd  = impressions * (GROSS_CPM / 1000.0)
earnings_usd = revenue_usd * 0.5

def fmt_usd(v): return f"${v:.6f}" if abs(v) < 1 else f"${v:,.2f}"
def fmt_num(n): return f"{n:,}"

print('=== Kickbacks Snapshot ===')
print(f'Queries:       {fmt_num(total_q)}')
print(f'Input tokens:  {fmt_num(total_in)}')
print(f'Output tokens: {fmt_num(total_out)}')
print(f'Cost:          {fmt_usd(total_cost)}')
print(f'Est. revenue:  {fmt_usd(revenue_usd)}  (@ ${GROSS_CPM:.2f} CPM)')
print(f'Your 50%:      {fmt_usd(earnings_usd)}')
print()

model_stats = defaultdict(lambda: {'q':0,'cost':0.0})
for e in entries:
    st = model_stats[e.get('model_actual','unknown')]
    st['q'] += 1; st['cost'] += e.get('cost_usd',0.0)

print('By model:')
for model, st in sorted(model_stats.items(), key=lambda kv: -kv[1]['cost']):
    pct = (st['cost'] / total_cost * 100) if total_cost else 0.0
    print(f'  {model:50s} {fmt_num(st["q"])} q  {fmt_usd(st["cost"])} ({pct:.1f}%)')
