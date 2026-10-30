#!/usr/bin/env python3
"""Shared helpers for hook scripts that read the project's .claude/ directory.

All operations are fail-soft: missing files, parse errors, or unexpected
shapes return empty/neutral values so hooks can decide silently.
"""
import json
import os
import re
import sys

IS_WINDOWS = sys.platform.startswith("win")


# --------------------------------------------------------------------------
# Locating things
# --------------------------------------------------------------------------

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


def project_root(claude_dir):
    return os.path.dirname(os.path.abspath(claude_dir)) if claude_dir else None


def load_manifest(claude_dir):
    """Return the parsed manifest.json, or {} when missing or unreadable."""
    if not claude_dir:
        return {}
    try:
        path = os.path.join(claude_dir, "manifest.json")
        if not os.path.isfile(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def task_heading(manifest, key, default):
    """Heading text configured under task_docs.headings.<key>, else default."""
    try:
        value = (manifest or {}).get("task_docs", {}).get("headings", {}).get(key)
        return value.strip() if isinstance(value, str) and value.strip() else default
    except Exception:
        return default


def verification(manifest):
    """The manifest's verification block, or {}."""
    try:
        block = (manifest or {}).get("verification", {})
        return block if isinstance(block, dict) else {}
    except Exception:
        return {}


# --------------------------------------------------------------------------
# Task docs
# --------------------------------------------------------------------------

# status: open / in_progress / in progress / in-progress / active, any case,
# markdown bold or underscores around key or value tolerated.
_ACTIVE_STATUS_RE = re.compile(
    r"status[\s*_]*:[\s*_]*(open|in[\s_-]?progress|active)\b", re.I
)


def find_active_tasks(claude_dir, manifest=None):
    """All task docs whose first 2 KB declare an active status, newest first.

    Honours task_docs.directory (default "tasks"). Returns [(path, text), ...].
    """
    if not claude_dir:
        return []
    try:
        directory = (manifest or {}).get("task_docs", {}).get("directory") or "tasks"
        tasks_dir = os.path.join(claude_dir, directory)
        if not os.path.isdir(tasks_dir):
            return []
        found = []
        for fname in os.listdir(tasks_dir):
            if not fname.endswith(".md") or fname.upper() == "INDEX.MD":
                continue
            fpath = os.path.join(tasks_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue
            if _ACTIVE_STATUS_RE.search(text[:2048]):
                found.append((os.path.getmtime(fpath), fpath, text))
        found.sort(reverse=True)
        return [(p, t) for _, p, t in found]
    except Exception:
        return []


def find_active_task(claude_dir, manifest=None):
    """(path, text) of the most recently modified active task doc, or (None, None)."""
    active = find_active_tasks(claude_dir, manifest)
    return active[0] if active else (None, None)


def extract_section(text, heading):
    """Body of a `## Heading` or `### Heading` section (case-insensitive, trailing
    colon tolerated), up to the next heading of level 1-3 or EOF."""
    if not text or not heading:
        return ""
    pattern = rf"(?im)^#{{2,3}}\s+{re.escape(heading)}\s*:?\s*$"
    m = re.search(pattern, text)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"(?m)^#{1,3}\s", rest)
    return rest[: n.start()] if n else rest


_LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")


def list_items(section_text):
    """Items of a markdown list: markers, backticks, and trailing comments stripped."""
    items = []
    for line in strip_fenced_blocks(section_text or "").splitlines():
        m = _LIST_LINE_RE.match(line)
        if not m:
            continue
        item = m.group(1).strip()
        item = re.split(r"\s+(?:#|//|<!--)", item, maxsplit=1)[0].strip()
        item = item.strip("`").strip()
        if item:
            items.append(item)
    return items


# --------------------------------------------------------------------------
# Path globs (same vocabulary as rule `paths:` frontmatter)
# --------------------------------------------------------------------------

def normalize_path(path):
    return (path or "").replace("\\", "/")


def rel_project_path(file_path, root):
    """Project-relative, forward-slash path, or None when outside the project."""
    if not file_path or not root:
        return None
    try:
        fp = normalize_path(os.path.abspath(file_path))
        rt = normalize_path(os.path.abspath(root)).rstrip("/") + "/"
        if IS_WINDOWS:
            inside = fp.lower().startswith(rt.lower())
        else:
            inside = fp.startswith(rt)
        if not inside:
            return None
        return fp[len(rt):]
    except Exception:
        return None


def expand_braces(glob):
    """`a/{b,c}/d` -> ['a/b/d', 'a/c/d'] (nested braces handled by recursion)."""
    m = re.search(r"\{([^{}]*)\}", glob)
    if not m:
        return [glob]
    head, tail = glob[: m.start()], glob[m.end():]
    out = []
    for alt in m.group(1).split(","):
        out.extend(expand_braces(head + alt.strip() + tail))
    return out


def glob_to_regex(glob):
    """Anchored regex for one glob: `**` any path, `*` within a segment, `?` one char."""
    parts = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            parts.append(".*")
            i += 2
        elif glob[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(parts) + "$", re.I)


def path_matches(rel_path, globs):
    """True when rel_path matches any glob. A glob without `/` also matches the
    basename, so `*.md` means any markdown file at any depth."""
    rel = normalize_path(rel_path).lstrip("./")
    base = rel.rsplit("/", 1)[-1]
    for raw in globs or []:
        for g in expand_braces(normalize_path(raw).strip().lstrip("./")):
            if not g:
                continue
            try:
                rx = glob_to_regex(g)
            except re.error:
                continue
            if rx.match(rel):
                return True
            if "/" not in g and rx.match(base):
                return True
            if g.endswith("/**") and rel.lower() == g[:-3].lower():
                return True
    return False


# --------------------------------------------------------------------------
# Text cleanup
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"(?ms)^\s*(```|~~~)[^\n]*\n.*?^\s*\1\s*$")
_INLINE_CODE_RE = re.compile(r"`{1,2}[^`\n]+?`{1,2}")
_BLOCKQUOTE_RE = re.compile(r"(?m)^\s*>.*$")


def strip_fenced_blocks(text):
    if not text:
        return text
    return _FENCE_RE.sub("", text)


def strip_code_and_quotes(text):
    """Remove fenced blocks, inline code, and blockquoted lines before scanning
    response text for phrasing, so quoted or documented phrases do not count."""
    if not text:
        return text
    text = _FENCE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    return text
