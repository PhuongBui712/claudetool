"""
Stats command — token usage and cost summary per session.
"""

import json
from datetime import datetime
from pathlib import Path

from claudetool.rendering import BOLD, CYAN, DIM, GREEN, YELLOW, RED, RESET
from claudetool.sessions import (
    resolve_targets,
)


# ─────────────────────────────────────────────
# Pricing (USD per 1M tokens) — updated for Claude 4.x
# ─────────────────────────────────────────────

MODEL_PRICING: dict[str, dict[str, float]] = {
    # model-name-substring → {input, output, cache_read, cache_write} per 1M tokens
    "opus": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "haiku": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_write": 1.0,
    },
}

# Fallback for unknown models
_DEFAULT_PRICING = MODEL_PRICING["sonnet"]


def _get_pricing(model: str) -> dict[str, float]:
    model_lower = model.lower()
    for key, pricing in MODEL_PRICING.items():
        if key in model_lower:
            return pricing
    return _DEFAULT_PRICING


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_cost(usd: float) -> str:
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.2f}"


# ─────────────────────────────────────────────
# Token extraction from a session file
# ─────────────────────────────────────────────


def extract_session_usage(session_file: Path) -> dict:
    """Parse a session JSONL and return aggregated token usage."""
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    by_model: dict[str, dict[str, int]] = {}

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("type") != "assistant":
                    continue

                msg = entry.get("message", {})
                usage = msg.get("usage")
                if not usage:
                    continue

                model = msg.get("model", "unknown")

                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cread = usage.get("cache_read_input_tokens", 0)
                cwrite = usage.get("cache_creation_input_tokens", 0)

                totals["input_tokens"] += inp
                totals["output_tokens"] += out
                totals["cache_read_input_tokens"] += cread
                totals["cache_creation_input_tokens"] += cwrite

                if model not in by_model:
                    by_model[model] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "requests": 0,
                    }
                by_model[model]["input_tokens"] += inp
                by_model[model]["output_tokens"] += out
                by_model[model]["cache_read_input_tokens"] += cread
                by_model[model]["cache_creation_input_tokens"] += cwrite
                by_model[model]["requests"] += 1

    except (IOError, PermissionError):
        pass

    return {"totals": totals, "by_model": by_model}


def compute_cost(usage: dict[str, int], model: str = "sonnet") -> float:
    pricing = _get_pricing(model)
    cost = 0.0
    cost += usage.get("input_tokens", 0) / 1_000_000 * pricing["input"]
    cost += usage.get("output_tokens", 0) / 1_000_000 * pricing["output"]
    cost += usage.get("cache_read_input_tokens", 0) / 1_000_000 * pricing["cache_read"]
    cost += (
        usage.get("cache_creation_input_tokens", 0) / 1_000_000 * pricing["cache_write"]
    )
    return cost


def get_session_total_cost(session_file: Path) -> float:
    """Quick cost estimate for a single session (used in list view)."""
    usage_data = extract_session_usage(session_file)
    total_cost = 0.0
    for model, model_usage in usage_data["by_model"].items():
        total_cost += compute_cost(model_usage, model)
    return total_cost


# ─────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────


