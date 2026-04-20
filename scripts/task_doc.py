#!/usr/bin/env python3
"""Shared helpers for hook scripts that need to read the active task doc.

All operations are fail-soft: missing files, parse errors, or unexpected
shapes return empty/neutral values so hooks can decide silently.
"""
import json
import os
import re


def get_enforcement_flag(claude_dir, name):
    """Return the boolean value of governance.enforcement.<name> from manifest.json.

    Missing manifest, missing block, missing key all return False — the plugin
    does not impose conventions a project has not explicitly opted into.
    """
    if not claude_dir:
        return False
    try:
        manifest_path = os.path.join(claude_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            return False
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        enforcement = manifest.get("governance", {}).get("enforcement", {})
        return bool(enforcement.get(name, False))
    except Exception:
        return False


def find_claude_dir(start=None):
    """Walk up from `start` (or cwd) to find the nearest `.claude/` directory."""
    try:
        current = start or os.getcwd()
        for _ in range(10):
            candidate = os.path.join(current, ".claude")
            if os.path.isdir(candidate):
                return candidate
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    except Exception:
        pass
    return None


def find_active_task(claude_dir):
    """Return (path, text) of the active task doc, or (None, None).

    Active = status is open or in_progress. If multiple match, returns
    the most recently modified one.
    """
    if not claude_dir:
        return None, None
    try:
        tasks_dir = os.path.join(claude_dir, "tasks")
        if not os.path.isdir(tasks_dir):
            return None, None
        candidates = []
        for fname in os.listdir(tasks_dir):
            if not fname.endswith(".md") or fname == "INDEX.md":
                continue
            fpath = os.path.join(tasks_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue
            head = text[:1024]
            if re.search(r"status:[\s*]*(open|in_progress)\b", head, re.I):
                candidates.append((os.path.getmtime(fpath), fpath, text))
        if not candidates:
            return None, None
        candidates.sort(reverse=True)
        _, fpath, text = candidates[0]
        return fpath, text
    except Exception:
        return None, None


def extract_section(text, heading):
    """Return the body of a `## heading` section up to the next `## ` or EOF."""
    if not text:
        return ""
    pattern = rf"(?m)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1) if m else ""


# Matches lines like "- [ ] ...", "- [x] ...", "- [deferred:TASK-20260420-001] ..."
# Also accepts "* [x]" and "1. [x]" list styles.
_CHECKBOX_RE = re.compile(
    r"(?m)^\s*(?:[-*+]|\d+\.)\s+\[(?P<mark>[^\]]*)\]"
)

# Matches a fenced code block (```...``` or ~~~...~~~).
_FENCE_RE = re.compile(
    r"(?ms)^\s*(```|~~~)[^\n]*\n.*?^\s*\1\s*$"
)


def strip_fenced_blocks(text):
    """Remove fenced code blocks so checkboxes inside examples aren't counted."""
    if not text:
        return text
    return _FENCE_RE.sub("", text)


def parse_acceptance_criteria(text):
    """Parse the Acceptance Criteria section and categorize each checkbox.

    Returns {"checked": N, "unchecked": N, "deferred": [TASK-ID, ...], "invalid": N}
    where `invalid` counts free-text deferrals or malformed marks.

    Checkboxes inside fenced code blocks are ignored so documentation-style
    task docs that show the format as an example don't pollute the count.
    """
    section = extract_section(text, "Acceptance Criteria")
    result = {"checked": 0, "unchecked": 0, "deferred": [], "invalid": 0}
    if not section:
        return result
    section = strip_fenced_blocks(section)
    for m in _CHECKBOX_RE.finditer(section):
        mark = m.group("mark").strip()
        if mark == "":
            result["unchecked"] += 1
        elif mark.lower() == "x":
            result["checked"] += 1
        elif mark.lower().startswith("deferred:"):
            task_id = mark.split(":", 1)[1].strip()
            if task_id:
                result["deferred"].append(task_id)
            else:
                result["invalid"] += 1
        else:
            result["invalid"] += 1
    return result


def count_open_deferrals(claude_dir):
    """Count `[deferred:TASK-ID]` entries across all non-index task docs.

    An entry is "open" if the referenced TASK-ID's own doc is still
    open/in_progress (or does not exist — dangling references count as open
    since they cannot be audited).
    """
    if not claude_dir:
        return 0
    tasks_dir = os.path.join(claude_dir, "tasks")
    if not os.path.isdir(tasks_dir):
        return 0
    try:
        all_deferrals = []
        task_statuses = {}
        for fname in os.listdir(tasks_dir):
            if not fname.endswith(".md") or fname == "INDEX.md":
                continue
            fpath = os.path.join(tasks_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue
            # Record status of this doc, keyed by bare filename sans .md
            task_id = os.path.splitext(fname)[0]
            head = text[:1024]
            m = re.search(r"status:[\s*]*(open|in_progress|closed|abandoned)\b", head, re.I)
            task_statuses[task_id] = m.group(1).lower() if m else "open"
            criteria = parse_acceptance_criteria(text)
            all_deferrals.extend(criteria["deferred"])

        open_count = 0
        for ref in all_deferrals:
            status = task_statuses.get(ref)
            if status in ("closed", "abandoned"):
                continue
            open_count += 1
        return open_count
    except Exception:
        return 0


def task_id_exists(claude_dir, task_id):
    """Check whether `task_id` resolves to a file or an INDEX.md entry."""
    if not claude_dir or not task_id:
        return False
    tasks_dir = os.path.join(claude_dir, "tasks")
    if not os.path.isdir(tasks_dir):
        return False
    # Direct filename match (with or without .md)
    for cand in (task_id, task_id + ".md"):
        if os.path.isfile(os.path.join(tasks_dir, cand)):
            return True
    # Index lookup
    index_path = os.path.join(tasks_dir, "INDEX.md")
    if os.path.isfile(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_text = f.read()
            # Anchor with `[^-\w]` on both sides so TASK-001 doesn't match
            # inside TASK-001-extra. Use lookarounds to allow start/end-of-text.
            if re.search(
                rf"(?<![-\w]){re.escape(task_id)}(?![-\w])", index_text
            ):
                return True
        except Exception:
            pass
    return False
