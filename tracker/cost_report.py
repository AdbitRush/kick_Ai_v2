#!/usr/bin/env python3
"""Detailed per-query cost & model report.

Usage:
    python3 tracker/cost_report.py
    python3 tracker/cost_report.py --date 2026-06-14
    python3 tracker/cost_report.py --csv report.csv
"""
import json, os, sys, argparse
from collections import defaultdict

LEDGER = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')
parser = argparse.ArgumentParser()
parser.add_argument('--date', help='Filter by date (YYYY-MM-DD)')
parser.add_argument('--csv',  help='Write detail table to CSV')
args = parser.parse_args()

if not os.path.exists(LEDGER):
    sys.stderr.write(f"Ledger not found: {LEDGER}\n"); sys.exit(1)

entries = []
with open(LEDGER) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if args.date and not obj.get('ts','').startswith(args.date):
            continue
        entries.append(obj)

if not entries:
    print('No entries match.'); sys.exit(0)

total_q    = len(entries)
total_in   = sum(e.get('input_tokens', 0)  for e in entries)
total_out  = sum(e.get('output_tokens', 0) for e in entries)
total_cost = sum(e.get('cost_usd', 0.0)   for e in entries)

def fmt_usd(v): return f"${v:.6f}" if abs(v) < 1 else f"${v:,.2f}"
def fmt_num(n): return f"{n:,}"

print('=== Kickbacks Cost & Model Report ===')
print(f'Queries:       {fmt_num(total_q)}')
print(f'Input tokens:  {fmt_num(total_in)}')
print(f'Output tokens: {fmt_num(total_out)}')
print(f'Total cost:    {fmt_usd(total_cost)}')
print()

header = ['#', 'timestamp', 'model_actual', 'cost_usd', 'input', 'output']
rows = [[str(i), e.get('ts',''), e.get('model_actual','unknown'),
         fmt_usd(e.get('cost_usd',0.0)), fmt_num(e.get('input_tokens',0)),
         fmt_num(e.get('output_tokens',0))] for i, e in enumerate(entries, 1)]

col_w   = [max(len(r[i]) for r in ([header]+rows)) for i in range(len(header))]
row_fmt = '  '.join(f'{{:<{w}}}' for w in col_w)
print(row_fmt.format(*header))
print('-' * (sum(col_w) + 2*(len(header)-1)))
for r in rows: print(row_fmt.format(*r))
print()

if args.csv:
    import csv
    with open(args.csv, 'w', newline='') as cf:
        csv.writer(cf).writerows([header] + rows)
    print(f'CSV written to {args.csv}')

model_stats = defaultdict(lambda: {'q':0,'in':0,'out':0,'cost':0.0})
for e in entries:
    st = model_stats[e.get('model_actual','unknown')]
    st['q'] += 1; st['in'] += e.get('input_tokens',0)
    st['out'] += e.get('output_tokens',0); st['cost'] += e.get('cost_usd',0.0)

print('By model:')
for model, st in sorted(model_stats.items(), key=lambda kv: -kv[1]['cost']):
    pct = (st['cost'] / total_cost * 100) if total_cost else 0.0
    print(f'  {model:50s} {fmt_num(st["q"])} q  {fmt_usd(st["cost"])} ({pct:.1f}%)')
