#!/usr/bin/env python3
"""Kickbacks Arbitrage Engine — zero-cost free model proxy + financial tracking

Bridges the Anthropic Messages API to OpenRouter's free model tier. Free models
are slow, which is good: the Claude Code spinner runs longer = more ad
impressions = more Kickbacks revenue, while you pay $0 for inference.

Key features:
  * Concurrent model racing — all healthy free models are called simultaneously
    and the first successful response wins (big latency win vs. sequential).
  * Per-model health tracking — models that fail/rate-limit repeatedly are
    temporarily skipped so the race isn't slowed down by dead endpoints.
  * Request-ID tracking for debugging across the ledger and logs.
  * Rich /metrics endpoint for dashboards, plus /stats and /health.
"""
import http.server
import socketserver
import json
import urllib.request
import urllib.error
import ssl
import sys
import os
import time
import datetime
import atexit
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    OR_KEY = os.environ['OPENROUTER_API_KEY']
except KeyError:
    OR_KEY = ''

PORT   = int(os.environ.get('PROXY_PORT', '5555'))
# Default to the home dir so the ledger survives reboots (/tmp gets wiped).
LEDGER = os.environ.get(
    'LEDGER_PATH',
    os.path.join(os.path.expanduser('~'), 'kickbacks_ledger.jsonl'),
)
STATUS_FILE = os.environ.get(
    'STATUS_PATH',
    os.path.join(os.path.expanduser('~'), 'kickbacks_status.txt'),
)

# Largest free models = slowest responses = most ad impressions per query.
#
# Checked against https://openrouter.ai/api/v1/models on 2026-08-14: four of the
# five slugs previously listed here had been retired and returned nothing —
# llama-3.3-70b-instruct:free, qwen3-coder:free, qwen-2.5-72b-instruct:free and
# deepseek-chat-v3-5:free. Only the nemotron ultra was still real, so the race
# was firing four dead requests per query and the "last resort" was dead too.
#
# Re-verify before assuming a failure is a bug: OpenRouter retires free slugs
# regularly, and a retired slug looks exactly like a rate-limited one from here.
#   curl -s https://openrouter.ai/api/v1/models | grep ':free'
#
# Ordered largest first, which is also slowest first, which is the point.
FREE_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",   # 550B, 1M ctx
    "nvidia/nemotron-3-super-120b-a12b:free",   # 120B, 262k
    "google/gemma-4-31b-it:free",               #  31B, 262k
    "nvidia/nemotron-3-nano-30b-a3b:free",      #  30B, 256k
    "openai/gpt-oss-20b:free",                  #  20B, 131k
]
# Last resort only. Also a :free slug — nothing in this proxy may reach a billed
# endpoint, which is the whole premise of the engine.
PAID_MODEL      = "nvidia/nemotron-nano-9b-v2:free"
PAID_COST_PER_M = (0.0, 0.0)                    # free tier: nothing is billed

# Race all healthy free models at once; first to succeed wins.
CONCURRENT_RACE = os.environ.get('CONCURRENT_RACE', '1') not in ('0', 'false', 'False')
UPSTREAM_TIMEOUT = int(os.environ.get('UPSTREAM_TIMEOUT', '180'))
MAX_TOKENS_CAP   = int(os.environ.get('MAX_TOKENS_CAP', '8192'))

# Health tracking: skip models whose recent failure rate is too high.
HEALTH_WINDOW       = 20      # consider last N attempts per model
HEALTH_MIN_SAMPLES  = 5       # need at least this many before we'll skip a model
HEALTH_FAIL_CUTOFF  = 0.8     # skip if >=80% of recent attempts failed
HEALTH_COOLDOWN_SEC = 120     # ...but retry an unhealthy model after this long

_lock = threading.Lock()
q = 0
total_cost = 0.0
total_thinking_ms = 0
rate_limit_counts = {}
start_time = time.time()

