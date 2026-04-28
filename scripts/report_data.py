#!/usr/bin/env python3
"""Aggregates governance telemetry and task state into a single JSON document.

Usage:
  python report_data.py [--since YYYY-MM-DD] [--last-days N]

Output: JSON to stdout. Designed to be consumed by the /report skill — the
script does the deterministic aggregation, the skill does the rendering and
synthesis.

Reads (all optional, gracefully missing):
- .claude/hook-log.jsonl       — hook telemetry written by hook_telemetry.py
- .claude/manifest.json        — governance metadata
- .claude/tasks/*.md           — task docs (status frontmatter, deferrals)

Stays stdlib-only — no third-party dependencies.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_doc import (
    find_claude_dir,
    parse_acceptance_criteria,
    count_open_deferrals,
)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=None,
                   help="ISO date YYYY-MM-DD; only consider entries on/after this date")
    p.add_argument("--last-days", type=int, default=None,
                   help="Only consider the last N days (mutually exclusive with --since)")
    return p.parse_args()


def resolve_window(args):
    """Return (since_dt, until_dt, filter_label)."""
    now = datetime.now(timezone.utc)
    if args.since:
        try:
            since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        except ValueError:
            since = None
        return since, now, f"since {args.since}"
    if args.last_days:
        since = now - timedelta(days=args.last_days)
        return since, now, f"last {args.last_days} days"
    return None, now, "all-time"


def parse_iso(ts):
    """Parse an ISO timestamp written by hook_telemetry. Returns aware datetime or None."""
    if not ts:
        return None
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def in_window(dt, since, until):
    if dt is None:
        return False
    if since is not None and dt < since:
        return False
    if until is not None and dt > until:
        return False
    return True


def aggregate_hooks(claude_dir, since, until):
    """Aggregate hook-log.jsonl into per-hook stats over the window.

    Returns a list of dicts, one per hook seen, with fires/feedback_reasons/
    skipped_by_flag. The skipped_by_flag breakdown is the key signal — it
    shows which gates would have blocked if their flag had been on.
    """
    log_path = os.path.join(claude_dir, "hook-log.jsonl")
    entries_considered = 0
    by_hook = defaultdict(lambda: {
        "fires": Counter(),
        "feedback_reasons": Counter(),
        "skipped_by_flag": defaultdict(lambda: {"count": 0, "reasons": Counter()}),
        "first_seen": None,
        "last_seen": None,
    })

    if not os.path.isfile(log_path):
        return [], 0, "missing"

    log_status = "rotated_likely" if os.path.getsize(log_path) >= 5 * 1024 * 1024 - 1024 else "complete"

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = parse_iso(e.get("ts"))
                if not in_window(ts, since, until):
                    continue
                entries_considered += 1
                hook_name = e.get("hook", "unknown")
                decision = e.get("decision", "unknown")
                bucket = by_hook[hook_name]
                bucket["fires"][decision] += 1
                if bucket["first_seen"] is None or (ts and ts < bucket["first_seen"]):
                    bucket["first_seen"] = ts
                if bucket["last_seen"] is None or (ts and ts > bucket["last_seen"]):
                    bucket["last_seen"] = ts

                reason = e.get("reason")
                if decision == "feedback" and reason:
                    bucket["feedback_reasons"][reason] += 1
                elif decision == "skipped":
                    flag = (e.get("context") or {}).get("flag", "unspecified")
                    sbf = bucket["skipped_by_flag"][flag]
                    sbf["count"] += 1
                    if reason:
                        sbf["reasons"][reason] += 1
    except OSError:
        return [], 0, "missing"

    output = []
    for name, b in sorted(by_hook.items()):
        output.append({
            "name": name,
            "fires": dict(b["fires"]),
            "feedback_reasons": [
                {"reason": r, "count": c}
                for r, c in b["feedback_reasons"].most_common(5)
            ],
            "skipped_by_flag": [
                {
                    "flag": flag,
                    "would_have_blocked": data["count"],
                    "top_reasons": [r for r, _ in data["reasons"].most_common(3)],
                }
                for flag, data in sorted(
                    b["skipped_by_flag"].items(),
                    key=lambda kv: -kv[1]["count"],
                )
            ],
            "first_seen": b["first_seen"].isoformat() if b["first_seen"] else None,
            "last_seen": b["last_seen"].isoformat() if b["last_seen"] else None,
        })
    return output, entries_considered, log_status


_FRONTMATTER_DATE_RE = re.compile(
    r"(?im)^\s*-?\s*\*{0,2}created\*{0,2}[\s*]*:[\s*]*(\d{4}-\d{2}-\d{2})"
)
_FRONTMATTER_STATUS_RE = re.compile(
    r"(?im)^\s*-?\s*\*{0,2}status\*{0,2}[\s*]*:[\s*]*(open|in_progress|review|closed|abandoned)\b"
)


def aggregate_tasks(claude_dir, since, until):
    tasks_dir = os.path.join(claude_dir, "tasks")
    if not os.path.isdir(tasks_dir):
        return {
            "total": 0,
            "status_distribution": {},
            "considered": 0,
            "stale_open": [],
            "deferral_ledger": 0,
        }

    now = datetime.now(timezone.utc)
    status_counts = Counter()
    considered = 0
    stale = []

    for fname in os.listdir(tasks_dir):
        if not fname.endswith(".md") or fname == "INDEX.md":
            continue
        path = os.path.join(tasks_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue

        head = text[:2048]
        sm = _FRONTMATTER_STATUS_RE.search(head)
        cm = _FRONTMATTER_DATE_RE.search(head)
        created = None
        if cm:
            try:
                created = datetime.fromisoformat(cm.group(1)).replace(tzinfo=timezone.utc)
            except ValueError:
                created = None

        # Window filter: include if created in window OR (no created date) OR window is all-time
        if since is not None and created is not None and created < since:
            continue
        considered += 1

        status = sm.group(1).lower() if sm else "unknown"
        status_counts[status] += 1

        if status in ("open", "in_progress") and created is not None:
            age = now - created
            if age >= timedelta(days=7):
                stale.append({
                    "task": fname,
                    "days_open": age.days,
                    "status": status,
                })

    return {
        "total": sum(status_counts.values()),
        "status_distribution": dict(status_counts),
        "considered": considered,
        "stale_open": sorted(stale, key=lambda t: -t["days_open"]),
        "deferral_ledger": count_open_deferrals(claude_dir),
    }


def aggregate_governance(claude_dir):
    out = {
        "plugin_version": None,
        "governance_version": None,
        "initialized": None,
        "age_days": None,
        "last_evolved": None,
        "days_since_evolve": None,
        "enforcement_flags": {},
        "deferred_threshold": None,
    }
    manifest_path = os.path.join(claude_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return out
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, json.JSONDecodeError):
        return out

    g = m.get("governance", {})
    out["plugin_version"] = g.get("plugin_version")
    out["governance_version"] = g.get("version")
    out["initialized"] = g.get("initialized")
    out["last_evolved"] = g.get("last_evolved")
    out["enforcement_flags"] = g.get("enforcement", {})
    out["deferred_threshold"] = g.get("deferred_threshold")

    now = datetime.now(timezone.utc)
    if out["initialized"]:
        try:
            init_dt = datetime.fromisoformat(out["initialized"]).replace(tzinfo=timezone.utc)
            out["age_days"] = (now - init_dt).days
        except ValueError:
            pass
    if out["last_evolved"]:
        try:
            ev_dt = datetime.fromisoformat(out["last_evolved"]).replace(tzinfo=timezone.utc)
            out["days_since_evolve"] = (now - ev_dt).days
        except ValueError:
            pass
    return out


def main():
    args = parse_args()
    claude_dir = find_claude_dir()
    if not claude_dir:
        print(json.dumps({
            "error": "no .claude directory found in cwd or ancestors",
        }, indent=2))
        sys.exit(1)

    since, until, label = resolve_window(args)
    governance = aggregate_governance(claude_dir)
    hooks, hook_entries, log_status = aggregate_hooks(claude_dir, since, until)
    tasks = aggregate_tasks(claude_dir, since, until)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {
            "filter": label,
            "since_iso": since.isoformat() if since else None,
            "until_iso": until.isoformat(),
            "hook_entries_considered": hook_entries,
            "hook_log_status": log_status,
            "tasks_considered": tasks["considered"],
        },
        "governance": governance,
        "hooks": hooks,
        "tasks": {
            "total": tasks["total"],
            "status_distribution": tasks["status_distribution"],
            "stale_open": tasks["stale_open"],
            "deferral_ledger": tasks["deferral_ledger"],
        },
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
