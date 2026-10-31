#!/usr/bin/env python3
"""Read tool results from a Claude Code session transcript.

Shape relied on, confirmed against a captured Claude Code 2.1 session
(tolerant of extra fields): one JSON object per line.
- `type: "user"` entries that carry no `tool_result` block are human turns:
  the boundary between turns. A slash-command invocation is one too (text
  wrapped in `<command-message>` tags); so is a prompt with an attached image.
  Entries with `isMeta` (injected skill bodies, Stop-hook feedback) and
  `<local-command-...>` / `<system-reminder>` / `<user-prompt-submit-hook>`
  wrappers are not boundaries.
- `type: "user"` entries whose content is a list of `tool_result` blocks carry
  tool output. Each block's `tool_use_id` points at a `tool_use` block in an
  earlier `type: "assistant"` entry, which names the tool and its input.
- Entries with `isSidechain` true belong to subagents and are ignored.

Only the tail of a very large transcript is read.
"""
import json
import os
import re

MAX_TAIL_BYTES = 8 * 1024 * 1024

_WRAPPER_RE = re.compile(
    r"^\s*(<local-command|<system-reminder|<user-prompt-submit-hook|\[Request interrupted|Stop hook feedback:)",
    re.I,
)


def _entries(transcript_path):
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as fh:
            if size > MAX_TAIL_BYTES:
                fh.seek(size - MAX_TAIL_BYTES)
                fh.readline()
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            p.get("text") or "" for p in content if isinstance(p, dict) and p.get("type") == "text"
        )
    return ""


def tool_uses(entries):
    """tool_use_id -> {"name": tool name, "command": Bash command or ''} from
    assistant entries (sidechains excluded)."""
    uses = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                inp = block.get("input") if isinstance(block.get("input"), dict) else {}
                uses[block["id"]] = {"name": block.get("name") or "", "command": str(inp.get("command") or "")}
    return uses


def classify(entry):
    """('prompt', text) for a human turn boundary, ('tool_result', [blocks])
    for tool output, (None, '') for anything else."""
    if not isinstance(entry, dict) or entry.get("type") != "user" or entry.get("isSidechain"):
        return None, ""
    message = entry.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        if results:
            return "tool_result", results
    text = _text_of(content)
    if entry.get("isMeta") or _WRAPPER_RE.match(text or ""):
        return None, ""
    if isinstance(content, str) or isinstance(content, list):
        return "prompt", text
    return None, ""


def tool_results(transcript_path, turns=1, tools=None):
    """Tool results of the last `turns` turns, newest first, as dicts
    {"tool": name, "command": str, "text": str}. `tools` restricts by tool
    name (e.g. ("Bash",)); results whose tool_use cannot be found are reported
    with tool "". Returns None when the transcript cannot be read."""
    entries = _entries(transcript_path)
    if entries is None:
        return None
    uses = tool_uses(entries)
    turns = max(1, int(turns or 1))
    seen_prompts = 0
    out = []
    for entry in reversed(entries):
        kind, payload = classify(entry)
        if kind == "prompt":
            seen_prompts += 1
            if seen_prompts >= turns:
                break
        elif kind == "tool_result":
            for block in payload:
                use = uses.get(block.get("tool_use_id") or "", {"name": "", "command": ""})
                if tools and use["name"] not in tools:
                    continue
                out.append({"tool": use["name"], "command": use["command"], "text": _text_of(block.get("content"))})
    return out


def tool_results_in_window(transcript_path, turns=1, tools=None):
    """Concatenated text of tool_results(); None when unreadable."""
    results = tool_results(transcript_path, turns, tools)
    if results is None:
        return None
    return "\n".join(r["text"] for r in results)