# Per-model rolling health: recent outcomes (True=ok), last failure time, totals.
model_health = {
    m: {"recent": [], "ok": 0, "fail": 0, "last_fail_ts": 0.0, "last_ok_ts": 0.0}
    for m in FREE_MODELS + [PAID_MODEL]
}


def _record_health(model, ok):
    h = model_health.setdefault(
        model, {"recent": [], "ok": 0, "fail": 0, "last_fail_ts": 0.0, "last_ok_ts": 0.0}
    )
    h["recent"].append(bool(ok))
    if len(h["recent"]) > HEALTH_WINDOW:
        h["recent"].pop(0)
    if ok:
        h["ok"] += 1
        h["last_ok_ts"] = time.time()
    else:
        h["fail"] += 1
        h["last_fail_ts"] = time.time()


def _is_healthy(model):
    """Return False only if the model has been reliably failing recently and is
    still inside its cooldown window."""
    h = model_health.get(model)
    if not h or len(h["recent"]) < HEALTH_MIN_SAMPLES:
        return True
    fail_rate = h["recent"].count(False) / len(h["recent"])
    if fail_rate < HEALTH_FAIL_CUTOFF:
        return True
    # Unhealthy — but allow a probe after the cooldown elapses.
    return (time.time() - h["last_fail_ts"]) > HEALTH_COOLDOWN_SEC


def _healthy_models():
    healthy = [m for m in FREE_MODELS if _is_healthy(m)]
    return healthy or list(FREE_MODELS)  # never return empty


def append_ledger(d):
    with _lock:
        with open(LEDGER, 'a') as f:
            f.write(json.dumps(d) + '\n')


def write_status():
    elapsed = time.time() - start_time
    try:
        with open(STATUS_FILE, 'w') as f:
            f.write(f"Kickbacks Arbitrage\nUptime: {elapsed/3600:.1f}h\nQueries: {q}\n"
                    f"Thinking: {total_thinking_ms/1000:.1f}s\nCost: ${total_cost:.6f}\n")
    except OSError:
        pass


atexit.register(write_status)


def get_stats():
    elapsed = time.time() - start_time
    impressions = total_thinking_ms / 5000.0
    return {
        "uptime_h":       round(elapsed / 3600, 2),
        "queries":        q,
        "thinking_s":     round(total_thinking_ms / 1000, 1),
        "impressions":    round(impressions, 1),
        "est_earnings":   round(impressions * 0.0025, 6),
        "cost_usd":       round(total_cost, 6),
        "free_models":    FREE_MODELS,
        "rate_limits":    rate_limit_counts,
    }


def get_metrics():
    """Richer payload for dashboards: live stats + per-model health detail."""
    elapsed = max(time.time() - start_time, 1e-9)
    impressions = total_thinking_ms / 5000.0
    avg_ms = (total_thinking_ms / q) if q else 0
    models = {}
    for m, h in model_health.items():
        attempts = h["ok"] + h["fail"]
        recent = h["recent"]
        models[m] = {
            "ok": h["ok"],
            "fail": h["fail"],
            "attempts": attempts,
            "success_rate": round(h["ok"] / attempts, 3) if attempts else None,
            "recent_success_rate": round(recent.count(True) / len(recent), 3) if recent else None,
            "healthy": _is_healthy(m),
            "rate_limited": rate_limit_counts.get(m, 0),
        }
    return {
        "uptime_h":         round(elapsed / 3600, 3),
        "queries":          q,
        "queries_per_hour": round(q / (elapsed / 3600), 2),
        "thinking_s":       round(total_thinking_ms / 1000, 1),
        "avg_thinking_ms":  round(avg_ms, 1),
        "impressions":      round(impressions, 1),
        "est_earnings_usd": round(impressions * 0.0025, 6),
        "cost_usd":         round(total_cost, 6),
        "concurrent_race":  CONCURRENT_RACE,
        "max_tokens_cap":   MAX_TOKENS_CAP,
        "ledger_path":      LEDGER,
        "models":           models,
        "rate_limits":      rate_limit_counts,
        "started_at":       datetime.datetime.utcfromtimestamp(start_time).isoformat() + "Z",
    }


