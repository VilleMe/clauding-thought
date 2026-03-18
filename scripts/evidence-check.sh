#!/usr/bin/env bash
# evidence-check.sh — Stop hook
# Verifies that claims like "tests pass" are backed by actual command output.

INPUT=$(cat)

# Use python3 for everything (cross-platform, no jq/grep -P dependency)
RESULT=$(echo "$INPUT" | python3 -c "
import sys, json, re
try:
    d = json.load(sys.stdin)
    response = d.get('response', '')
    if not response:
        sys.exit(0)

    # Check for success claims
    claim_patterns = r'(all\s+tests?\s+pass|tests?\s+(are\s+)?passing|build\s+succeed|build\s+pass|no\s+(test\s+)?errors|everything\s+(works|passes|compiles))'
    if not re.search(claim_patterns, response, re.I):
        sys.exit(0)

    # Check for evidence in tool outputs
    evidence_pattern = r'(PASS|OK|success|passed|Tests:.*\d|BUILD SUCCESS|\d+\s+passing)'
    outputs = d.get('tool_outputs', [])
    for o in (outputs if isinstance(outputs, list) else []):
        text = o.get('output', '') if isinstance(o, dict) else ''
        if re.search(evidence_pattern, text, re.I):
            sys.exit(0)

    print('no_evidence')
except: pass
" 2>/dev/null)

if [ "$RESULT" = "no_evidence" ]; then
  echo "You claimed tests pass or build succeeds, but no test/build output was found. Run the actual command before claiming success." >&2
  exit 2
fi

exit 0
