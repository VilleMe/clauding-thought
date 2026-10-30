#!/usr/bin/env python3
"""Stop hook — pushes back when the final response dismisses an issue it found.

Input contract (Claude Code hooks reference): a Stop hook receives
`last_assistant_message` (the text of the final response) and
`stop_hook_active` (true when this Stop was already caused by a Stop hook).

Behaviour: if the response contains dismissal language ("out of scope",
"pre-existing issue", "acceptable tradeoff", ...) with no nearby commitment to
fix or track it, exit 2 with feedback on stderr. Claude Code then continues
the turn with that feedback. The hook never fires twice in a row for one
turn: when `stop_hook_active` is set it allows, so it cannot loop.

Fenced code, inline code, and blockquotes are stripped before scanning so
quoted or documented phrases do not count.
"""
import sys, json, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger
from task_doc import strip_code_and_quotes

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    logger = TelemetryLogger("anti-rationalization", "Stop")

    if data.get("stop_hook_active"):
        logger.log("allow", reason="stop_hook_active — already continued once this turn")
        sys.exit(0)

    response = data.get("last_assistant_message") or data.get("response") or ""
    if not response:
        logger.log("allow")
        sys.exit(0)

    response = strip_code_and_quotes(response)
    if not response.strip():
        logger.log("allow")
        sys.exit(0)

    dismissal_patterns = [
        r"pre-existing\s+(issue|bug|problem|debt)",
        r"out\s+of\s+scope",
        r"separate\s+(issue|concern|problem|ticket)",
        r"not\s+related\s+to\s+(our|the|this)\s+(change|task|work)",
        r"we\s+don.t\s+need\s+to\s+(fix|address|handle)",
        r"already\s+existed\s+before",
        r"beyond\s+the\s+scope",
        r"not\s+our\s+responsibility",
        r"outside\s+(the\s+)?scope",
        r"left\s+for\s+future\s+(iteration|sprint|work)",
        r"defer(red)?\s+to\s+(next|later|future)",
        r"technical\s+debt\s+to\s+(be\s+)?address(ed)?\s+later",
        r"orthogonal\s+to\s+(our|the|this)",
        # review-time rationalization — downgrading real violations
        r"deliberate\s+trade\s*-?\s*off",
        r"acceptable\s+(deviation|violation|exception|compromise|tradeoff|trade-off)",
        r"(this|the)\s+(is|was)\s+(a\s+)?(justified|intentional|acceptable)\b",
        r"(minor|low[- ]risk|negligible)\s+(violation|deviation|issue)",
        r"not\s+(a\s+)?(real|actual|true|genuine)\s+(violation|issue|problem)",
    ]

    # A commitment near the match means it is being handled, not dismissed.
    negation_patterns = [
        r"(I will|I'll|let me|let's|we should|we must|going to)\s+(fix|address|handle|resolve|document|track)",
        r"won.t\s+(dismiss|ignore|skip|overlook)",
        r"(fix|address|resolv|track)(e|ed|ing)\s+(this|it|the issue)",
        r"documented?\s+(this|it|the issue)\s+(as|in)\s+(tech debt|a ticket|the task)",
        r"adding\s+(this\s+)?to\s+(tech debt|backlog|the task|a follow-up)",
        r"(flagg|not)(ed|ing)?\s+(this\s+)?for\s+(you|the user|review)",
    ]

    dismissal_regex = re.compile("|".join(dismissal_patterns), re.I)
    negation_regex = re.compile("|".join(negation_patterns), re.I)

    match = dismissal_regex.search(response)
    if match:
        start = max(0, match.start() - 200)
        end = min(len(response), match.end() + 200)
        context = response[start:end]
        if not negation_regex.search(context):
            logger.log("feedback",
                       reason="Dismissal without acknowledgment",
                       pattern=match.group(0)[:100],
                       context={"matched_phrase": match.group(0)[:200]})
            print(
                "If you identified an issue during this task, address it or record it "
                "as tracked follow-up work with a reference. Do not dismiss issues "
                "without explicit acknowledgment and a plan.",
                file=sys.stderr
            )
            sys.exit(2)

    logger.log("allow")
    sys.exit(0)

except SystemExit:
    raise
except Exception:
    sys.exit(0)  # fail-open
