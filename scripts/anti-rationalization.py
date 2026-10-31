#!/usr/bin/env python3
"""Stop hook: pushes back when the final response dismisses an issue it found.

Runs only while a task doc is active; outside a task there is no finding
ledger to point at. Fires once per turn (honours `stop_hook_active`).

A dismissal ("out of scope", "pre-existing", "unrelated to this task",
"flaky", "won't fix", "acceptable tradeoff") passes when, near it, the
response either records the item somewhere with a reference (a task id,
issue number, ADR, the task doc's Implementation or Lessons section) or
commits to handling it now; when the user themself asked for that scoping
("as you asked", "per your instructions"); or when "scope" is used in its
programming sense (the scope of a closure, variable, block).

Fenced blocks, inline code and blockquotes are stripped before scanning.
An internal error is reported on stderr with exit 1 (visible, non-blocking).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DISMISSAL_RE = re.compile("|".join([
    r"pre-existing\s+(?:issue|bug|problem|debt|failure|test|behaviou?r|condition)",
    r"(?:was|were|is|are)\s+(?:already\s+)?(?:failing|broken)\s+before",
    r"already\s+existed\s+before",
    r"out\s+of\s+scope",
    r"outside\s+(?:the\s+|of\s+)?scope",
    r"beyond\s+the\s+scope",
    r"not\s+(?:in|within)\s+(?:the\s+)?scope",
    r"not\s+part\s+of\s+(?:this|the)\s+(?:task|change|work)",
    r"unrelated\s+to\s+(?:this|the|our|my)\s+(?:change|task|work|pr|diff)",
    r"not\s+related\s+to\s+(?:our|the|this)\s+(?:change|task|work)",
    r"separate\s+(?:issue|problem|ticket|pr|bug)",
    r"orthogonal\s+to\s+(?:our|the|this)",
    r"we\s+don.t\s+need\s+to\s+(?:fix|address|handle)",
    r"not\s+our\s+responsibility",
    r"left\s+for\s+(?:future|later|a\s+follow-up)",
    r"defer(?:red)?\s+to\s+(?:next|later|future|a\s+follow-up)",
    r"technical\s+debt\s+to\s+(?:be\s+)?address(?:ed)?\s+later",
    r"flaky\s+(?:test|spec|check)|(?:test|spec)\s+is\s+flaky",
    r"won.t\s+fix",
    r"known\s+(?:issue|problem|limitation)",
    r"deliberate\s+trade\s*-?\s*off",
    r"acceptable\s+(?:deviation|violation|exception|compromise|tradeoff|trade-off|risk)",
    r"(?:this|that|the)\s+(?:is|was)\s+(?:a\s+)?(?:justified|intentional|acceptable)\s+(?:violation|deviation|exception|risk|gap)",
    r"(?:minor|low[- ]risk|negligible)\s+(?:violation|deviation|issue|finding)",
    r"not\s+(?:a\s+)?(?:real|actual|true|genuine)\s+(?:violation|issue|problem|finding)",
]), re.I)

# Near the dismissal: a record with a reference, or a commitment to handle it now
NEGATION_RE = re.compile("|".join([
    r"\bTASK-[\w-]+\b", r"(?<![\w/])#\d+\b", r"\b[\w-]+\.md\b", r"\bADR-?\d+\b", r"\bticket\b", r"\bissue\s+#?\d+",
    r"(?:record|not|logg|document|track|add|fil|captur|list)(?:ed|ing|s)?\s+(?:it|this|that|them|the\s+\w+)?\s*"
    r"(?:under|in|to|as)\s+(?:the\s+)?(?:implementation|lessons|rule\s+candidates|task\s+doc|task\s+document|"
    r"backlog|tech\s+debt|follow-up|suppressions)",
    r"(?:I(?:'ll|\s+will)|let\s+me|let's|going\s+to|we\s+should|we\s+must)\s+(?:fix|address|handle|resolve|do|take)\s+"
    r"(?:it|this|that|the\s+\w+)?\s*(?:now|next|first|right\s+away|immediately|before\s+\w+|in\s+this\s+(?:task|turn|session|pass))",
    r"(?:fix|address|resolv|handl)(?:e|ed|ing)\s+(?:it|this|that)\s+(?:now|next|first|below|in\s+this\s+(?:task|turn))",
]), re.I)

# The user asked for the scoping, or "scope" means a programming scope
EXEMPT_RE = re.compile("|".join([
    r"(?:as|per)\s+(?:you|your)\s+(?:asked|requested|said|instruct(?:ed|ions?)|request|direction)",
    r"you\s+(?:asked|told|said|requested|decided)",
    r"scope\s+of\s+(?:the|a|this|its|that|an?)\s+(?:closure|function|variable|block|module|class|method|loop|"
    r"component|file|lambda|generic|type|query|transaction)",
    r"(?:out\s+of\s+|outside\s+(?:the\s+)?)scope\s+(?:after|when|once|at\s+the\s+end|until)",
    r"lexical(?:ly)?\s+scope|block\s+scope|function\s+scope|variable\s+scope|scope\s+chain|"
    r"(?:block|function|loop|closure)\s+(?:ends|exits|returns)",
]), re.I)


def read_hook_input():
    return json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))


try:
    data = read_hook_input()
except Exception:
    sys.exit(0)

try:
    from hook_telemetry import TelemetryLogger
except Exception:
    class TelemetryLogger:
        def __init__(self, *a, **k): pass
        def log(self, *a, **k): pass

try:
    from task_doc import find_active_tasks, find_claude_dir, load_manifest, strip_code_and_quotes

    logger = TelemetryLogger("anti-rationalization", "Stop", hook_input=data)

    if data.get("stop_hook_active"):
        logger.log("allow", reason="stop_hook_active")
        sys.exit(0)

    response = data.get("last_assistant_message") or data.get("response") or ""
    if not isinstance(response, str) or not response:
        logger.log("allow")
        sys.exit(0)

    claude_dir = find_claude_dir(data.get("cwd"))
    if not claude_dir or not find_active_tasks(claude_dir, load_manifest(claude_dir)):
        logger.log("allow", reason="no active task")
        sys.exit(0)

    text = strip_code_and_quotes(response)
    if not text or not text.strip():
        logger.log("allow")
        sys.exit(0)

    skipped = "no dismissal"
    for match in DISMISSAL_RE.finditer(text):
        near = text[max(0, match.start() - 220): match.end() + 220]
        if EXEMPT_RE.search(near):
            skipped = "exempt phrasing"
            continue
        if NEGATION_RE.search(near):
            skipped = "recorded or handled"
            continue
        logger.log("feedback", reason="dismissal without a recorded follow-up",
                   pattern=match.group(0)[:100], context={"matched_phrase": match.group(0)[:200]})
        print(
            "You set an issue aside without recording it. Either handle it now, or record it under "
            "the task doc's Implementation or Lessons section with a reference (task id, issue, "
            "ADR), and say so. Do not dismiss findings silently.",
            file=sys.stderr,
        )
        sys.exit(2)

    logger.log("allow", reason=skipped)
    sys.exit(0)

except SystemExit:
    raise
except Exception as e:
    print(f"anti-rationalization: internal error ({type(e).__name__}); allowed by default", file=sys.stderr)
    sys.exit(1)
