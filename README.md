# kick_Ai_v2

**Kickbacks arbitrage engine — zero-cost AI + ad revenue from your coding sessions, with an AI finance agent.**

Routes Claude Code through free OpenRouter models (Nemotron 550B, Llama 70B, Qwen3 Coder).
You pay $0. The thinking spinner still runs. Kickbacks.ai pays you 50% of ad revenue.
A Claude-powered finance agent then analyzes your ledger and projects earnings.

```
Claude Code → proxy :5555 → OpenRouter (free, raced concurrently) → Response
                   ↓
            Kickbacks ads → 50% revenue → You
                   ↓
        ~/kickbacks_ledger.jsonl → finance agent (Claude) → P&L + projections
```

## What's new in v2

- **Concurrent model racing** — the proxy fires all healthy free models at once and
  returns the first success (much lower latency, more queries/hour).
- **Per-model health tracking** — models that keep failing/rate-limiting are skipped
  (with cooldown), so the race isn't slowed by dead endpoints.
- **Richer `/metrics` endpoint** — per-model success rates, queries/hour, est. earnings.
- **Request-ID tracking** — every query gets an ID in the ledger and `X-Kickbacks-Request-Id` header.
- **AI finance agent** (`kickbacks finance`) — Claude reads the ledger and returns a
  graded P&L report with 7/30-day projections and concrete actions.
- **Ledger field alignment** — the proxy, coffee-brake, and finance module now share
  the same schema (`ts`, `thinking_ms`, `model_actual`, `free`), so the finance module
  actually works.
- **Durable ledger** — defaults to `~/kickbacks_ledger.jsonl` (survives reboot) instead of `/tmp`.
- **coffee-brake `--queries N` and `--interval MIN MAX`** for bounded, tunable runs.

---

## Install (one command, fresh Linux VPS)

```bash
git clone https://github.com/AdbitRush/Kick_and_backoff.git ~/kickbacks
bash ~/kickbacks/install.sh
```

That's it. The installer:
- Installs Python 3, Node.js 20, Claude Code CLI
- Prompts for your OpenRouter API key
- Starts the proxy as a systemd service (survives reboot)
- Installs the `kickbacks` CLI

**Requirements:** Ubuntu 20.04+ / Debian 11+ / any systemd Linux. 512MB RAM minimum.

---

## Daily Use

```bash
# Tell Claude Code to use the proxy
kickbacks use          # prints the two export commands to paste

# Then just work normally
claude

# Check earnings anytime
kickbacks dashboard    # full P&L
kickbacks snapshot     # quick numbers
kickbacks stats        # live proxy JSON
```

---

## CLI Reference

```
kickbacks start            Start proxy (+ --brake for coffee brake daemon)
kickbacks stop             Stop everything
kickbacks status           Service health + live stats
kickbacks dashboard        Full P&L dashboard with projections
kickbacks snapshot         Quick cost/revenue snapshot
kickbacks finance          AI P&L analysis (--json for raw, --model NAME to override)
kickbacks report           Per-query table (--date YYYY-MM-DD, --csv out.csv)
kickbacks logs proxy       Tail proxy log
kickbacks logs brake       Tail coffee brake log
kickbacks brake-start      Start coffee brake daemon
kickbacks brake-stop       Stop coffee brake daemon
kickbacks health           Quick proxy health check
kickbacks use              Print env vars to paste into your shell
kickbacks update           Pull latest code + restart services
kickbacks env              Show current .env
```

---

## Components

| File | Purpose |
|------|---------|
| `install.sh` | One-command installer (also installs the `anthropic` Python SDK) |
| `proxy/arbitrage.py` | Anthropic → OpenRouter bridge with concurrent racing + health tracking. `GET /stats`, `/health`, `/metrics` |
| `scripts/coffee-brake.py` | Human-mimicking query daemon (`--daemon / --queries N / --interval MIN MAX / --health / --stop`) |
| `scripts/health.py` | Proxy health + ledger summary |
| `scripts/run_instances.sh` | Launch N parallel browser workers |
| `finance/ledger.py` | Ledger reader — computes P&L stats from `~/kickbacks_ledger.jsonl` |
| `finance/projections.py` | Pure-math revenue projections (no AI) |
| `finance/agent.py` | Claude-powered finance agent (`python3 -m finance.agent`) |
| `worker/intd-v2.js` | Browser worker — drives Claude Code in code-server via Playwright |
| `worker/intd-config.json` | Timing config for worker (thinkSec, brakeSec, pauses) |
| `worker/model_config.json` | Default + paid model mapping for the worker |
| `kickbacks_fetch.py` | Playwright scraper for live Kickbacks balance → `/tmp/kickbacks_balance.json` |
| `tracker/dashboard.py` | Full P&L (cost, revenue, margin, projections) |
| `tracker/cost_report.py` | Per-query detail with `--date` and `--csv` |
| `tracker/current_cost_report.py` | Quick snapshot |

---

## Free Models Used

| Model | Params | Speed | Impressions |
|-------|--------|-------|-------------|
| Nemotron 550B | 550B | Slowest | Highest |
| Llama 3.3-70B | 70B | Slow | High |
| Qwen3 Coder | 72B | Medium | Medium |
| Qwen2.5-72B | 72B | Medium | Medium |

Slow = longer thinking time = more ad impressions = more revenue. All free.

The proxy **races all healthy free models concurrently** and returns the first to
succeed. Models that fail or rate-limit repeatedly are temporarily skipped (with a
cooldown) so the race stays fast. Set `CONCURRENT_RACE=0` to fall back to sequential.

---

## Proxy Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /stats` | Live counters (queries, thinking time, impressions, est. earnings) |
| `GET /health` | Same as `/stats` (health probe) |
| `GET /metrics` | Rich JSON: per-model success/fail rates, queries/hour, cost, model health |
| `POST /` | Anthropic Messages API endpoint Claude Code talks to |

---

## Finance Agent

`kickbacks finance` runs a Claude-powered analyst over your ledger:

```bash
kickbacks finance              # formatted report
kickbacks finance --json       # raw JSON for scripting
kickbacks finance --model claude-opus-4-8   # override the model
```

It returns a performance grade, executive summary, best-earning model, 7/30-day and
annualized revenue projections, and three concrete actions to improve earnings.

**Requires** a real `ANTHROPIC_API_KEY` in `~/kickbacks/.env` (the proxy key won't work —
the agent talks to the real Anthropic API, not the local free-model proxy). Default
model is `claude-sonnet-4-6`; override with `--model` or `FINANCE_AGENT_MODEL`.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | required | Your OpenRouter key |
| `ANTHROPIC_API_KEY` | optional | Real Anthropic key for `kickbacks finance` |
| `PROXY_PORT` | `5555` | Proxy listen port |
| `LEDGER_PATH` | `~/kickbacks_ledger.jsonl` | Query log file |
| `KICKBACKS_CPM` | `5.0` | CPM rate for revenue estimates |
| `CLAUDE_WORKDIR` | `~/testproj` | Working dir for coffee-brake queries |
| `CONCURRENT_RACE` | `1` | Race all free models at once (`0` = sequential) |
| `MAX_TOKENS_CAP` | `8192` | Upper cap on `max_tokens` forwarded upstream |
| `UPSTREAM_TIMEOUT` | `180` | Seconds before an upstream model call times out |
| `FINANCE_AGENT_MODEL` | `claude-sonnet-4-6` | Model for the finance agent |

---

## Update

```bash
kickbacks update
```

Or manually: `git -C ~/kickbacks pull && kickbacks restart`
