#!/usr/bin/env python3
"""Read tool results from a Claude Code session transcript.

Shape relied on, confirmed against a captured Claude Code 2.1 session
(tolerant of extra fields): one JSON object per line.
- `type: "user"` entries whose `message.content` is a plain string, or a list of
  `text` blocks, are human prompts: the boundary between turns. A slash-command
  invocation is one too; it arrives as text wrapped in `<command-message>` and
  `<command-name>` tags. Entries that carry `isMeta` (injected skill bodies,
  Stop-hook feedback), or whose text is a `<local-command-...>`,
  `<system-reminder>`, or `<user-prompt-submit-hook>` wrapper, are not boundaries.
- `type: "user"` entries whose content is a list of `tool_result` blocks carry
  tool output, as a string or a list of `text` blocks.
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
                fh.readline()  # drop the partial line
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


def classify(entry):
    """'prompt' for a human turn boundary, 'tool_result' with text for tool output,
    None for anything else."""
    if not isinstance(entry, dict) or entry.get("type") != "user" or entry.get("isSidechain"):
        return None, ""
    message = entry.get("message") or {}
    content = message.get("content")
    if isinstance(content, str) or (
        isinstance(content, list) and content and all(
            isinstance(b, dict) and b.get("type") == "text" for b in content)
    ):
        text = _text_of(content)
        if entry.get("isMeta") or _WRAPPER_RE.match(text or ""):
            return None, ""
        return "prompt", text
    if isinstance(content, list):
        chunks = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                chunks.append(_text_of(block.get("content")))
        if chunks:
            return "tool_result", "\n".join(chunks)
    return None, ""


def tool_results_in_window(transcript_path, turns=1):
    """Concatenated tool-result text from the last `turns` turns, newest first.

    Returns None when the transcript cannot be read (callers should not treat
    that as "no evidence"). A turn ends at a human prompt.
    """
    entries = _entries(transcript_path)
    if entries is None:
        return None
    turns = max(1, int(turns or 1))
    seen_prompts = 0
    chunks = []
    for entry in reversed(entries):
        kind, text = classify(entry)
        if kind == "prompt":
            seen_prompts += 1
            if seen_prompts >= turns:
                break
        elif kind == "tool_result" and text:
            chunks.append(text)
    return "\n".join(chunks)
