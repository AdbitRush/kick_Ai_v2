# HANDOFF — kick_Ai_v2 (Kickbacks Engine)

**Updated:** 2026-07-30 · **Repo:** https://github.com/AdbitRush/kick_Ai_v2 · **Branch:** main
**Read this first, then `UPGRADES.md`.** `README.md` is the pitch, `MANUAL.md` the
full manual, `SESSION.md` a June session log (history, not current state).

Routes Claude Code through free OpenRouter models and earns a share of Kickbacks.ai
ad revenue from the sessions; the ledger then feeds a Claude finance agent.

---

## How it runs — this one is different

**CLI-first, not a service.** There is no pm2 process and nothing to keep alive:
the proxy exists only while you're running it.

| | |
|---|---|
| Proxy | `:5555` — up only while `kickbacks start` runs |
| Metrics | `http://127.0.0.1:5555/metrics` (per-model success rates, queries/hour, est. earnings) |
| Ledger | `~/kickbacks_ledger.jsonl` — **not present yet, so nothing has been logged** |
| Finance agent | `kickbacks finance` → `finance/agent.py`, `ledger.py`, `projections.py` |
| Watchdog | pm2 **`kickbacks-guard`** — but it runs from the **`Kick_and_backoff`** repo, not this one |
| In the hub | ABRI ONE → Deals & money → Kickbacks Engine (links to `/metrics`) |

**ABRI ONE will show this "stopped" most of the time and that is correct** — it has
no `cmd` in the registry on purpose, because starting a proxy behind your back is
not something a dashboard should do. Don't "fix" that by giving it one.

Prereqs (from `MANUAL.md`): an OpenRouter key and a Kickbacks.ai account. Standard
library only — no pip install.

---

## Traps

- **Two sibling repos.** `kick_Ai_v2` is the current engine; `Kick_and_backoff` is
  the older one that still owns the running `kickbacks-guard` watchdog. Check which
  directory you're in before editing — `pm2 show kickbacks-guard` tells you where
  the live process actually runs.
- The proxy **races all healthy free models concurrently** and returns the first
  success, with per-model cooldowns. If throughput drops, it's usually models being
  rate-limited into cooldown, not a bug.
- Slowness is the business model, not a defect: longer thinking time = more ad
  impressions. Don't "optimise" latency.

---

## Open / next

- [ ] **The ledger doesn't exist**, so `kickbacks finance` has nothing to analyse
      and the earnings numbers are theoretical. Run one real session before
      trusting any projection.
- [ ] Decide the relationship with `Kick_and_backoff` — two repos, one live
      watchdog, is exactly the setup that makes someone edit the wrong file. Either
      move the guard here or write down that it lives there for good.
- [ ] Nothing queued in `UPGRADES.md`.