class P(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/stats', '/health'):
            self._send(200, get_stats())
        elif self.path == '/metrics':
            self._send(200, get_metrics())
        else:
            self._send(404, {"error": "not found"})

    def do_HEAD(self):
        # HEAD must not include a body. Send headers only.
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        global q, total_cost, total_thinking_ms
        req_id = uuid.uuid4().hex[:12]
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        try:
            msg = json.loads(body)
        except Exception:
            return self._send(400, {"type": "error", "error": {"message": "bad json"}})

        om  = msg.get('model', 'claude-sonnet-4-20250514')
        oai = self._to_openai(msg)
        mt  = min(msg.get('max_tokens', 2048), MAX_TOKENS_CAP)

        t1 = time.time()
        used, is_free, model_cost, res = None, False, 0.0, None

        if CONCURRENT_RACE:
            used, res = self._race(_healthy_models(), oai, mt, req_id)
            if used:
                is_free = True
        else:
            offset  = q % len(FREE_MODELS)
            ordered = [m for m in (FREE_MODELS[offset:] + FREE_MODELS[:offset]) if _is_healthy(m)]
            for model in ordered or FREE_MODELS:
                r = self._call(model, oai, mt)
                if r and r.get('choices'):
                    used, is_free, res = model, True, r
                    _record_health(model, True)
                    break
                _record_health(model, False)
                self._note_rate_limit(model, r)

        # Last-resort fallback model.
        if not used:
            r = self._call(PAID_MODEL, oai, mt)
            if r and r.get('choices'):
                used, is_free, res = PAID_MODEL, True, r
                _record_health(PAID_MODEL, True)
                u  = r.get('usage', {}) or {}
                pt = int(u.get('prompt_tokens', 0) or 0)
                ct = int(u.get('completion_tokens', 0) or 0)
                model_cost = (pt * PAID_COST_PER_M[0]) + (ct * PAID_COST_PER_M[1])
            else:
                _record_health(PAID_MODEL, False)
                res = r

        ms = int((time.time() - t1) * 1000)
        with _lock:
            q += 1
            total_thinking_ms += ms
            total_cost += model_cost
            cur_q = q

        if used and res and res.get('choices'):
            u = res.get('usage', {}) or {}
            append_ledger({
                'ts': datetime.datetime.utcnow().isoformat(),
                'request_id': req_id,
                'q': cur_q,
                'model_actual': used,
                'model_claude': om,
                'free': is_free,
                'input_tokens':  int(u.get('prompt_tokens', 0) or 0),
                'output_tokens': int(u.get('completion_tokens', 0) or 0),
                'thinking_ms': ms,
                'duration_sec': round(ms / 1000.0, 3),  # compat for finance module
                'cost_usd': round(model_cost, 8),
            })
            self._send(200, self._to_anthropic(res, om, ms, used, req_id), req_id)
        else:
            err = str(res.get('error', 'all models failed'))[:200] if res else 'no response'
            self._send(502, {"type": "error", "error": {"message": err}}, req_id)

    # ── upstream calling ─────────────────────────────────────────────────────
    def _note_rate_limit(self, model, r):
        if r and isinstance(r.get('error'), (str, dict)):
            err_str = str(r.get('error', ''))
            if '429' in err_str or 'rate' in err_str.lower():
                with _lock:
                    rate_limit_counts[model] = rate_limit_counts.get(model, 0) + 1

    def _race(self, models, messages, max_tokens, req_id):
        """Fire all candidate models concurrently; return (model, response) for
        the first that yields choices. We do NOT block on the stragglers — any
        futures not yet resolved when we find a winner are drained in a background
        thread (which records their health) — so the caller gets the fastest
        successful response without waiting for slow/failed models."""
        if not models:
            return None, None
        ex = ThreadPoolExecutor(max_workers=len(models))
        futures = {ex.submit(self._call, m, messages, max_tokens): m for m in models}
        handled = set()  # futures whose health we've already recorded

        def _drain(pending):
            for fut in as_completed(pending):
                model = pending[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    r = {"error": str(e)}
                if r and r.get('choices'):
                    _record_health(model, True)
                else:
                    _record_health(model, False)
                    self._note_rate_limit(model, r)
            ex.shutdown(wait=False)

        winner_model, winner_res = None, None
        for fut in as_completed(futures):
            model = futures[fut]
            handled.add(fut)
            try:
                r = fut.result()
            except Exception as e:
                r = {"error": str(e)}
            if r and r.get('choices'):
                _record_health(model, True)
                winner_model, winner_res = model, r
                break
            _record_health(model, False)
            self._note_rate_limit(model, r)

        pending = {f: m for f, m in futures.items() if f not in handled}
        if pending:
            threading.Thread(target=_drain, args=(pending,), daemon=True).start()
        else:
            ex.shutdown(wait=False)
        return winner_model, winner_res

    def _call(self, model, messages, max_tokens):
        payload = json.dumps({
            "model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": 0.7,
        }).encode('utf-8')
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {OR_KEY}",
                "HTTP-Referer":  "https://kickbacks.ai",
                "X-Title":       "Kick_and_backoff",
            },
        )
        try:
            ctx = ssl.create_default_context()
            return json.loads(urllib.request.urlopen(req, context=ctx, timeout=UPSTREAM_TIMEOUT).read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except Exception:
                return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": str(e)}

    # ── format conversion ────────────────────────────────────────────────────
    def _to_openai(self, msg):
        msgs = []
        sys_t = None
        if 'system' in msg:
            t = msg['system']
            sys_t = t if isinstance(t, str) else ' '.join(
                b.get('text', '') for b in t if isinstance(b, dict) and b.get('type') == 'text')
        for m in msg.get('messages', []):
            c = m.get('content', '')
            if isinstance(c, list):
                c = '\n'.join(b.get('text', '') for b in c if isinstance(b, dict) and b.get('type') == 'text')
            msgs.append({"role": m['role'], "content": c or ''})
        if sys_t:
            msgs.insert(0, {"role": "system", "content": sys_t})
        return msgs

    def _to_anthropic(self, r, om, ms, used, req_id):
        c    = r.get('choices', [{}])[0]
        text = (c.get('message', {}) or {}).get('content', '') or ''
        u    = r.get('usage', {}) or {}
        return {
            "id": r.get('id', f'msg_{req_id}'), "type": "message", "role": "assistant",
            "content": [{"type": "text", "text": text}], "model": om,
            "stop_reason": c.get('finish_reason', 'end_turn'), "stop_sequence": None,
            "usage": {
                "input_tokens":     int(u.get('prompt_tokens', 0) or 0),
                "output_tokens":    int(u.get('completion_tokens', 0) or 0),
                "thinking_time_ms": ms,
            },
            "_kickbacks": {"model_actual": used, "request_id": req_id},
        }

    def _send(self, code, data, req_id=None):
        b = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        if req_id:
            self.send_header('X-Kickbacks-Request-Id', req_id)
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, fmt, *a):
        pass


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    if not OR_KEY:
        print("FATAL: OPENROUTER_API_KEY not set")
        sys.exit(1)
    sv = ThreadingServer(('127.0.0.1', PORT), P)
    mode = "concurrent race" if CONCURRENT_RACE else "sequential"
    print(f"Arbitrage Proxy :{PORT} | {len(FREE_MODELS)} free models | {mode} | "
          f"/stats /metrics for live data | ledger: {LEDGER}")
    write_status()
    sv.serve_forever()
