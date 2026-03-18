#!/usr/bin/env python3
"""Stop hook — verifies that 'tests pass' claims are backed by actual output."""
import sys, json, re

try:
    data = json.load(sys.stdin)
except:
    sys.exit(0)

response = data.get("response", "")
if not response:
    sys.exit(0)

# Check for success claims
claim_pattern = r"(all\s+tests?\s+pass|tests?\s+(are\s+)?passing|build\s+succeed|build\s+pass|no\s+(test\s+)?errors|everything\s+(works|passes|compiles))"
if not re.search(claim_pattern, response, re.I):
    sys.exit(0)

# Check for evidence in tool outputs
evidence_pattern = r"(PASS|OK|success|passed|Tests:.*\d|BUILD SUCCESS|\d+\s+passing)"
outputs = data.get("tool_outputs", [])
if isinstance(outputs, list):
    for o in outputs:
        text = o.get("output", "") if isinstance(o, dict) else ""
        if re.search(evidence_pattern, text, re.I):
            sys.exit(0)

print("You claimed tests pass or build succeeds, but no test/build output was found. Run the actual command before claiming success.", file=sys.stderr)
sys.exit(2)
