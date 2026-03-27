#!/usr/bin/env python3
"""Shared telemetry logger for Clauding Thought hook scripts.

Writes JSONL entries to <project>/.claude/hook-log.jsonl.
All operations are fail-open: logging errors are silently swallowed
so they never interfere with hook decisions.
"""
import json
import os
import time
from datetime import datetime, timezone

MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB
ROTATION_SUFFIX = ".1.jsonl"


class TelemetryLogger:
    def __init__(self, hook_name, event, matcher=""):
        self.hook_name = hook_name
        self.event = event
        self.matcher = matcher
        self.start_time = time.monotonic()
        self._log_dir = self._find_log_dir()

    @staticmethod
    def _find_log_dir():
        """Locate .claude/ by walking up from cwd to find the nearest one."""
        try:
            current = os.getcwd()
            for _ in range(10):  # limit depth to avoid infinite loop
                claude_dir = os.path.join(current, ".claude")
                if os.path.isdir(claude_dir):
                    return claude_dir
                parent = os.path.dirname(current)
                if parent == current:
                    break
                current = parent
        except Exception:
            pass
        return None

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
            if context:
                entry["context"] = context

            log_path = os.path.join(self._log_dir, "hook-log.jsonl")
            self._rotate_if_needed(log_path)
            with open(log_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # fail-open: never interfere with hook decision

    def _rotate_if_needed(self, log_path):
        """Rotate log file if it exceeds MAX_LOG_SIZE."""
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > MAX_LOG_SIZE:
                rotated = log_path.replace(".jsonl", ROTATION_SUFFIX)
                if os.path.exists(rotated):
                    os.remove(rotated)
                os.rename(log_path, rotated)
        except Exception:
            pass  # fail-open