def _print_usage_table(usage_data: dict, label: str) -> None:
    totals = usage_data["totals"]
    by_model = usage_data["by_model"]

    total_all = (
        totals["input_tokens"]
        + totals["output_tokens"]
        + totals["cache_read_input_tokens"]
        + totals["cache_creation_input_tokens"]
    )

    print(f"\n  {BOLD}{GREEN}{label}{RESET}")
    print()

    # Per-model breakdown
    if by_model:
        print(
            f"    {BOLD}{'Model':<30} {'Requests':>8} {'Input':>10} {'Output':>10} {'Cache R':>10} {'Cache W':>10} {'Cost':>10}{RESET}"
        )
        print(f"    {'─' * 88}")

        total_cost = 0.0
        for model, mu in sorted(by_model.items()):
            cost = compute_cost(mu, model)
            total_cost += cost
            short_model = model[:28]
            print(
                f"    {CYAN}{short_model:<30}{RESET}"
                f" {mu['requests']:>8}"
                f" {_fmt_tokens(mu['input_tokens']):>10}"
                f" {_fmt_tokens(mu['output_tokens']):>10}"
                f" {_fmt_tokens(mu['cache_read_input_tokens']):>10}"
                f" {_fmt_tokens(mu['cache_creation_input_tokens']):>10}"
                f" {YELLOW}{_fmt_cost(cost):>10}{RESET}"
            )

        print(f"    {'─' * 88}")
        print(
            f"    {BOLD}{'Total':<30}{RESET}"
            f" {'':>8}"
            f" {_fmt_tokens(totals['input_tokens']):>10}"
            f" {_fmt_tokens(totals['output_tokens']):>10}"
            f" {_fmt_tokens(totals['cache_read_input_tokens']):>10}"
            f" {_fmt_tokens(totals['cache_creation_input_tokens']):>10}"
            f" {BOLD}{YELLOW}{_fmt_cost(total_cost):>10}{RESET}"
        )
        print(
            f"\n    {DIM}Total tokens: {_fmt_tokens(total_all)}  ·  Estimated cost: {_fmt_cost(total_cost)}{RESET}"
        )
    else:
        print(f"    {DIM}(no token usage data found){RESET}")


# ─────────────────────────────────────────────
# Command
# ─────────────────────────────────────────────


def cmd_stats(sessions: list[dict], args) -> None:
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
        except ValueError:
            print(
                f"{RED}Invalid date format:{RESET} {args.since}  (expected YYYY-MM-DD)"
            )
            return

    # Filter to specific session(s)
    if args.session:
        targets = resolve_targets(sessions, [args.session])
        if not targets:
            print(f"{RED}No session matched:{RESET} {args.session}")
            return
    else:
        targets = sessions

    # Date filter
    if since:
        targets = [s for s in targets if s["created_at"] and s["created_at"] >= since]
        if not targets:
            print(f"  {DIM}No sessions found since {args.since}{RESET}")
            return

    if args.session and len(targets) == 1:
        # Detailed single-session view
        s = targets[0]
        label = s["custom_title"] or s["session_id"][:16]
        date_str = (
            s["created_at"].strftime("%Y-%m-%d %H:%M") if s["created_at"] else "?"
        )
        usage_data = extract_session_usage(s["file"])
        _print_usage_table(usage_data, f"{label}  {DIM}({date_str}){RESET}")
    else:
        # Aggregate across all matched sessions
        agg_totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        agg_by_model: dict[str, dict[str, int]] = {}

        print(f"\n  {BOLD}{'Session':<52} {'Tokens':>10} {'Cost':>10}{RESET}")
        print(f"  {'─' * 72}")

        grand_cost = 0.0
        for s in targets:
            usage_data = extract_session_usage(s["file"])

            # Accumulate
            for key in agg_totals:
                agg_totals[key] += usage_data["totals"][key]
            for model, mu in usage_data["by_model"].items():
                if model not in agg_by_model:
                    agg_by_model[model] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "requests": 0,
                    }
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                    "requests",
                ):
                    agg_by_model[model][key] += mu[key]

            # Per-session summary line
            t = usage_data["totals"]
            sess_tokens = (
                t["input_tokens"]
                + t["output_tokens"]
                + t["cache_read_input_tokens"]
                + t["cache_creation_input_tokens"]
            )
            sess_cost = sum(
                compute_cost(mu, m) for m, mu in usage_data["by_model"].items()
            )
            grand_cost += sess_cost

            label = (s["custom_title"] or s["session_id"][:16])[:50]
            print(
                f"  {CYAN}{label:<52}{RESET}"
                f" {_fmt_tokens(sess_tokens):>10}"
                f" {YELLOW}{_fmt_cost(sess_cost):>10}{RESET}"
            )

        print(f"  {'─' * 72}")
        total_tokens = sum(agg_totals.values())
        print(
            f"  {BOLD}{'Total (' + str(len(targets)) + ' sessions)':<52}{RESET}"
            f" {BOLD}{_fmt_tokens(total_tokens):>10}{RESET}"
            f" {BOLD}{YELLOW}{_fmt_cost(grand_cost):>10}{RESET}"
        )

        # Full model breakdown below
        _print_usage_table(
            {"totals": agg_totals, "by_model": agg_by_model}, "Model Breakdown"
        )

    print()
