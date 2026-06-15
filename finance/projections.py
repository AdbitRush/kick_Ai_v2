"""
Pure-math revenue projections based on observed ledger run rate.
No AI calls — used by the agent as pre-computed context.
"""
from __future__ import annotations
from typing import Any


def project(stats: dict[str, Any]) -> dict[str, Any]:
    total_queries = stats.get("entries", 0)
    if total_queries == 0:
        return {"error": "no data"}

    last_24h = stats.get("last_24h_queries", 0)
    last_24h_impressions = stats.get("last_24h_impressions", 0)
    cpm = stats.get("cpm", 5.0)

    if last_24h >= 5:
        daily_impressions = last_24h_impressions
        rate_source = "last_24h"
    else:
        avg_sec = stats.get("total_think_sec", 0.0) / max(total_queries, 1)
        daily_impressions = int((avg_sec * 50) / 5)
        rate_source = "all_time_avg"

    daily_gross = (daily_impressions / 1000) * cpm
    daily_net = daily_gross * 0.5

    return {
        "rate_source": rate_source,
        "daily_impressions_est": daily_impressions,
        "daily_net_revenue_usd": round(daily_net, 4),
        "7d_net_revenue_usd": round(daily_net * 7, 4),
        "30d_net_revenue_usd": round(daily_net * 30, 4),
        "90d_net_revenue_usd": round(daily_net * 90, 4),
        "annualized_net_revenue_usd": round(daily_net * 365, 2),
        "cpm_used": cpm,
    }
