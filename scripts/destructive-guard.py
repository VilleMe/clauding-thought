#!/usr/bin/env python3
"""PreToolUse hook for Bash — blocks destructive commands."""
import sys, json, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    logger = TelemetryLogger("destructive-guard", "PreToolUse", "Bash")

    cmd = data.get("tool_input", {}).get("command", "")
    if not cmd:
        logger.log("allow")
        sys.exit(0)

    checks = [
        # rm with force+recursive in any flag order, split or combined
        (r"rm\s+.*-[^\s]*r[^\s]*f[^\s]*\s+[/~.]/?(\s|$)", "rm -rf on root/home/cwd is destructive."),
        (r"rm\s+.*-[^\s]*f[^\s]*r[^\s]*\s+[/~.]/?(\s|$)", "rm -fr on root/home/cwd is destructive."),
        (r"rm\s+(-\w+\s+)*--recursive\s+.*--force", "rm --recursive --force is destructive."),
        (r"rm\s+(-\w+\s+)*--force\s+.*--recursive", "rm --force --recursive is destructive."),
        # rm -rf with variable paths that could resolve to dangerous locations
        (r"rm\s+.*-[^\s]*r[^\s]*f[^\s]*\s+\$", "rm -rf with variable path — verify the variable is safe."),

        # git force push to protected branches — flag before or after branch name (exclude --force-with-lease)
        (r"git\s+push\s+.*--force(?!-with-lease).*(main|master|release|production)", "Force push to protected branch can destroy shared history."),
        (r"git\s+push\s+.*(main|master|release|production).*--force(?!-with-lease)", "Force push to protected branch can destroy shared history."),
        (r"git\s+push\s+.*\s-f\s.*(main|master|release|production)", "Force push (-f) to protected branch can destroy shared history."),
        (r"git\s+push\s+.*(main|master|release|production).*\s-f(\s|$)", "Force push (-f) to protected branch can destroy shared history."),
        # Catch-all: any force push without --force-with-lease
        (r"git\s+push\s+.*--force(?!-with-lease)", "Force push without --force-with-lease is dangerous. Use --force-with-lease instead."),

        # git reset --hard
        (r"git\s+reset\s+--hard", "git reset --hard discards uncommitted changes permanently."),
        (r"git\s+clean\s+-[^\s]*f", "git clean -f permanently deletes untracked files."),

        # destructive SQL
        (r"(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE)", "Destructive SQL operation detected."),
        (r"DELETE\s+FROM\s+\w+\s*;?\s*$", "DELETE without WHERE clause will remove all rows."),

        # dangerous permissions
        (r"chmod\s+777", "chmod 777 makes files world-writable. Use more restrictive permissions."),
        (r"chmod\s+-R\s+777", "Recursive chmod 777 is especially dangerous."),

        # disk/filesystem destruction
        (r"dd\s+.*of=/dev/", "dd to a device can wipe the disk."),
        (r"mkfs\.", "mkfs formats a filesystem — all data will be lost."),

        # eval/exec with external input (command injection risk)
        (r"\beval\s+[\"'].*rm\s", "eval with rm detected — possible command injection."),
        (r"\beval\s+\$", "eval with variable expansion is a command injection risk."),

        # find with -delete on broad paths
        (r"find\s+[/~.]\s+.*-delete", "find with -delete on a broad path is dangerous."),
    ]

    for pattern, msg in checks:
        if re.search(pattern, cmd, re.I):
            reason = f"{msg} If intentional, ask the user to confirm."
            logger.log("block", reason=reason, pattern=pattern,
                       context={"tool": "Bash", "command_preview": cmd[:200]})
            print(json.dumps({"decision": "block", "reason": reason}))
            sys.exit(0)

    logger.log("allow")
    sys.exit(0)

except SystemExit:
    raise  # let sys.exit() through
except Exception:
    sys.exit(0)  # fail-open: unexpected errors must not block the tool
