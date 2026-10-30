#!/usr/bin/env python3
"""Stop hook — refuses "tests pass" / "build succeeds" claims with no evidence.

Input contract (Claude Code hooks reference): a Stop hook receives
`last_assistant_message` (the final response text), `transcript_path` (the
session's JSONL transcript), and `stop_hook_active`.

Behaviour: if the final response claims success, the hook scans the tool
results of the CURRENT turn in the transcript for test-runner or build-tool
success output. If none is found it exits 2 with feedback, and Claude Code
continues the turn with that feedback. When `stop_hook_active` is set the
hook allows, so it cannot loop.

Transcript shape relied on (tolerant of extra fields): one JSON object per
line; `type: "user"` entries whose `message.content` is a plain string are
human prompts (turn boundaries); `type: "user"` entries whose content is a
list of `tool_result` blocks carry tool output, as a string or as a list of
`text` blocks.
"""
import sys, json, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger

MAX_TAIL_BYTES = 8 * 1024 * 1024  # only the tail of a very large transcript is read

CLAIM_RE = re.compile(
    r"(all\s+tests?\s+pass|tests?\s+(are\s+|now\s+)?pass(ing|ed)?\b|build\s+succeed|build\s+pass"
    r"|no\s+(test\s+)?errors|everything\s+(works|passes|compiles)"
    r"|tests?\s+are\s+green|all\s+checks?\s+pass|ci\s+(is\s+)?green)",
    re.I,
)

EVIDENCE_RE = re.compile("|".join([
    # Jest / Vitest / Mocha
    r"Tests?:\s*\d+\s+(passed|succeeded)",
    r"\d+\s+passing",
    r"Test Suites?:\s*\d+\s+passed",
    # Pytest
    r"\d+\s+passed\s+in\s+[\d.]+s",
    r"=+\s*\d+\s+passed",
    # PHPUnit / Pest
    r"OK\s*\(\d+\s+tests?",
    r"Tests:\s*\d+,\s*Assertions:",
    r"Tests:\s*\d+\s+passed",
    r"PASS\s+Tests\\",
    # Go
    r"^ok\s+\S+\s+[\d.]+s",
    r"^PASS$",
    # Rust
    r"test result: ok\.",
    # RSpec / minitest
    r"\d+\s+examples?,\s*0\s+failures?",
    r"\d+\s+runs,\s*\d+\s+assertions,\s*0\s+failures",
    # JUnit / Maven / Gradle
    r"BUILD SUCCESS(FUL)?",
    r"Tests run:\s*\d+.*Failures:\s*0",
    # .NET
    r"Passed!\s+-\s+Failed:\s*0",
    r"Test Run Successful",
    # Generic build
    r"Compilation finished successfully",
    r"compiled successfully",
    r"Build complete",
    r"^(Exit code:?\s*0|exit status 0)\s*$",
]), re.I | re.M)


def tool_output_of_current_turn(transcript_path):
    """Concatenate tool-result text from the current turn, newest entry first."""
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

    chunks = []
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "user":
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            break  # human prompt: start of the current turn
        if not isinstance(content, list):
            continue
        saw_tool_result = False
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            saw_tool_result = True
            inner = block.get("content")
            if isinstance(inner, str):
                chunks.append(inner)
            elif isinstance(inner, list):
                for part in inner:
                    if isinstance(part, dict) and part.get("type") == "text":
                        chunks.append(part.get("text") or "")
        if not saw_tool_result:
            break  # a human prompt written as text blocks
    return "\n".join(chunks)


try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    logger = TelemetryLogger("evidence-check", "Stop")

    if data.get("stop_hook_active"):
        logger.log("allow", reason="stop_hook_active — already continued once this turn")
        sys.exit(0)

    response = data.get("last_assistant_message") or data.get("response") or ""
    if not response:
        logger.log("allow")
        sys.exit(0)

    claim = CLAIM_RE.search(response)
    if not claim:
        logger.log("allow")
        sys.exit(0)

    output = tool_output_of_current_turn(data.get("transcript_path", ""))
    if output is None:
        # No transcript to check against: cannot judge, so do not block.
        logger.log("allow", reason="transcript unavailable",
                   context={"matched_phrase": claim.group(0)[:200]})
        sys.exit(0)

    if EVIDENCE_RE.search(output):
        logger.log("allow")
        sys.exit(0)

    logger.log("feedback",
               reason="Success claim without test/build output in this turn",
               context={"matched_phrase": claim.group(0)[:200]})
    print(
        "You claimed tests pass or the build succeeds, but no test or build output "
        "appears in this turn's tool results. Run the actual command and quote its "
        "result before claiming success.",
        file=sys.stderr
    )
    sys.exit(2)

except SystemExit:
    raise
except Exception:
    sys.exit(0)  # fail-open
