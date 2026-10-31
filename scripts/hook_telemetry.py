#!/usr/bin/env python3
"""Shared telemetry logger for Clauding Thought hook scripts.

Writes JSONL entries to <project>/.claude/hook-log.jsonl. Every entry carries
the hook name, event, decision, and duration; when the hook input is given,
also a short session id and, for file tools, the project-relative path.

The log never stores tool content: command previews are masked so that
tokens, keys, and passwords in a denied command are not written to disk.

All operations are fail-open: logging errors are silently swallowed so they
never interfere with hook decisions.
"""
import json
import os
import re
import time
from datetime import datetime, timezone

MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB
ROTATION_SUFFIX = ".1.jsonl"

_TOKEN_RE = re.compile(r"\S{16,}")


def mask(text, limit=160):
    """Shorten text and replace any long unbroken token with a placeholder."""
    if not isinstance(text, str):
        return ""
    return _TOKEN_RE.sub("<token>", text[:limit])


def find_claude_dir(start=None):
    """Nearest `.claude/` walking up from `start` (or cwd).

    Stops at the first directory that contains `.git` (after checking it), and
    never returns the user's own `~/.claude`, so a project without a `.claude/`
    cannot be mistaken for the home directory's.
    """
    try:
        home_claude = os.path.normcase(os.path.join(os.path.expanduser("~"), ".claude"))
        current = os.path.abspath(start) if start and os.path.isdir(start) else os.getcwd()
        for _ in range(12):
            candidate = os.path.join(current, ".claude")
            if os.path.isdir(candidate) and os.path.normcase(candidate) != home_claude:
                return candidate
            if os.path.exists(os.path.join(current, ".git")):
                return None
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    except Exception:
        pass
    return None


class TelemetryLogger:
    def __init__(self, hook_name, event, matcher="", hook_input=None):
        self.hook_name = hook_name
        self.event = event
        self.matcher = matcher
        self.start_time = time.monotonic()
        start = hook_input.get("cwd") if isinstance(hook_input, dict) else None
        self._log_dir = find_claude_dir(start)
        self.base = self._base_context(hook_input)

    def _base_context(self, hook_input):
        base = {}
        try:
            if not isinstance(hook_input, dict):
                return base
            sid = hook_input.get("session_id")
            if isinstance(sid, str) and sid:
                base["session"] = sid[:8]
            ti = hook_input.get("tool_input") or {}
            path = ti.get("file_path") or ti.get("notebook_path") if isinstance(ti, dict) else None
            if isinstance(path, str) and path and self._log_dir:
                root = os.path.dirname(self._log_dir)
                try:
                    rel = os.path.relpath(os.path.abspath(path), root)
                    if not rel.startswith(".."):
                        path = rel
                except ValueError:
                    pass
                base["file"] = path.replace("\\", "/")
        except Exception:
            pass
        return base

    def log(self, decision, reason=None, pattern=None, context=None):
        """Write a log entry. Never raises."""
        if self._log_dir is None:
            return
        try:
            elapsed = int((time.monotonic() - self.start_time) * 1000)
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "hook": self.hook_name,
                "event": self.event,
                "matcher": self.matcher,
                "decision": decision,
                "duration_ms": elapsed,
            }
            if reason:
                entry["reason"] = reason
            if pattern:
                entry["pattern"] = pattern
            merged = dict(self.base)
            if context:
                merged.update(context)
            if merged:
                entry["context"] = merged

            log_path = os.path.join(self._log_dir, "hook-log.jsonl")
            self._rotate_if_needed(log_path)
            with open(log_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # fail-open: never interfere with hook decision

    def _rotate_if_needed(self, log_path):
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > MAX_LOG_SIZE:
                rotated = log_path.replace(".jsonl", ROTATION_SUFFIX)
                if os.path.exists(rotated):
                    os.remove(rotated)
                os.rename(log_path, rotated)
        except Exception:
            pass


class NullLogger:
    """Stand-in when hook_telemetry cannot be imported: hooks still judge."""

    def __init__(self, *args, **kwargs):
        self.base = {}

    def log(self, *args, **kwargs):
        pass
