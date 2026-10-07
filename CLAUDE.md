# CLAUDE.md

## Standing rule: end-of-task ship checklist (Or, 2026-10-07)

Or continues from the VPS over Telegram, so work left only on the PC is invisible to them. At the end of EVERY task, always:

1. **Commit and push to GitHub.** Commit only the files this task changed (the tree may hold other agents' or earlier uncommitted work) and push the branch.
2. **Update the VPS.** `ssh root@178.105.148.72`, find this repo's checkout there (usually `/opt/<repo>`), and `git pull --ff-only` it. If the VPS checkout is dirty or not fast-forwardable, stop and report it; never reset or discard work there.
3. **Redeploy or restart whatever serves it** (systemd unit, site build, Caddy reload, etc.) so the live site or service matches the new code. Verify it afterwards.
4. **Report the live URL or service state**, with what you actually checked.

Never leave work only on the PC. If a step cannot be done (no remote, no VPS checkout, push rejected), say so plainly in the report instead of skipping it silently.
