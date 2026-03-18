#!/usr/bin/env bash
# anti-rationalization.sh — Stop hook
# Detects when Claude rationalizes away issues it should address.

INPUT=$(cat)

# Use python3 for both JSON parsing and regex (cross-platform)
FOUND=$(echo "$INPUT" | python3 -c "
import sys, json, re
try:
    d = json.load(sys.stdin)
    response = d.get('response', '')
    if not response:
        sys.exit(0)
    patterns = [
        r'pre-existing\s+(issue|bug|problem)',
        r'out\s+of\s+scope',
        r'separate\s+issue',
        r'not\s+related\s+to\s+(our|the)\s+change',
        r'we\s+don.t\s+need\s+to\s+fix',
        r'already\s+existed\s+before',
        r'beyond\s+the\s+scope',
        r'not\s+our\s+responsibility',
        r'outside\s+the\s+scope',
    ]
    combined = '|'.join(patterns)
    if re.search(combined, response, re.I):
        print('found')
except: pass
" 2>/dev/null)

if [ "$FOUND" = "found" ]; then
  echo "If you identified an issue during this task, address it or document it as tech debt in the task document. Don't dismiss issues without explicit acknowledgment." >&2
  exit 2
fi

exit 0
