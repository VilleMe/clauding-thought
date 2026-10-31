#!/usr/bin/env python3
"""PreToolUse hook for Bash: denies destructive commands.

The command is split on `;`, `&&`, `||`, `|` and newlines, each piece is
tokenised like a shell would, and the decision is made on argv, not on a
regex over the whole string. That is what lets `rm -r -f .`, `rm -rf *`,
`'rm' -rf .` and `cd x && rm -rf .` be caught while `grep 'DROP TABLE'`,
`find . -name '*.pyc' -delete`, `git clean -fdn` and `terraform plan
-var-file $VARS` pass.

Output contract: deny with stdout JSON hookSpecificOutput.permissionDecision
= "deny", exit 0. Empty stdout, exit 0 allows. An internal error is reported
on stderr with exit 1 (visible, non-blocking) so a broken guard is never
silent. Claude Code's own permission rules are text matches and its sandbox
does not run on native Windows, so this is the real-time line against the
handful of commands that destroy work or data.
"""
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SPLIT_RE = re.compile(r"\s*(?:;|&&|\|\||\||\r?\n)\s*")
PREFIX_CMDS = {"sudo", "doas", "env", "nice", "time", "command", "exec", "nohup", "busybox", "xargs"}
DB_CLIENTS = {"psql", "mysql", "mysqlsh", "sqlite3", "sqlcmd", "mongosh", "mongo", "redis-cli",
              "clickhouse-client", "cqlsh", "bq"}
PROTECTED_BRANCHES = ("main", "master", "release", "production", "prod", "develop")
DANGEROUS_RM_TARGETS = {".", "./", "..", "../", "/", "~", "~/", "*", "./*", "/*", "~/*", "/.", "~/."}
NARROWING_FIND = {"-name", "-iname", "-path", "-ipath", "-regex", "-iregex", "-type", "-mtime", "-mmin",
                  "-newer", "-maxdepth", "-mindepth", "-size", "-user", "-empty", "-samefile", "-wholename"}
SAFE_DD_TARGETS = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/zero", "/dev/tty")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


def read_hook_input():
    return json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))


def base(token):
    return os.path.basename(token.strip("\"'")).lower()


def to_argv(piece):
    try:
        return shlex.split(piece, posix=True)
    except ValueError:
        return piece.split()


def shift_prefixes(argv):
    """Drop leading env assignments and wrapper commands; say whether xargs fed it."""
    piped = False
    while argv:
        if ASSIGN_RE.match(argv[0]):
            argv = argv[1:]
            continue
        b = base(argv[0])
        if b in PREFIX_CMDS:
            piped = piped or b == "xargs"
            argv = argv[1:]
            # skip the wrapper's own options (sudo -u user, env -i, xargs -0 ...)
            while argv and argv[0].startswith("-") and b in ("sudo", "env", "xargs", "nice"):
                argv = argv[2:] if argv[0] in ("-u", "-g", "-n", "-I", "-L", "-P") else argv[1:]
            continue
        break
    return argv, piped


def check_rm(argv, piped):
    if base(argv[0]) != "rm":
        return None
    args = [a for a in argv[1:] if a != "--"]
    flags = [a for a in args if a.startswith("-")]
    targets = [a for a in args if not a.startswith("-")]
    recursive = any(a == "--recursive" or (not a.startswith("--") and re.search(r"[rR]", a)) for a in flags)
    force = any(a == "--force" or (not a.startswith("--") and "f" in a) for a in flags)
    if not (recursive and force):
        return None
    if piped and not targets:
        return "rm -rf fed by a pipe deletes whatever the pipe lists."
    for t in targets:
        n = t.replace("\\", "/")
        if n in DANGEROUS_RM_TARGETS or n.startswith("$") or "${" in n or n.startswith("~/*"):
            return f"rm -rf on `{t}` is destructive."
    return None


