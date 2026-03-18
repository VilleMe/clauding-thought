#!/usr/bin/env python3
"""Stop hook — detects when Claude rationalizes away issues it should address."""
import sys, json, re

try:
    data = json.load(sys.stdin)
except:
    sys.exit(0)

response = data.get("response", "")
if not response:
    sys.exit(0)

patterns = [
    r"pre-existing\s+(issue|bug|problem)",
    r"out\s+of\s+scope",
    r"separate\s+issue",
    r"not\s+related\s+to\s+(our|the)\s+change",
    r"we\s+don.t\s+need\s+to\s+fix",
    r"already\s+existed\s+before",
    r"beyond\s+the\s+scope",
    r"not\s+our\s+responsibility",
    r"outside\s+the\s+scope",
]

if re.search("|".join(patterns), response, re.I):
    print("If you identified an issue during this task, address it or document it as tech debt. Don't dismiss issues without explicit acknowledgment.", file=sys.stderr)
    sys.exit(2)

sys.exit(0)
