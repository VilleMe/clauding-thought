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


# Matches inline code spans (single or double backticks, non-greedy).
_INLINE_CODE_RE = re.compile(r"`{1,2}[^`\n]+?`{1,2}")

# Matches markdown blockquote lines (lines beginning with `>`).
_BLOCKQUOTE_RE = re.compile(r"(?m)^\s*>.*$")


def strip_code_and_quotes(text):
    """Remove fenced blocks, inline code, and blockquoted lines from text.

    Used before scanning agent response text for dismissal/rationalization
    phrases so that quoted content, code examples, and block quotes do not
    trigger false positives.
    """
    if not text:
        return text
    text = _FENCE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    return text


def has_opt_out_marker(text):
    """True when the task doc declares no user-observable change.

    Accepted forms:
    - `no-user-observable-change: true` anywhere in the first 2KB
    - A `## No User-Observable Change` section (case-insensitive) with any body

    Used by thesis-check to skip enforcement for infrastructure/refactor tasks
    that deliberately have no user-visible thesis.
    """
    if not text:
        return False
    head = text[:2048]
    if re.search(
        r"no-user-observable-change[\s*]*:[\s*]*true\b", head, re.I
    ):
        return True
    if re.search(
        r"(?m)^##\s+no\s+user[- ]observable\s+change\b", text, re.I
    ):
        return True
    return False


_THESIS_SECTION_RE = re.compile(
    r"(?m)^##\s+thesis\s+demo\s*\n", re.I
)

# Timestamps accepted under **Demonstrated:** — either an ISO 8601 datetime
# (2026-04-20T14:30:00Z / 2026-04-20T14:30:00+00:00) or a plain date.
_THESIS_TIMESTAMP_RE = re.compile(
    r"\*\*demonstrated:\*\*\s*"
    r"(?P<ts>\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)",
    re.I,
)


def extract_thesis_demo(text):
    """Return the `## Thesis Demo` section body, or '' if absent."""
    return extract_section(text, "Thesis Demo")


def validate_thesis_demo(text, max_age_hours=24):
    """Inspect the `## Thesis Demo` section and report what's missing.

    Returns a dict:
    - present:     section exists at all
    - has_claim:   Claim subsection present
    - has_script:  Script subsection present
    - has_observable: Observable subsection present
    - demonstrated_ts: parsed datetime or None
    - fresh:       demonstrated_ts within max_age_hours (if parsed)

    Does NOT attempt to verify the content of Claim/Script/Observable — that
    is structurally impossible from regex. The value is forcing the author to
    produce the structured artifact.

    Callers that gate on thesis_demo should also gate on is_task_ready_to_close
    so the check only fires when the task is actually attempting closure. A
    task with no `## Acceptance Criteria` section is never considered ready to
    close by this helper, which means thesis_demo enforcement silently skips
    prose-style task docs. Projects using prose tasks should also enable
    `criteria_format` so the author is nudged toward the structured form.
    """
    from datetime import datetime, timezone, timedelta

    result = {
        "present": False,
        "has_claim": False,
        "has_script": False,
        "has_observable": False,
        "demonstrated_ts": None,
        "fresh": False,
    }
    if not text:
        return result
    section = extract_thesis_demo(text)
    if not section.strip():
        return result
    result["present"] = True
    # Strip fenced blocks before checking subsections so examples inside code
    # fences don't falsely satisfy the requirements.
    clean = strip_fenced_blocks(section)
    result["has_claim"] = bool(re.search(r"\*\*claim:\*\*", clean, re.I))
    result["has_script"] = bool(re.search(r"\*\*script:\*\*", clean, re.I))
    result["has_observable"] = bool(
        re.search(r"\*\*observable:\*\*", clean, re.I)
    )
    m = _THESIS_TIMESTAMP_RE.search(clean)
    if m:
        ts_text = m.group("ts").replace("Z", "+00:00").replace(" ", "T")
        try:
            if "T" in ts_text:
                ts = datetime.fromisoformat(ts_text)
            else:
                ts = datetime.fromisoformat(ts_text + "T00:00:00+00:00")
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            result["demonstrated_ts"] = ts
            age = datetime.now(timezone.utc) - ts
            result["fresh"] = age <= timedelta(hours=max_age_hours)
        except (ValueError, TypeError):
            pass
    return result


def is_task_ready_to_close(criteria):
    """True when every acceptance-criterion is either [x] or [deferred:...].

    Accepts the dict returned by parse_acceptance_criteria. A task with zero
    criteria returns False — we cannot tell if it is ready to close without
    the author declaring done-ness somewhere. This is deliberately conservative:
    the ledger check that uses this helper should not fire on tasks without
    criteria at all.
    """
    if not criteria:
        return False
    total = (
        criteria.get("checked", 0)
        + criteria.get("unchecked", 0)
        + len(criteria.get("deferred", []))
        + criteria.get("invalid", 0)
    )
    if total == 0:
        return False
    return (
        criteria.get("unchecked", 0) == 0
        and criteria.get("invalid", 0) == 0
    )


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
