#!/usr/bin/env python3
"""Aggregates governance telemetry and task state into one JSON document.

Usage:
  python report_data.py [--since YYYY-MM-DD] [--last-days N]

Output: JSON to stdout, consumed by the report skill. The script does the
deterministic counting; the skill does the rendering and interpretation.

Reads (all optional, gracefully missing):
- .claude/hook-log.jsonl  — hook telemetry written by hook_telemetry.py
- .claude/selftest.json   — last hook self-test result
- .claude/manifest.json   — governance metadata, verification block, headings
- .claude/<tasks>/*.md    — task docs (status line near the top, scope section)

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
from task_doc import (  # noqa: E402
    extract_section, find_active_tasks, find_claude_dir, list_items, load_manifest,
    task_heading, verification,
)

STALE_DAYS = 7
SCOPE_SAMPLE = 10


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=None, help="ISO date YYYY-MM-DD; entries on/after this date")
    p.add_argument("--last-days", type=int, default=None, help="Only the last N days")
    p.add_argument("--project", default=None,
                   help="Project directory (default: $CLAUDE_PROJECT_DIR, else the current directory)")
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
    """Per-hook counts of decisions, top reasons for interventions, and how
    often scope-guard saw more than one active task."""
    log_path = os.path.join(claude_dir, "hook-log.jsonl")
    if not os.path.isfile(log_path):
        return [], 0, "missing", 0

    considered = 0
    multiple_active = 0
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
                if decision in ("block", "feedback", "annotate") and e.get("reason"):
                    b["reasons"][e["reason"]] += 1
                if (e.get("context") or {}).get("multiple_active_tasks"):
                    multiple_active += 1
                if ts and (b["first_seen"] is None or ts < b["first_seen"]):
                    b["first_seen"] = ts
                if ts and (b["last_seen"] is None or ts > b["last_seen"]):
                    b["last_seen"] = ts
    except OSError:
        return [], 0, "missing", 0

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
    return output, considered, "rotated_earlier" if rotated else "complete", multiple_active


def governance_block(manifest, now):
    g = manifest.get("governance", {}) or {}
    out = {
        "plugin_version": g.get("plugin_version"),
        "governance_version": g.get("version"),
        "initialized": g.get("initialized"),
        "age_days": None,
        "last_evolved": g.get("last_evolved"),
        "days_since_evolve": None,
        "security_posture": (manifest.get("security", {}) or {}).get("posture"),
    }
    init = parse_iso(g.get("initialized"))
    if init:
        out["age_days"] = (now - init).days
    ev = parse_iso(g.get("last_evolved"))
    if ev:
        out["days_since_evolve"] = (now - ev).days
    return out


def selftest_block(claude_dir, now):
    path = os.path.join(claude_dir, "selftest.json")
    if not os.path.isfile(path):
        return {"status": "never"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"status": "unreadable"}
    ran = parse_iso(d.get("ran_at"))
    return {
        "status": d.get("status"),
        "passed": d.get("passed"),
        "total": d.get("total"),
        "ran_at": d.get("ran_at"),
        "age_days": (now - ran).days if ran else None,
        "interpreter": d.get("interpreter"),
        "failed": [r.get("name") for r in d.get("results", []) if not r.get("ok")][:10],
    }


def verification_block(manifest):
    v = verification(manifest)
    gates = [g for g in (v.get("gates") or []) if isinstance(g, dict)]
    return {
        "declared": bool(v),
        "test_command": v.get("test_command"),
        "gates": len(gates),
        "data_gates": sum(1 for g in gates if g.get("kind") == "data"),
        "claim_guard": v.get("claim_guard", "annotate"),
        "claim_window_turns": v.get("claim_window_turns", 1),
        "llm_judge": bool(v.get("llm_judge")),
    }


def tasks_block(claude_dir, manifest, since, now):
    directory = (manifest.get("task_docs") or {}).get("directory") or "tasks"
    tasks_dir = os.path.join(claude_dir, directory)
    heading = task_heading(manifest, "scope", "Scope")
    out = {"total": 0, "status_distribution": {}, "stale_open": [],
           "scope_coverage": {"with_scope": 0, "of": 0, "heading": heading},
           "active_tasks": len(find_active_tasks(claude_dir, manifest))}
    if not os.path.isdir(tasks_dir):
        return out
    statuses = Counter()
    stale = []
    docs = []
    for fname in os.listdir(tasks_dir):
        if not fname.endswith(".md") or fname.upper() == "INDEX.MD":
            continue
        fpath = os.path.join(tasks_dir, fname)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc)
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        docs.append((mtime, fname, text))

    docs.sort(reverse=True)
    sample = docs[:SCOPE_SAMPLE]
    out["scope_coverage"]["of"] = len(sample)
    out["scope_coverage"]["with_scope"] = sum(
        1 for _, _, text in sample if list_items(extract_section(text, heading)))

    for mtime, fname, text in docs:
        if since is not None and mtime < since:
            continue
        m = re.search(r"status[\s*_]*:[\s*_]*([A-Za-z][A-Za-z _-]*)", text[:2048], re.I)
        status = m.group(1).strip().lower().replace(" ", "_") if m else "unknown"
        statuses[status] += 1
        out["total"] += 1
        if status in ("open", "in_progress", "in-progress", "active"):
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
    start = args.project or os.environ.get("CLAUDE_PROJECT_DIR") or None
    claude_dir = find_claude_dir(start)
    if not claude_dir:
        print(json.dumps({"status": "error", "error": "No .claude/ directory found",
                          "searched_from": start or os.getcwd()}, indent=2))
        sys.exit(1)

    since, until, label = resolve_window(args)
    manifest = load_manifest(claude_dir)
    hooks, considered, log_status, multiple_active = aggregate_hooks(claude_dir, since, until)
    tasks = tasks_block(claude_dir, manifest, since, until)

    print(json.dumps({
        "status": "success",
        "claude_dir": claude_dir,
        "generated_at": until.isoformat(timespec="seconds"),
        "window": {
            "filter": label,
            "since_iso": since.isoformat() if since else None,
            "until_iso": until.isoformat(),
            "hook_entries_considered": considered,
            "hook_log_status": log_status,
            "tasks_considered": tasks["total"],
        },
        "governance": governance_block(manifest, until),
        "selftest": selftest_block(claude_dir, until),
        "verification": verification_block(manifest),
        "hooks": hooks,
        "multiple_active_tasks_seen": multiple_active,
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
