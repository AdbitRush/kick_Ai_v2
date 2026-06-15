#!/usr/bin/env python3
"""Quick proxy health + stats check."""
import urllib.request, json, sys, os

PORT   = os.environ.get('PROXY_PORT', '5555')
LEDGER = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')

def check_proxy():
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/v1/messages",
            data=b'{"model":"health","messages":[{"role":"user","content":"ping"}]}',
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
        return f"Proxy :{PORT} — alive"
    except Exception as e:
        return f"Proxy :{PORT} — DOWN: {e}"

def summary():
    lines = []
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            lines = [json.loads(l) for l in f if l.strip()]
    total = sum(l.get('cost_usd', 0) for l in lines)
    ms    = sum(l.get('thinking_ms', 0) for l in lines)
    return f"{len(lines)} queries | {ms/1000:.1f}s thinking | ${total:.6f} cost"

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd in ('proxy', 'all'): print(check_proxy())
    if cmd in ('stats', 'all'): print(summary())
