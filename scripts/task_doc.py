#!/usr/bin/env python3
"""Shared helpers for hook scripts that read the project's .claude/ directory.

All operations are fail-soft: missing files, parse errors, or unexpected
shapes return empty/neutral values so hooks can decide silently.
"""
import os
import re


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

    Active = the first 1KB declares status open or in_progress (markdown bold
    around the key or value is tolerated). If several match, the most recently
    modified wins.
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
            if re.search(r"status:[\s*]*(open|in_progress)\b", text[:1024], re.I):
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


# Fenced code block (```...``` or ~~~...~~~).
_FENCE_RE = re.compile(r"(?ms)^\s*(```|~~~)[^\n]*\n.*?^\s*\1\s*$")
# Inline code span (single or double backticks, non-greedy).
_INLINE_CODE_RE = re.compile(r"`{1,2}[^`\n]+?`{1,2}")
# Markdown blockquote line.
_BLOCKQUOTE_RE = re.compile(r"(?m)^\s*>.*$")


def strip_fenced_blocks(text):
    """Remove fenced code blocks."""
    if not text:
        return text
    return _FENCE_RE.sub("", text)


def strip_code_and_quotes(text):
    """Remove fenced blocks, inline code, and blockquoted lines.

    Used before scanning response text for phrasing patterns so quoted
    content, code examples, and block quotes do not trigger false positives.
    """
    if not text:
        return text
    text = _FENCE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    return text
