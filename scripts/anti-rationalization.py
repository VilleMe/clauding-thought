#!/usr/bin/env python3
"""Stop hook — detects when Claude rationalizes away issues it should address."""
import sys, json, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    logger = TelemetryLogger("anti-rationalization", "Stop")

    response = data.get("response", "")
    if not response:
        logger.log("allow")
        sys.exit(0)

    # Phrases that often indicate dismissal of real issues
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
        # QC rationalization — downgrading real violations
        r"deliberate\s+trade\s*-?\s*off",
        r"acceptable\s+(deviation|violation|exception|compromise|tradeoff|trade-off)",
        r"(this|the)\s+(is|was)\s+(a\s+)?(justified|intentional|acceptable)\b",
        r"(minor|low[- ]risk|negligible)\s+(violation|deviation|issue)",
        r"not\s+(a\s+)?(real|actual|true|genuine)\s+(violation|issue|problem)",
    ]

    # Phrases that negate dismissal — if these appear near the match, it's not a rationalization
    negation_patterns = [
        r"(I will|I'll|let me|let's|we should|we must|going to)\s+(fix|address|handle|resolve|document)",
        r"won.t\s+(dismiss|ignore|skip|overlook)",
        r"(fix|address|resolv)(e|ed|ing)\s+(this|it|the issue)",
        r"documented?\s+(this|it|the issue)\s+(as|in)\s+(tech debt|a ticket|the task)",
        r"adding\s+(this\s+)?to\s+(tech debt|backlog|task)",
    ]

    # Check for dismissal
    dismissal_regex = re.compile("|".join(dismissal_patterns), re.I)
    negation_regex = re.compile("|".join(negation_patterns), re.I)

    match = dismissal_regex.search(response)
    if match:
        # Look for negation within 200 chars around the match
        start = max(0, match.start() - 200)
        end = min(len(response), match.end() + 200)
        context = response[start:end]

        if not negation_regex.search(context):
            logger.log("feedback",
                       reason="Rationalization detected — dismissal without acknowledgment",
                       pattern=match.group(0)[:100],
                       context={"matched_phrase": match.group(0)[:200]})
            print(
                "If you identified an issue during this task, address it or document it as tech debt with a tracking ID. "
                "Don't dismiss issues without explicit acknowledgment and a plan.",
                file=sys.stderr
            )
            sys.exit(2)

    logger.log("allow")
    sys.exit(0)

except SystemExit:
    raise  # let sys.exit() through
except Exception:
    sys.exit(0)  # fail-open: unexpected errors must not block the hook
