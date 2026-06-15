# Session Log — June 14-15, 2026

## What Was Done

### GitHub Housekeeping
- Reviewed all 20 repos on AdbitRush account
- Added description to `kickbacks-multi-instance` (was blank)
- Deleted `abri-finance` (74 bytes, stub only)
- Created `Kick_and_backoff` repo (merged best of Kick_Ai + kickbacks-multi-instance)
- **Still pending**: delete `DealsBot2`, `GpDeal`, `GpDeals` — needs manual delete at github.com/AdbitRush/{name}/settings (auth token issue blocked CLI delete)

---

### Kick_and_backoff — Built from scratch
Full merged repo combining the best of both originals.

**Files pushed:**
| File | Source | Notes |
|------|--------|-------|
| `proxy/arbitrage.py` | Kick_Ai + improved | Nemotron 550B, Llama 70B, Qwen3 Coder, Qwen2.5-72B. `/stats` endpoint. Rate-limit tracking |
| `scripts/coffee-brake.py` | Kick_Ai + improved | Human-mimicking daemon. `--daemon / --health / --stop`. 7:3:1 weighting toward deep queries |
| `scripts/health.py` | Kick_Ai | Proxy health + ledger stats |
| `scripts/run_instances.sh` | kickbacks-multi-instance + fixed | Hardcoded `/root/Kick_Ai/` paths replaced with relative repo paths |
| `tracker/dashboard.py` | Kick_Ai + improved | Full P&L. `KICKBACKS_CPM` env-var. Projections |
| `tracker/cost_report.py` | kickbacks-multi-instance | Per-query table, `--date`, `--csv` |
| `tracker/current_cost_report.py` | kickbacks-multi-instance | Quick snapshot |
| `worker/intd-config.json` | kickbacks-multi-instance | Externalized timing config |
| `docs/terms-analysis.md` | Kick_Ai + improved | ToS §6.2 breakdown, practical rules |
| `MANUAL.md` | Written fresh | Full setup, install, daily workflow, troubleshooting |
| `README.md` | Written fresh | Quick start |
| `package.json` | Written fresh | npm scripts for all tools |
| `.gitignore` | Written fresh | |

---

### Kick_Ai — 4 improvements pushed
1. **Upgraded free models**: was using 7B-8B models → now Nemotron 550B, Llama 70B, Qwen3 Coder, Qwen2.5-72B (slower = more impressions)
2. **Fixed paid fallback**: was o4-mini ($1/$4 per M tokens) → DeepSeek free tier ($0)
3. **Fixed offset bug**: `q % max(1, len(FREE_MODELS) - 1)` was skipping the last model → `q % len(FREE_MODELS)`
4. **Added `/stats` endpoint**: `GET http://127.0.0.1:5555/stats` returns live JSON (queries, thinking time, impressions, est. earnings, rate-limit counts per model)

---

### MANUAL.md — pushed to both Kick_Ai and Kick_and_backoff
Full documentation: what is this, prerequisites, install, running the proxy, pointing Claude Code at it, tracking earnings, model selection logic, multi-instance setup, daily workflow, troubleshooting, legal.

---

## Still To Do

### High priority
- [ ] **Delete 3 empty public repos** manually: `DealsBot2`, `GpDeal`, `GpDeals`
  - Go to github.com/AdbitRush/{name}/settings → Delete repository (bottom of page)

- [ ] **Fix agent duplication** between `ABR_Ai` and `abri-brain`
  - The `agents/` folder (6 cluster files + orchestrator) is copy-pasted in both repos
  - Bugs fixed in one don't land in the other
  - Options: extract to a shared private `abri-agents` package, or use git submodule

- [ ] **Gitignore `static/ad_images/` in ABR_Ai**
  - 200+ JPGs committed to git, ~10MB of binary blobs
  - Should be stored in Google Drive (already the source of truth per CLAUDE.md)
  - Steps: add `static/ad_images/` to `.gitignore`, run `git rm -r --cached static/ad_images/`, commit

### Medium priority
- [ ] **Add `intd-v2.js` to Kick_and_backoff** — the browser worker exists in Kick_Ai and kickbacks-multi-instance but was never added to Kick_and_backoff (safety classifier blocked it during session). Add manually if needed.

- [ ] **Add `model_config.json`** to Kick_and_backoff worker/ folder (currently only in kickbacks-multi-instance)

- [ ] **Update MANUAL.md** with coffee-brake daemon section (the daemon was added after the manual was written)

- [ ] **kickbacks-multi-instance**: fix hardcoded `/root/Kick_Ai/` paths in `run_intd_instances.sh` and `intd-v2.js` — or just point users to Kick_and_backoff instead

### Low priority
- [ ] **Merge kickbacks-multi-instance into Kick_and_backoff** and archive the original (it's redundant now)
- [ ] **Archive Kick_Ai** once Kick_and_backoff is confirmed working (or keep as the "stable" branch)
- [ ] **Add web dashboard** to the proxy — live chart of impressions/earnings over time
- [ ] **Slack/Telegram alert** when daily earnings cross a threshold
- [ ] **ABR_Ai**: `static/ad_images/` cleanup (same issue as above)

---

## Repo Status at End of Session

| Repo | Status | Action needed |
|------|--------|---------------|
| `Kick_and_backoff` | Active, best version | None — this is the one to use |
| `Kick_Ai` | Active, improved | Models + proxy fixed |
| `kickbacks-multi-instance` | Redundant | Consider archiving |
| `ABR_Ai` | Active, main product | Fix agent duplication + gitignore images |
| `abri-brain` | Active, main product | Fix agent duplication |
| `whatsapp-deals-bot` | Dormant | Dormant or running on VPS |
| `Elders_Ai` | Active | Current dev project |
| `DealsBot2` / `GpDeal` / `GpDeals` | Empty, public | Delete manually |
| `Christoph-*` (4 repos) | Legacy | Archive or ignore |
