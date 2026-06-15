#!/usr/bin/env python3
"""
Coffee Brake — human-mimicking impression generator for Kickbacks.ai

Runs `claude -p "query"` through the proxy in bursts with jittered timing.
Mimics real developer work patterns: burst of queries → coffee break → repeat.

Usage:
  python3 scripts/coffee-brake.py              # single query now
  python3 scripts/coffee-brake.py --daemon     # continuous loop
  python3 scripts/coffee-brake.py --health     # check if daemon is running
  python3 scripts/coffee-brake.py --stop       # stop the daemon
"""

import subprocess, json, random, time, datetime, os, sys, signal, atexit

WORKDIR  = os.environ.get('CLAUDE_WORKDIR', '/tmp/testproj')
LEDGER   = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')
PID_FILE = '/tmp/coffee_brake.pid'

# ── Query library ─────────────────────────────────────────────────────────────
# Weighted: DEEP queries preferred — longer thinking = more impressions

DEEP = [
    "Think through the design of a rate-limiting system for a distributed API. Consider token bucket vs leaky bucket algorithms, Redis-based implementation, and backpressure handling. Walk through your reasoning step by step.",
    "Analyze the tradeoffs between microservices and monolith architectures for a SaaS platform. Consider team size, deployment complexity, data consistency, and evolutionary architecture. Think step by step.",
    "Design a caching strategy for a high-traffic e-commerce website. Consider CDN, Redis, database query caching, cache invalidation (write-through, cache-aside), and cache stampedes. Think through each layer.",
    "Compare WebSocket, Server-Sent Events, and long-polling for real-time data delivery. Analyze connection overhead, browser support, reconnection handling, and scaling. Think carefully about use cases.",
    "Design a fault-tolerant message queue. Consider at-least-once vs exactly-once delivery, consumer group rebalancing, dead letter queues, and backpressure. Reason through the architecture step by step.",
    "How would you architect a system to detect and prevent duplicate payment processing? Consider idempotency keys, database constraints, distributed locking, and race conditions. Think carefully.",
    "Design a full-text search system for 10M documents. Consider inverted indexes, TF-IDF vs BM25, fuzzy search, sharding, and real-time indexing. Work through each component.",
    "Analyze OAuth 2.0 authorization code flow with PKCE. Walk through each step and explain what threat each component protects against. Think step by step.",
    "Design a real-time collaborative editing system like Google Docs. Consider OT vs CRDTs, conflict resolution, cursor sync, offline support, and scalability.",
    "Design an API gateway for microservices. Consider request routing, rate limiting, JWT validation, circuit breaking, and observability. Think through each concern.",
]

MEDIUM = [
    "Compare SQL vs NoSQL databases. When would you choose each? Consider consistency, scalability, query flexibility, and operational complexity.",
    "How would you implement authentication in a REST API? Compare JWT vs session-based approaches and security considerations.",
    "Design a URL shortener like bit.ly. Consider hash generation, database schema, redirect strategy, analytics, and scaling.",
    "Explain the CAP theorem and its implications for distributed database design with concrete examples.",
    "How does a CDN work? Walk through request routing, cache hierarchy, cache invalidation, and dynamic content acceleration.",
    "Design a logging and monitoring system for a Kubernetes cluster. Consider log aggregation, metrics, alerting, and distributed tracing.",
    "Compare REST vs GraphQL. Analyze over-fetching, under-fetching, caching complexity, and when each excels.",
    "How would you implement a feature flag system? Consider targeting rules, percentage rollout, evaluation performance, and flag cleanup.",
    "Design a zero-downtime database migration strategy with backward-compatible schema changes.",
    "Explain quorum-based consensus. Compare Raft, Paxos, and Zab — their similarities and tradeoffs in production.",
]

QUICK = [
    "Explain what a closure is in JavaScript. Keep it concise.",
    "What's the difference between let, const, and var in JavaScript?",
    "Briefly explain hoisting in JavaScript.",
    "What is a Promise in JavaScript? Simple explanation.",
    "Explain the Event Loop in one paragraph.",
    "What is the difference between == and === in JavaScript?",
    "What is the difference between null and undefined?",
    "Explain what RESTful API means briefly.",
    "What's the difference between TCP and UDP?",
    "What are the SOLID principles? One sentence each.",
]

# Weights: heavily prefer deep queries (max thinking time)
CATEGORIES = [QUICK, MEDIUM, DEEP]
WEIGHTS    = [1, 3, 7]

# ── Timing ───────────────────────────────────────────────────────────────────
BURST_SIZE      = (1, 4)        # queries per burst
BURST_GAP       = (30, 180)     # seconds between queries within a burst
COFFEE_BREAK    = (180, 900)    # seconds between bursts (3-15 min)
LONG_BREAK_EVERY = (5, 10)      # take a long break every N bursts
LONG_BREAK      = (1800, 7200)  # 30min-2h (lunch, meeting)

