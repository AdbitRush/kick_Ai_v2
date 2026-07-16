"""
Kickbacks → central AI usage ledger reporter.

Fire-and-forget: reports every AI API call to the abri-brain usage ledger
(POST /api/usage/record) so per-model usage + cost across ALL systems lives in
one place. Never blocks, never raises into the caller.

Config (env, all optional):
  ABRI_BRAIN_URL   base URL of abri-brain     (default http://127.0.0.1:8765)
  ABRI_USERNAME    basic-auth user, if the Brain has ABRI_PASSWORD set
  ABRI_PASSWORD    basic-auth password
  ABRI_USAGE_OFF   set to "1" to disable reporting entirely
"""
from __future__ import annotations

import base64
import json
import os
import threading
import urllib.request

SYSTEM = "Kickbacks"


def _brain_url() -> str:
    return os.environ.get("ABRI_BRAIN_URL", "http://127.0.0.1:8765").rstrip("/")


def _post(payload: dict) -> None:
    try:
        req = urllib.request.Request(
            _brain_url() + "/api/usage/record",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        pw = os.environ.get("ABRI_PASSWORD", "").strip()
        if pw:
            user = os.environ.get("ABRI_USERNAME", "abri")
            tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
            req.add_header("Authorization", "Basic " + tok)
        urllib.request.urlopen(req, timeout=6).read()
    except Exception:
        pass  # telemetry must never break the caller


def report(model: str, tokens_in: int = 0, tokens_out: int = 0,
           feature: str = "finance", cost_usd: float | None = None,
           provider: str | None = None, units: int = 1) -> None:
    """Report one AI call to the central ledger (async, best-effort)."""
    if os.environ.get("ABRI_USAGE_OFF", "").strip() == "1" or not model:
        return
    payload = {
        "system": SYSTEM, "model": model, "feature": feature,
        "tokens_in": int(tokens_in or 0), "tokens_out": int(tokens_out or 0),
        "units": int(units or 1),
    }
    if cost_usd is not None:
        payload["cost_usd"] = cost_usd
    if provider:
        payload["provider"] = provider
    threading.Thread(target=_post, args=(payload,), daemon=True).start()
