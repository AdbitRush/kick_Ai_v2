"""
Finance Agent — Claude-powered P&L analysis for the Kickbacks arbitrage system.
Reads the ledger, sends stats to Claude, returns structured financial insights.

Usage:
    python3 -m finance.agent
    python3 -m finance.agent --json
"""
from __future__ import annotations
import argparse
import json
import os
import sys

import anthropic

from finance.ledger import compute_stats
from finance.projections import project

MODEL = os.getenv("FINANCE_AGENT_MODEL", "claude-sonnet-4-6")

_SYSTEM = """\
You are a quantitative financial analyst specializing in digital arbitrage systems.
You receive real-time P&L data from a Kickbacks.ai arbitrage proxy and provide:
1. A sharp executive summary of current performance
2. Efficiency analysis (which models earn the most per hour)
3. 7-day and 30-day revenue projections based on observed run rate
4. Three concrete actions the operator should take to improve earnings

Respond in strict JSON only — no prose before or after:
{
  "summary": "2-3 sentence executive summary",
  "performance_grade": "A|B|C|D|F",
  "grade_rationale": "one sentence",
  "efficiency": {
    "best_model": "model name",
    "best_model_reason": "why it earns most",
    "impressions_per_hour": 0.0,
    "revenue_per_hour_usd": 0.0
  },
  "projections": {
    "7d_net_revenue_usd": 0.0,
    "30d_net_revenue_usd": 0.0,
    "annualized_net_revenue_usd": 0.0,
    "confidence": "high|medium|low",
    "confidence_reason": "one sentence"
  },
  "actions": [
    {"priority": 1, "action": "...", "expected_impact": "..."},
    {"priority": 2, "action": "...", "expected_impact": "..."},
    {"priority": 3, "action": "...", "expected_impact": "..."}
  ],
  "risk_flags": ["..."],
  "opportunities": ["..."]
}"""


def analyze(ledger_path: str | None = None, as_json: bool = False, model: str | None = None) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    stats = compute_stats(ledger_path)
    if "error" in stats:
        return {"error": stats["error"]}

    proj = project(stats)

    payload = {
        "current_stats": stats,
        "math_projections": proj,
    }

    # The kickbacks .env points ANTHROPIC_BASE_URL at the local free-model proxy
    # so `claude` routes through it. The finance agent must talk to the REAL
    # Anthropic API, so override base_url explicitly (env var would hijack it).
    base_url = os.getenv("FINANCE_ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
    response = client.messages.create(
        model=model or MODEL,
        max_tokens=2048,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                "Analyze this Kickbacks arbitrage P&L data and return your structured JSON assessment:\n\n"
                + json.dumps(payload, indent=2)
            ),
        }],
    )

    raw = response.content[0].text.strip()
    # strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    result = json.loads(raw)
    result["_raw_stats"] = stats
    result["_projections"] = proj
    return result


def _print_report(result: dict) -> None:
    stats = result.get("_raw_stats", {})
    proj = result.get("_projections", {})

    print("\n" + "═" * 58)
    print("  Kickbacks Finance Agent Report")
    print("═" * 58)

    print(f"\n{'Queries:':<30} {stats.get('entries', 0):,} ({stats.get('free_queries', 0)} free / {stats.get('paid_queries', 0)} paid)")
    print(f"{'Thinking time:':<30} {stats.get('total_think_sec', 0)/3600:.1f}h total  ({stats.get('avg_think_sec', 0):.0f}s avg)")
    print(f"{'Impressions:':<30} {stats.get('total_impressions', 0):,}  (@ CPM ${stats.get('cpm', 5.0):.2f})")
    print(f"{'Gross revenue (est.):':<30} ${stats.get('gross_revenue_usd', 0):.4f}")
    print(f"{'Your 50%:':<30} ${stats.get('net_revenue_usd', 0):.4f}")
    print(f"{'Cost:':<30} ${stats.get('total_cost_usd', 0):.6f}")
    print(f"{'Margin:':<30} {stats.get('margin_pct', 0):.1f}%")

    print(f"\n{'Last 24h queries:':<30} {stats.get('last_24h_queries', 0)}")
    print(f"{'Last 24h impressions:':<30} {stats.get('last_24h_impressions', 0):,}")

    print("\n" + "─" * 58)
    print(f"  Performance Grade: {result.get('performance_grade', '?')}  — {result.get('grade_rationale', '')}")
    print("─" * 58)

    print(f"\nSummary:\n  {result.get('summary', '')}")

    eff = result.get("efficiency", {})
    print(f"\nBest model: {eff.get('best_model', '?')}")
    print(f"  {eff.get('best_model_reason', '')}")
    print(f"  Impressions/hr: {eff.get('impressions_per_hour', 0):.0f}")
    print(f"  Revenue/hr:     ${eff.get('revenue_per_hour_usd', 0):.4f}")

    prj = result.get("projections", {})
    print(f"\n  7-day projection:    ${prj.get('7d_net_revenue_usd', 0):.4f}")
    print(f"  30-day projection:   ${prj.get('30d_net_revenue_usd', 0):.4f}")
    print(f"  Annualized:          ${prj.get('annualized_net_revenue_usd', 0):.2f}")
    print(f"  Confidence: {prj.get('confidence', '?')} — {prj.get('confidence_reason', '')}")

    actions = result.get("actions", [])
    if actions:
        print("\n  Top Actions:")
        for a in actions:
            print(f"    {a.get('priority', '?')}. {a.get('action', '')}")
            print(f"       → {a.get('expected_impact', '')}")

    flags = result.get("risk_flags", [])
    if flags:
        print("\n  Risk Flags:")
        for f in flags:
            print(f"    • {f}")

    opps = result.get("opportunities", [])
    if opps:
        print("\n  Opportunities:")
        for o in opps:
            print(f"    • {o}")

    print("\n" + "═" * 58 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kickbacks Finance Agent — AI P&L analysis")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted report")
    parser.add_argument("--ledger", help="Path to ledger file (default: ~/kickbacks_ledger.jsonl)")
    parser.add_argument("--model", help=f"Claude model to use (default: {MODEL})")
    args = parser.parse_args()

    result = analyze(ledger_path=args.ledger, as_json=args.json, model=args.model)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_report(result)


if __name__ == "__main__":
    main()