def check_git(argv):
    if base(argv[0]) != "git":
        return None
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
    sub = argv[i] if i < len(argv) else ""
    rest = argv[i + 1:]
    short_flags = [a for a in rest if a.startswith("-") and not a.startswith("--")]
    if sub == "push":
        lease = any(a.startswith("--force-with-lease") or a.startswith("--force-if-includes") for a in rest)
        force = "--force" in rest or any("f" in a[1:] for a in short_flags) or \
            any(a.startswith("+") and len(a) > 1 for a in rest)
        if force and not lease:
            if any(p in a for a in rest for p in PROTECTED_BRANCHES):
                return "Force push to a protected branch can destroy shared history."
            return "Force push without --force-with-lease is dangerous. Use --force-with-lease instead."
    if sub == "reset" and "--hard" in rest:
        return "git reset --hard discards uncommitted changes permanently."
    if sub == "clean":
        dry = "--dry-run" in rest or any("n" in a[1:] for a in short_flags)
        force = "--force" in rest or any("f" in a[1:] for a in short_flags)
        if force and not dry:
            return "git clean -f permanently deletes untracked files."
    if sub == "checkout" and "." in rest and not any(a.startswith("-b") for a in rest):
        return "git checkout . discards all uncommitted changes."
    if sub == "restore" and "." in rest and "--staged" not in rest and "-S" not in rest:
        return "git restore . discards all uncommitted changes."
    if sub == "branch" and ("-D" in rest or ("--delete" in rest and "--force" in rest)) and \
            any(a in PROTECTED_BRANCHES for a in rest):
        return "Deleting a protected branch can destroy shared history."
    if sub == "stash" and rest[:1] == ["clear"]:
        return "git stash clear permanently deletes every stash."
    return None


def check_sql(piece, argv):
    text = piece if base(argv[0]) in DB_CLIENTS else QUOTED_RE.sub(" ", piece)
    if re.search(r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE(\s+TABLE)?)\b", text, re.I):
        return "Destructive SQL operation detected."
    if re.search(r"\bDELETE\s+FROM\s+[\w.\"`]+\s*;?\s*$", text.strip(), re.I) and \
            not re.search(r"\bWHERE\b", text, re.I):
        return "DELETE without a WHERE clause removes all rows."
    return None


def check_misc(argv):
    b = base(argv[0])
    rest = argv[1:]
    if b == "chmod" and any(re.fullmatch(r"0?777", a) or re.search(r"(?:^|,)[ugoa]*\+?rwx$", a) and "a" in a
                            for a in rest):
        return "chmod 777 / a+rwx makes files world-writable. Use more restrictive permissions."
    if b == "dd" and any(a.startswith("of=/dev/") and not a.startswith(SAFE_DD_TARGETS) and a[3:] not in SAFE_DD_TARGETS
                         for a in rest):
        return "dd to a device can wipe the disk."
    if b.startswith("mkfs"):
        return "mkfs formats a filesystem; all data will be lost."
    if b == "eval" and re.search(r"\b(rm|mkfs|dd)\b|curl|wget", " ".join(rest)):
        return "eval over rm/mkfs/dd/curl/wget is a command-injection risk."
    if b == "find":
        has_delete = "-delete" in rest or ("-exec" in rest and any(base(a) == "rm" for a in rest))
        if has_delete:
            paths = []
            for a in rest:
                if a.startswith("-") or a in ("!", "(", ")"):
                    break
                paths.append(a)
            narrowing = any(a in NARROWING_FIND for a in rest)
            broad = not paths or any(p.rstrip("/") in ("", ".", "..", "~") or p == "/" for p in paths)
            if broad and not narrowing:
                return "find -delete over a whole tree with no name or type filter is dangerous."
    return None


def judge(cmd):
    """(message, check_id) for the first destructive piece, else (None, None)."""
    for piece in SPLIT_RE.split(cmd):
        if not piece or not piece.strip():
            continue
        argv, piped = shift_prefixes(to_argv(piece))
        if not argv:
            continue
        for check_id, msg in (
            ("rm", check_rm(argv, piped)),
            ("git", check_git(argv)),
            ("sql", check_sql(piece, argv)),
            ("misc", check_misc(argv)),
        ):
            if msg:
                return msg, check_id
    return None, None


try:
    data = read_hook_input()
except Exception:
    sys.exit(0)

try:
    from hook_telemetry import TelemetryLogger, mask
except Exception:
    class TelemetryLogger:  # no-op stand-in: the guard still judges
        def __init__(self, *a, **k): pass
        def log(self, *a, **k): pass

    def mask(text, limit=160):
        return re.sub(r"\S{16,}", "<token>", (text or "")[:limit])

try:
    logger = TelemetryLogger("destructive-guard", "PreToolUse", "Bash", hook_input=data)
    cmd = (data.get("tool_input") or {}).get("command", "")
    if not isinstance(cmd, str) or not cmd.strip():
        logger.log("allow")
        sys.exit(0)

    msg, check_id = judge(cmd)
    if msg:
        reason = f"{msg} If intentional, ask the user to confirm."
        logger.log("block", reason=msg, pattern=check_id, context={"command_preview": mask(cmd)})
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
except Exception as e:
    print(f"destructive-guard: internal error ({type(e).__name__}); command allowed by default", file=sys.stderr)
    sys.exit(1)
