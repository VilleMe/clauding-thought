#!/usr/bin/env bash
# destructive-guard.sh — PreToolUse hook for Bash
# Blocks destructive commands that are hard to reverse.

INPUT=$(cat)

# Extract command using python3 (cross-platform, no jq dependency)
CMD=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except: pass
" 2>/dev/null)

if [ -z "$CMD" ]; then
  exit 0
fi

# Use python for all pattern matching (avoids grep -P issues on Windows)
BLOCKED=$(echo "$CMD" | python3 -c "
import sys, re
cmd = sys.stdin.read().strip()
checks = [
    (r'rm\s+-(rf|fr)\s+[/~.](\s|$)', 'rm -rf on root/home/cwd is destructive. Use a specific path or trash.'),
    (r'git\s+push\s+.*--force.*(main|master)', 'Force push to main/master can destroy shared history.'),
    (r'git\s+reset\s+--hard', 'git reset --hard discards uncommitted changes permanently.'),
    (r'(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE)', 'Destructive SQL operation detected.'),
    (r'chmod\s+777', 'chmod 777 makes files world-writable. Use more restrictive permissions.'),
]
for pattern, msg in checks:
    if re.search(pattern, cmd, re.I):
        print(msg)
        break
" 2>/dev/null)

if [ -n "$BLOCKED" ]; then
  echo "{\"decision\":\"block\",\"reason\":\"$BLOCKED If intentional, ask the user to confirm.\"}"
  exit 0
fi

exit 0
