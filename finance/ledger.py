"""
Ledger reader — loads kickbacks_ledger.jsonl and computes P&L stats.
No AI here. Pure data layer used by the agent and projections modules.
"""
from __future__ import annotations
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path.home() / "kickbacks_ledger.jsonl"
CPM = float(os.getenv("KICKBACKS_CPM", "5.0"))
IMPRESSION_INTERVAL = 5  # seconds per impression


def _think_sec(e: dict) -> float:
    """Thinking time in seconds. The proxy/coffee-brake write `thinking_ms`
    (milliseconds); older entries may carry `duration_sec`. Support both."""
    if "thinking_ms" in e and e.get("thinking_ms") is not None:
        try:
            return float(e["thinking_ms"]) / 1000.0
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(e.get("duration_sec", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ts(e: dict) -> str:
    """Timestamp string. Proxy writes `ts`; legacy data may use `timestamp`."""
    return e.get("ts") or e.get("timestamp") or ""


def _model(e: dict) -> str:
    """Model name. Proxy writes `model_actual`; legacy data may use `model`."""
    return e.get("model_actual") or e.get("model") or "unknown"


def _is_free(e: dict) -> bool:
    """A query is free if explicitly flagged free, or has zero cost."""
    if "free" in e:
        return bool(e.get("free"))
    return float(e.get("cost_usd", 0.0) or 0.0) == 0.0


def _load(ledger_path: str | Path | None = None) -> list[dict]:
    path = Path(ledger_path or os.getenv("LEDGER_PATH", str(DEFAULT_LEDGER)))
    if not path.exists():
        return []
    entries = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def compute_stats(ledger_path: str | Path | None = None) -> dict[str, Any]:
    entries = _load(ledger_path)
    if not entries:
        return {"error": "No ledger data found", "entries": 0}

    total_queries = len(entries)
    free_queries = sum(1 for e in entries if _is_free(e))
    paid_queries = total_queries - free_queries

    total_cost = sum(float(e.get("cost_usd", 0.0) or 0.0) for e in entries)
    total_think_sec = sum(_think_sec(e) for e in entries)
    total_impressions = int(total_think_sec / IMPRESSION_INTERVAL)
    gross_revenue = (total_impressions / 1000) * CPM
    net_revenue = gross_revenue * 0.5  # Kickbacks.ai 50% share
    margin_pct = 100.0 if total_cost == 0 else ((net_revenue - total_cost) / max(net_revenue, 0.0001)) * 100

    # per-model breakdown
    by_model: dict[str, dict] = defaultdict(lambda: {"queries": 0, "think_sec": 0.0, "cost": 0.0})
    for e in entries:
        m = _model(e)
        by_model[m]["queries"] += 1
        by_model[m]["think_sec"] += _think_sec(e)
        by_model[m]["cost"] += float(e.get("cost_usd", 0.0) or 0.0)

    # daily breakdown
    by_day: dict[str, dict] = defaultdict(lambda: {"queries": 0, "think_sec": 0.0, "cost": 0.0})
    for e in entries:
        ts = _ts(e)
        day = ts[:10] if ts else "unknown"
        by_day[day]["queries"] += 1
        by_day[day]["think_sec"] += _think_sec(e)
        by_day[day]["cost"] += float(e.get("cost_usd", 0.0) or 0.0)

    # last 24h
    now = datetime.now(tz=timezone.utc)

    def _recent(e: dict) -> bool:
        ts = _ts(e)
        if not ts:
            return False
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds() < 86400

    recent = [e for e in entries if _recent(e)]
    recent_impressions = int(sum(_think_sec(e) for e in recent) / IMPRESSION_INTERVAL)

    avg_think_sec = total_think_sec / total_queries if total_queries else 0

    return {
        "entries": total_queries,
        "free_queries": free_queries,
        "paid_queries": paid_queries,
        "total_think_sec": round(total_think_sec, 1),
        "avg_think_sec": round(avg_think_sec, 1),
        "total_impressions": total_impressions,
        "total_cost_usd": round(total_cost, 6),
        "gross_revenue_usd": round(gross_revenue, 6),
        "net_revenue_usd": round(net_revenue, 6),
        "margin_pct": round(margin_pct, 1),
        "cpm": CPM,
        "last_24h_queries": len(recent),
        "last_24h_impressions": recent_impressions,
        "by_model": {k: {
            "queries": v["queries"],
            "think_sec": round(v["think_sec"], 1),
            "cost_usd": round(v["cost"], 6),
            "impressions": int(v["think_sec"] / IMPRESSION_INTERVAL),
        } for k, v in by_model.items()},
        "by_day": {day: {
            "queries": v["queries"],
            "think_sec": round(v["think_sec"], 1),
            "cost_usd": round(v["cost"], 6),
            "impressions": int(v["think_sec"] / IMPRESSION_INTERVAL),
            "net_revenue_usd": round((v["think_sec"] / IMPRESSION_INTERVAL / 1000) * CPM * 0.5, 6),
        } for day, v in sorted(by_day.items())},
    }
