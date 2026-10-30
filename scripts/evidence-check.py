#!/usr/bin/env python3
"""Stop hook: refuses "tests pass" / "build succeeds" claims with no evidence.

Reference it reads: the transcript's tool results in the last N turns
(`verification.claim_window_turns`, default 1). Evidence is output matching a
built-in test-runner or build-tool success pattern, or any gate's
`success_pattern` declared in `manifest.verification.gates`.

Pushes back with exit 2 once per turn (honours `stop_hook_active`); Claude
Code then continues with the feedback. Fail-open on any error.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    from hook_telemetry import TelemetryLogger
    from task_doc import find_claude_dir, load_manifest, strip_code_and_quotes, verification
    from transcript import tool_results_in_window

    logger = TelemetryLogger("evidence-check", "Stop", hook_input=data)

    if data.get("stop_hook_active"):
        logger.log("allow", reason="stop_hook_active")
        sys.exit(0)

    response = data.get("last_assistant_message") or data.get("response") or ""
    if not response:
        logger.log("allow")
        sys.exit(0)

    claim = CLAIM_RE.search(strip_code_and_quotes(response) or "")
    if not claim:
        logger.log("allow")
        sys.exit(0)

    ver = verification(load_manifest(find_claude_dir(data.get("cwd"))))
    window = ver.get("claim_window_turns") or 1

    output = tool_results_in_window(data.get("transcript_path", ""), window)
    if output is None:
        logger.log("allow", reason="transcript unavailable",
                   context={"claim": claim.group(0)[:120]})
        sys.exit(0)

    if EVIDENCE_RE.search(output):
        logger.log("allow", reason="evidence in window")
        sys.exit(0)
    for g in ver.get("gates") or []:
        try:
            if isinstance(g, dict) and g.get("success_pattern") and \
                    re.search(g["success_pattern"], output, re.I | re.M):
                logger.log("allow", reason="gate in window", context={"gate": g.get("name", "")})
                sys.exit(0)
        except re.error:
            continue

    logger.log("feedback", reason="success claim without test/build output",
               context={"claim": claim.group(0)[:120]})
    print(
        "You claimed tests pass or the build succeeds, but no test or build output "
        f"appears in the tool results of the last {window} turn(s). Run the actual "
        "command and quote its result before claiming success.",
        file=sys.stderr
    )
    sys.exit(2)

except SystemExit:
    raise
except Exception:
    sys.exit(0)  # fail-open
