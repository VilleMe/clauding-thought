#!/usr/bin/env python3
"""Aggregates governance telemetry and task state into one JSON document.

Usage:
  python report_data.py [--since YYYY-MM-DD] [--last-days N]

Output: JSON to stdout, consumed by the /report skill. The script does the
deterministic counting; the skill does the rendering and interpretation.

Reads (all optional, gracefully missing):
- .claude/hook-log.jsonl  — hook telemetry written by hook_telemetry.py
- .claude/manifest.json   — governance metadata
- .claude/tasks/*.md      — task docs (status line near the top)

Stdlib only.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_doc import find_claude_dir

STALE_DAYS = 7


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=None, help="ISO date YYYY-MM-DD; entries on/after this date")
    p.add_argument("--last-days", type=int, default=None, help="Only the last N days")
    return p.parse_args()


def resolve_window(args):
    now = datetime.now(timezone.utc)
    if args.since:
        try:
            since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        except ValueError:
            since = None
        return since, now, f"since {args.since}"
    if args.last_days:
        return now - timedelta(days=args.last_days), now, f"last {args.last_days} days"
    return None, now, "all-time"


def parse_iso(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
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
    return not (until is not None and dt > until)


def aggregate_hooks(claude_dir, since, until):
    """Per-hook counts of decisions, with the top reasons for blocks and feedback."""
    log_path = os.path.join(claude_dir, "hook-log.jsonl")
    if not os.path.isfile(log_path):
        return [], 0, "missing"

    considered = 0
    by_hook = defaultdict(lambda: {"fires": Counter(), "reasons": Counter(),
                                   "first_seen": None, "last_seen": None})
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
                considered += 1
                b = by_hook[e.get("hook", "unknown")]
                decision = e.get("decision", "unknown")
                b["fires"][decision] += 1
                if decision in ("block", "feedback") and e.get("reason"):
                    b["reasons"][e["reason"]] += 1
                if ts and (b["first_seen"] is None or ts < b["first_seen"]):
                    b["first_seen"] = ts
                if ts and (b["last_seen"] is None or ts > b["last_seen"]):
                    b["last_seen"] = ts
    except OSError:
        return [], 0, "missing"

    rotated = os.path.isfile(os.path.join(claude_dir, "hook-log.1.jsonl"))
    output = []
    for name, b in sorted(by_hook.items()):
        output.append({
            "name": name,
            "fires": dict(b["fires"]),
            "top_reasons": [{"reason": r, "count": c} for r, c in b["reasons"].most_common(5)],
            "first_seen": b["first_seen"].isoformat() if b["first_seen"] else None,
            "last_seen": b["last_seen"].isoformat() if b["last_seen"] else None,
        })
    return output, considered, "rotated_earlier" if rotated else "complete"


def governance_block(claude_dir, now):
    path = os.path.join(claude_dir, "manifest.json")
    out = {"plugin_version": None, "governance_version": None, "initialized": None,
           "age_days": None, "last_evolved": None, "days_since_evolve": None,
           "security_posture": None}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return out
    g = m.get("governance", {}) or {}
    out["plugin_version"] = g.get("plugin_version")
    out["governance_version"] = g.get("version")
    out["initialized"] = g.get("initialized")
    out["last_evolved"] = g.get("last_evolved")
    out["security_posture"] = (m.get("security", {}) or {}).get("posture")
    init = parse_iso(g.get("initialized"))
    if init:
        out["age_days"] = (now - init).days
    ev = parse_iso(g.get("last_evolved"))
    if ev:
        out["days_since_evolve"] = (now - ev).days
    return out


def tasks_block(claude_dir, since, until, now):
    tasks_dir = os.path.join(claude_dir, "tasks")
    out = {"total": 0, "status_distribution": {}, "stale_open": []}
    if not os.path.isdir(tasks_dir):
        return out
    statuses = Counter()
    stale = []
    for fname in sorted(os.listdir(tasks_dir)):
        if not fname.endswith(".md") or fname == "INDEX.md":
            continue
        fpath = os.path.join(tasks_dir, fname)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc)
            with open(fpath, "r", encoding="utf-8") as f:
                head = f.read(2048)
        except OSError:
            continue
        if since is not None and mtime < since:
            # keep tasks modified before the window out of the window's counts
            continue
        m = re.search(r"status:[\s*]*([A-Za-z_]+)", head, re.I)
        status = m.group(1).lower() if m else "unknown"
        statuses[status] += 1
        out["total"] += 1
        if status in ("open", "in_progress"):
            # created date from the filename prefix when present, else mtime
            cm = re.match(r"(\d{4}-\d{2}-\d{2})", fname)
            created = parse_iso(cm.group(1)) if cm else mtime
            days = (now - created).days if created else None
            if days is not None and days > STALE_DAYS:
                stale.append({"task": fname, "days_open": days, "status": status})
    out["status_distribution"] = dict(statuses)
    out["stale_open"] = sorted(stale, key=lambda s: -s["days_open"])
    return out


def main():
    args = parse_args()
    claude_dir = find_claude_dir()
    if not claude_dir:
        print(json.dumps({"status": "error", "error": "No .claude/ directory found"}, indent=2))
        sys.exit(1)

    since, until, label = resolve_window(args)
    hooks, considered, log_status = aggregate_hooks(claude_dir, since, until)
    tasks = tasks_block(claude_dir, since, until, until)

    print(json.dumps({
        "status": "success",
        "generated_at": until.isoformat(timespec="seconds"),
        "window": {
            "filter": label,
            "since_iso": since.isoformat() if since else None,
            "until_iso": until.isoformat(),
            "hook_entries_considered": considered,
            "hook_log_status": log_status,
            "tasks_considered": tasks["total"],
        },
        "governance": governance_block(claude_dir, until),
        "hooks": hooks,
        "tasks": tasks,
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # report errors as JSON, never a traceback
        print(json.dumps({"status": "error", "error": str(e)}, indent=2))
        sys.exit(1)
