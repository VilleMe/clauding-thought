#!/usr/bin/env python3
"""PreToolUse hook for Bash — blocks destructive commands."""
import sys, json, re

try:
    data = json.load(sys.stdin)
except:
    sys.exit(0)

cmd = data.get("tool_input", {}).get("command", "")
if not cmd:
    sys.exit(0)

checks = [
    (r"rm\s+-(rf|fr)\s+[/~.](\s|$)", "rm -rf on root/home/cwd is destructive. Use a specific path or trash."),
    (r"git\s+push\s+.*--force.*(main|master)", "Force push to main/master can destroy shared history."),
    (r"git\s+reset\s+--hard", "git reset --hard discards uncommitted changes permanently."),
    (r"(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE)", "Destructive SQL operation detected."),
    (r"chmod\s+777", "chmod 777 makes files world-writable. Use more restrictive permissions."),
]

for pattern, msg in checks:
    if re.search(pattern, cmd, re.I):
        print(json.dumps({"decision": "block", "reason": f"{msg} If intentional, ask the user to confirm."}))
        sys.exit(0)

sys.exit(0)
