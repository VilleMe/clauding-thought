#!/usr/bin/env python3
"""Stop hook — verifies that 'tests pass' claims are backed by actual output."""
import sys, json, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    logger = TelemetryLogger("evidence-check", "Stop")

    response = data.get("response", "")
    if not response:
        logger.log("allow")
        sys.exit(0)

    # Check for success claims
    claim_pattern = (
        r"(all\s+tests?\s+pass|tests?\s+(are\s+)?passing|build\s+succeed|build\s+pass"
        r"|no\s+(test\s+)?errors|everything\s+(works|passes|compiles)"
        r"|tests?\s+are\s+green|all\s+checks?\s+pass|ci\s+(is\s+)?green)"
    )
    if not re.search(claim_pattern, response, re.I):
        logger.log("allow")
        sys.exit(0)

    # Evidence patterns covering major test frameworks and build tools
    evidence_patterns = [
        # Generic
        r"\bPASS(ED)?\b",
        r"\bOK\b",
        r"\bsuccess(ful)?\b",

        # Jest / Vitest / Mocha
        r"Tests?:\s*\d+\s+(passed|succeeded)",
        r"\d+\s+passing",
        r"Test Suites?:\s*\d+\s+passed",

        # Pytest
        r"\d+\s+passed\s+in\s+[\d.]+s",
        r"=+\s*\d+\s+passed",

        # PHPUnit / Pest
        r"OK\s*\(\d+\s+test",
        r"Tests:\s*\d+,\s*Assertions:",
        r"PASS\s+Tests\\",

        # Go
        r"ok\s+\S+\s+[\d.]+s",
        r"^PASS$",

        # Rust (cargo test)
        r"test result: ok\.",

        # RSpec
        r"\d+\s+examples?,\s*0\s+failures?",

        # JUnit / Maven / Gradle
        r"BUILD SUCCESS",
        r"BUILD SUCCESSFUL",
        r"Tests run:\s*\d+.*Failures:\s*0",

        # Dotnet
        r"Passed!\s+-\s+Failed:\s*0",
        r"Test Run Successful",

        # Generic build
        r"Compilation finished successfully",
        r"Build complete",
        r"compiled successfully",
        r"Exit code:?\s*0",
    ]

    evidence_regex = re.compile("|".join(evidence_patterns), re.I | re.M)

    outputs = data.get("tool_outputs", [])
    if isinstance(outputs, list):
        for o in outputs:
            text = o.get("output", "") if isinstance(o, dict) else ""
            if evidence_regex.search(text):
                logger.log("allow")
                sys.exit(0)

    claim_match = re.search(claim_pattern, response, re.I)
    logger.log("feedback",
               reason="Success claim without evidence in tool outputs",
               context={"matched_phrase": claim_match.group(0)[:200] if claim_match else ""})
    print(
        "You claimed tests pass or build succeeds, but no test/build output was found. "
        "Run the actual command before claiming success.",
        file=sys.stderr
    )
    sys.exit(2)

except SystemExit:
    raise  # let sys.exit() through
except Exception:
    sys.exit(0)  # fail-open: unexpected errors must not block the hook