runs = 0; total_ms = 0; burst_count = 0
is_running = False; start_time = time.time()


def jitter(val, pct=0.3):
    return val * random.uniform(1 - pct, 1 + pct)


def pick_query():
    cat = random.choices(CATEGORIES, weights=WEIGHTS, k=1)[0]
    return random.choice(cat)


def run_query(query):
    global runs, total_ms
    depth = 'deep' if query in DEEP else ('medium' if query in MEDIUM else 'quick')
    marker = {'deep': '[D]', 'medium': '[M]', 'quick': '[Q]'}[depth]
    print(f"  {marker} {query[:65]}...")

    env = os.environ.copy()
    env.setdefault('ANTHROPIC_BASE_URL', 'http://127.0.0.1:5555')
    env.setdefault('ANTHROPIC_AUTH_TOKEN', 'kickbacks-proxy')

    t0 = time.time()
    try:
        subprocess.run(
            ['claude', '-p', query],
            capture_output=True,
            timeout=300,
            cwd=WORKDIR,
            env=env,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  warn: {e}")

    elapsed_ms = int((time.time() - t0) * 1000)
    runs += 1; total_ms += elapsed_ms

    with open(LEDGER, 'a') as f:
        f.write(json.dumps({
            'ts': datetime.datetime.utcnow().isoformat(),
            'q': runs, 'type': 'coffee_brake', 'depth': depth,
            'thinking_ms': elapsed_ms, 'cost_usd': 0.0,
            'query_preview': query[:80],
        }) + '\n')

    print(f"  done in {elapsed_ms/1000:.1f}s")
    return elapsed_ms


def status():
    elapsed = time.time() - start_time
    impressions = total_ms / 5000.0
    print(f"  {runs} queries | {total_ms/1000:.0f}s thinking | "
          f"{impressions:.0f} impressions | est ${impressions*0.0025:.4f} | "
          f"{elapsed/60:.0f}min uptime")


def run_daemon():
    global is_running, burst_count, start_time

    signal.signal(signal.SIGINT,  lambda s, f: stop())
    signal.signal(signal.SIGTERM, lambda s, f: stop())
    is_running = True; start_time = time.time()

    with open(PID_FILE, 'w') as f: f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(PID_FILE) and os.remove(PID_FILE))

    print(f"Coffee Brake daemon started (PID {os.getpid()})")
    print(f"Proxy: {os.environ.get('ANTHROPIC_BASE_URL', 'http://127.0.0.1:5555')}")

    while is_running:
        burst_count += 1
        size = random.randint(*BURST_SIZE)
        print(f"\n-- Burst #{burst_count}: {size} queries --")

        for i in range(size):
            if not is_running: break
            run_query(pick_query())
            if i < size - 1 and is_running:
                gap = jitter(random.uniform(*BURST_GAP))
                print(f"  next in {gap:.0f}s")
                _sleep(gap)

        if not is_running: break
        if burst_count % random.randint(*LONG_BREAK_EVERY) == 0:
            pause = jitter(random.uniform(*LONG_BREAK))
            print(f"\n  long break {pause/60:.0f}m"); status()
        else:
            pause = jitter(random.uniform(*COFFEE_BREAK))
            print(f"\n  coffee break {pause/60:.1f}m"); status()
        _sleep(pause)

    print("\nCoffee Brake stopped."); status()


def _sleep(seconds):
    slept = 0
    while slept < seconds and is_running:
        time.sleep(min(10, seconds - slept)); slept += 10


def stop():
    global is_running
    print("\nStopping..."); is_running = False


if __name__ == '__main__':
    args = sys.argv[1:]

    if '--daemon' in args:
        os.makedirs(WORKDIR, exist_ok=True)
        run_daemon()

    elif '--stop' in args:
        if os.path.exists(PID_FILE):
            pid = int(open(PID_FILE).read().strip())
            try: os.kill(pid, signal.SIGTERM); print(f"Stopped PID {pid}")
            except ProcessLookupError: print("Process not found")
            os.remove(PID_FILE)
        else: print("No daemon running")

    elif '--health' in args:
        if os.path.exists(PID_FILE):
            pid = int(open(PID_FILE).read().strip())
            alive = os.path.exists(f'/proc/{pid}') if os.name != 'nt' else True
            print(f"Coffee Brake {'running' if alive else 'stopped'} (PID {pid})")
        else: print("Coffee Brake not running")
        if os.path.exists(LEDGER):
            lines = [json.loads(l) for l in open(LEDGER) if l.strip()]
            cb = [l for l in lines if l.get('type') == 'coffee_brake']
            if cb:
                ms = sum(l.get('thinking_ms',0) for l in cb)
                print(f"{len(cb)} queries via coffee-brake | {ms/1000:.0f}s thinking | est ${ms/5000*0.0025:.4f}")

    else:
        os.makedirs(WORKDIR, exist_ok=True)
        run_query(pick_query())
        status()
