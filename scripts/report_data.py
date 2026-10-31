#!/usr/bin/env python3
"""Aggregates governance telemetry and task state into one JSON document.

Usage:
  python report_data.py [--project DIR] [--since YYYY-MM-DD] [--last-days N]

Output: JSON to stdout, consumed by the report and evolve skills. The script
does the deterministic counting; the skills render and interpret.

Reads (all optional, gracefully missing):
- .claude/hook-log.jsonl  — hook telemetry written by hook_telemetry.py
- .claude/selftest.json   — last hook self-test result
- .claude/manifest.json   — governance metadata, verification block, headings
- .claude/<tasks>/**/*.md — task docs (status line, scope and thesis sections)
- .claude/rules/*.md      — rule files (size, paths: scoping)

Task docs are ordered by the date in their file name when present, else by
modification time. Rule candidates count as pending when the closing task
records a `Closed:` date on or after governance.last_evolved; a doc without
a Closed line falls back to its modification time, which a fresh clone resets.

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
    CLOSED_STATUSES, extract_section, find_active_tasks, find_claude_dir, iter_task_docs, is_active_status,
    list_items, load_manifest, read_text, task_heading, task_status, thesis_status, verification,
)

STALE_DAYS = 7
SAMPLE = 10


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=None, help="ISO date YYYY-MM-DD; entries on/after this date")
    p.add_argument("--last-days", type=int, default=None, help="Only the last N days")
    p.add_argument("--project", default=None, help="Project directory (default: $CLAUDE_PROJECT_DIR, else cwd)")
    return p.parse_args()


def resolve_window(args):
    now = datetime.now(timezone.utc)
    if args.since:
        try:
            since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"--since must be an ISO date (YYYY-MM-DD), got {args.since!r}")
        return since, now, f"since {args.since}"
    if args.last_days is not None:
        if args.last_days < 1:
            raise ValueError("--last-days must be at least 1")
        return now - timedelta(days=args.last_days), now, f"last {args.last_days} days"
    return None, now, "all-time"


def parse_iso(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def in_window(dt, since, until):
    if since is not None and dt < since:
        return False
    return not (until is not None and dt > until)


# --------------------------------------------------------------------------

def aggregate_hooks(claude_dir, since, until):
    log_path = os.path.join(claude_dir, "hook-log.jsonl")
    if not os.path.isfile(log_path):
        return [], 0, 0, "missing", 0
    considered = unparsed = multiple_active = 0
    by_hook = defaultdict(lambda: {"fires": Counter(), "reasons": Counter(), "files": Counter(),
                                   "first_seen": None, "last_seen": None})
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    unparsed += 1
                    continue
                ts = parse_iso(e.get("ts"))
                if ts is None:
                    unparsed += 1
                    if since is not None:
                        continue
                elif not in_window(ts, since, until):
                    continue
                considered += 1
                b = by_hook[e.get("hook", "unknown")]
                decision = e.get("decision", "unknown")
                b["fires"][decision] += 1
                ctx = e.get("context") or {}
                if decision in ("block", "feedback", "annotate"):
                    if e.get("reason"):
                        b["reasons"][e["reason"]] += 1
                    if ctx.get("file"):
                        b["files"][ctx["file"]] += 1
                if ctx.get("multiple_active_tasks"):
                    multiple_active += 1
                if ts:
                    if b["first_seen"] is None or ts < b["first_seen"]:
                        b["first_seen"] = ts
                    if b["last_seen"] is None or ts > b["last_seen"]:
                        b["last_seen"] = ts
    except OSError:
        return [], 0, 0, "missing", 0
    rotated = os.path.isfile(os.path.join(claude_dir, "hook-log.1.jsonl"))
    output = []
    for name, b in sorted(by_hook.items()):
        output.append({
            "name": name,
            "fires": dict(b["fires"]),
            "top_reasons": [{"reason": r, "count": c} for r, c in b["reasons"].most_common(5)],
            "top_files": [{"file": f, "count": c} for f, c in b["files"].most_common(5)],
            "first_seen": b["first_seen"].isoformat() if b["first_seen"] else None,
            "last_seen": b["last_seen"].isoformat() if b["last_seen"] else None,
        })
    return output, considered, unparsed, "rotated_earlier" if rotated else "complete", multiple_active


def governance_block(manifest, now):
    g = manifest.get("governance") or {}
    out = {
        "plugin_version": g.get("plugin_version"),
        "governance_version": g.get("version"),
        "initialized": g.get("initialized"),
        "age_days": None,
        "last_evolved": g.get("last_evolved"),
        "days_since_evolve": None,
        "security_posture": (manifest.get("security") or {}).get("posture"),
        "disabled_hooks": [h for h in (g.get("disabled_hooks") or []) if isinstance(h, str)],
    }
    init = parse_iso(g.get("initialized"))
    if init:
        out["age_days"] = (now - init).days
    ev = parse_iso(g.get("last_evolved"))
    if ev:
        out["days_since_evolve"] = (now - ev).days
    return out


def selftest_block(claude_dir, now, plugin_version):
    path = os.path.join(claude_dir, "selftest.json")
    if not os.path.isfile(path):
        return {"status": "never"}
    try:
        d = json.loads(read_text(path))
    except (ValueError, TypeError):
        return {"status": "unreadable"}
    ran = parse_iso(d.get("ran_at"))
    return {
        "status": d.get("status"),
        "passed": d.get("passed"),
        "total": d.get("total"),
        "ran_at": d.get("ran_at"),
        "age_days": (now - ran).days if ran else None,
        "interpreter": d.get("interpreter"),
        "plugin_version": d.get("plugin_version"),
        "stale": bool(plugin_version and d.get("plugin_version") and d.get("plugin_version") != plugin_version),
        "failed": [r.get("name") for r in d.get("results", []) if not r.get("ok")][:12],
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


_FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.DOTALL)


def paths_globs(frontmatter):
    """Globs under the `paths:` key: inline `[a, b]`, indented or unindented `- x` items."""
    m = re.search(r"(?m)^paths[ \t]*:[ \t]*(.*)$", frontmatter)
    if not m:
        return []
    inline = m.group(1).strip()
    if inline.startswith("["):
        return [g.strip().strip("\"'") for g in inline.strip("[]").split(",") if g.strip().strip("\"'")]
    globs = []
    for line in frontmatter[m.end():].splitlines():
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z_][\w-]*\s*:", line):
            break  # next top-level key
        item = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if item:
            globs.append(item.group(1).strip("\"'"))
        elif re.match(r"^\S", line):
            break
    return globs


def rules_block(claude_dir):
    rules_dir = os.path.join(claude_dir, "rules")
    out = {"files": [], "unconditional_bytes": 0, "scoped_bytes": 0, "largest": None}
    if not os.path.isdir(rules_dir):
        return out
    for fname in sorted(os.listdir(rules_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(rules_dir, fname)
        text = read_text(path)
        size = len(text.encode("utf-8"))
        fm = _FRONTMATTER_RE.match(text)
        globs = paths_globs(fm.group(1)) if fm else []
        scoped = len(globs) > 0
        out["files"].append({"file": fname, "bytes": size, "scoped": scoped, "paths": len(globs)})
        out["scoped_bytes" if scoped else "unconditional_bytes"] += size
        if out["largest"] is None or size > out["largest"]["bytes"]:
            out["largest"] = {"file": fname, "bytes": size}
    return out


_CLOSED_LINE_RE = re.compile(r"(?im)^\s*\**closed\**\s*:\**\s*(\d{4}-\d{2}-\d{2})")
_FNAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def doc_date(fname, text, mtime):
    """Best date for ordering: the file-name date, else modification time."""
    m = _FNAME_DATE_RE.match(fname)
    dt = parse_iso(m.group(1)) if m else None
    return dt or mtime


def closed_date(text, mtime):
    m = _CLOSED_LINE_RE.search(text)
    return (parse_iso(m.group(1)) if m else None) or mtime


def tasks_block(claude_dir, manifest, since, now):
    heading = task_heading(manifest, "scope", "Scope")
    thesis_heading = task_heading(manifest, "thesis", "Thesis")
    last_evolved = parse_iso((manifest.get("governance") or {}).get("last_evolved"))
    out = {"total": 0, "status_distribution": {}, "stale_open": [],
           "scope_coverage": {"with_scope": 0, "of": 0, "heading": heading},
           "thesis_coverage": {"with_thesis": 0, "demonstrated": 0, "attested": 0, "opted_out": 0,
                               "cannot_demonstrate": 0, "of": 0, "heading": thesis_heading},
           "rule_candidates": {"pending": 0, "since": last_evolved.date().isoformat() if last_evolved else None,
                               "items": []},
           "active_tasks": len(find_active_tasks(claude_dir, manifest))}
    docs = []
    for fpath, text in iter_task_docs(claude_dir, manifest):
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc)
        fname = os.path.basename(fpath)
        docs.append((doc_date(fname, text, mtime), mtime, fname, text))
    if not docs:
        return out
    docs.sort(key=lambda d: d[0], reverse=True)

    sample = docs[:SAMPLE]
    out["scope_coverage"]["of"] = len(sample)
    out["thesis_coverage"]["of"] = len(sample)
    for _, _, _, text in sample:
        if list_items(extract_section(text, heading)):
            out["scope_coverage"]["with_scope"] += 1
        ts = thesis_status(text, thesis_heading)
        for key in ("demonstrated", "attested", "opted_out", "cannot_demonstrate"):
            out["thesis_coverage"][key] += 1 if ts[key] else 0
        out["thesis_coverage"]["with_thesis"] += 1 if ts["present"] else 0

    statuses = Counter()
    stale = []
    for ddate, mtime, fname, text in docs:
        status = task_status(text)
        if status in CLOSED_STATUSES:
            cdate = closed_date(text, mtime)
            if last_evolved is None or cdate >= last_evolved:
                items = list_items(extract_section(text, "Rule Candidates"))
                if items:
                    out["rule_candidates"]["items"].append({"task": fname, "closed": cdate.date().isoformat(),
                                                            "candidates": items[:10]})
                    out["rule_candidates"]["pending"] += len(items)
        if since is not None and ddate < since:
            continue
        statuses[status] += 1
        out["total"] += 1
        if is_active_status(status):
            days = (now - ddate).days
            if days > STALE_DAYS:
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
    plugin_version = (manifest.get("governance") or {}).get("plugin_version")
    hooks, considered, unparsed, log_status, multiple_active = aggregate_hooks(claude_dir, since, until)
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
            "hook_entries_unparsed": unparsed,
            "hook_log_status": log_status,
            "tasks_considered": tasks["total"],
        },
        "governance": governance_block(manifest, until),
        "selftest": selftest_block(claude_dir, until, plugin_version),
        "verification": verification_block(manifest),
        "hooks": hooks,
        "multiple_active_tasks_seen": multiple_active,
        "tasks": tasks,
        "rules": rules_block(claude_dir),
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"}, indent=2))
        sys.exit(1)
