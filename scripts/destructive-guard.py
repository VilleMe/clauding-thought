#!/usr/bin/env python3
"""PreToolUse hook for Bash: denies destructive commands.

Output contract (Claude Code hooks reference): a PreToolUse hook denies a tool
call by printing JSON with hookSpecificOutput.permissionDecision = "deny".
Exit 0 with empty stdout allows. Any unexpected error fails open.

Claude Code's own permission rules are text matches that `/bin/rm` or
`bash -c` can slip past, and its sandbox does not run on native Windows, so
this hook is the real-time line against the handful of commands that destroy
work or data. It denies; the model is told to ask the user if the command
was intentional.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CHECKS = [
    # rm with force+recursive in any flag order, split or combined, on root/home/cwd
    (r"rm\s+.*-[^\s]*r[^\s]*f[^\s]*\s+[/~.]/?(\s|$)", "rm -rf on root/home/cwd is destructive."),
    (r"rm\s+.*-[^\s]*f[^\s]*r[^\s]*\s+[/~.]/?(\s|$)", "rm -fr on root/home/cwd is destructive."),
    (r"rm\s+(-\w+\s+)*--recursive\s+.*--force", "rm --recursive --force is destructive."),
    (r"rm\s+(-\w+\s+)*--force\s+.*--recursive", "rm --force --recursive is destructive."),
    # rm -rf with a variable path that could resolve anywhere
    (r"rm\s+.*-[^\s]*r[^\s]*f[^\s]*\s+\$", "rm -rf with a variable path: verify the variable is safe."),

    # git force push to protected branches, flag before or after the branch name
    (r"git\s+push\s+.*--force(?!-with-lease).*(main|master|release|production)",
     "Force push to a protected branch can destroy shared history."),
    (r"git\s+push\s+.*(main|master|release|production).*--force(?!-with-lease)",
     "Force push to a protected branch can destroy shared history."),
    (r"git\s+push\s+.*\s-f\s.*(main|master|release|production)",
     "Force push (-f) to a protected branch can destroy shared history."),
    (r"git\s+push\s+.*(main|master|release|production).*\s-f(\s|$)",
     "Force push (-f) to a protected branch can destroy shared history."),
    # any force push without --force-with-lease
    (r"git\s+push\s+.*--force(?!-with-lease)",
     "Force push without --force-with-lease is dangerous. Use --force-with-lease instead."),

    # discarding work
    (r"git\s+reset\s+--hard", "git reset --hard discards uncommitted changes permanently."),
    (r"git\s+clean\s+-[^\s]*f", "git clean -f permanently deletes untracked files."),
    (r"git\s+checkout\s+--\s+\.", "git checkout -- . discards all uncommitted changes."),
    (r"git\s+restore\s+(--worktree\s+)?\.(\s|$)", "git restore . discards all uncommitted changes."),

    # destructive SQL
    (r"\b(DROP\s+TABLE|DROP\s+DATABASE|DROP\s+SCHEMA|TRUNCATE\s+TABLE)\b", "Destructive SQL operation detected."),
    (r"\bDELETE\s+FROM\s+\w+\s*;?\s*$", "DELETE without a WHERE clause removes all rows."),

    # dangerous permissions
    (r"chmod\s+(-R\s+)?777", "chmod 777 makes files world-writable. Use more restrictive permissions."),

    # disk/filesystem destruction
    (r"\bdd\s+.*of=/dev/", "dd to a device can wipe the disk."),
    (r"\bmkfs\.", "mkfs formats a filesystem; all data will be lost."),

    # eval with external input
    (r"\beval\s+[\"'].*rm\s", "eval with rm detected: possible command injection."),
    (r"\beval\s+\$", "eval with variable expansion is a command injection risk."),

    # find -delete on broad paths
    (r"find\s+[/~.]\s+.*-delete", "find with -delete on a broad path is dangerous."),
]

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    from hook_telemetry import TelemetryLogger

    logger = TelemetryLogger("destructive-guard", "PreToolUse", "Bash", hook_input=data)

    cmd = (data.get("tool_input") or {}).get("command", "")
    if not cmd:
        logger.log("allow")
        sys.exit(0)

    for pattern, msg in CHECKS:
        if re.search(pattern, cmd, re.I):
            reason = f"{msg} If intentional, ask the user to confirm."
            logger.log("block", reason=reason, pattern=pattern,
                       context={"command_preview": cmd[:200]})
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }))
            sys.exit(0)

    logger.log("allow")
    sys.exit(0)

except SystemExit:
    raise
except Exception:
    sys.exit(0)  # fail-open: unexpected errors must not block the tool
