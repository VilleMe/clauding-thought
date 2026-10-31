#!/usr/bin/env python3
"""PreToolUse hook for Write, Edit, MultiEdit, NotebookEdit: denies writes that
contain hardcoded secrets.

Detects provider tokens by shape, private keys of any kind, connection
strings with real embedded passwords, and credential assignments in the
forms people actually write (JSON keys, YAML, .env, backticks). Templated
values, environment lookups, placeholders and obvious test values pass.

Output contract: deny with stdout JSON hookSpecificOutput.permissionDecision
= "deny", exit 0. Empty stdout, exit 0 allows. An internal error is reported
on stderr with exit 1 (visible, non-blocking).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TOKEN_PATTERNS = [
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"(?<![\w-])sk-ant-[A-Za-z0-9_-]{20,}", "Anthropic API key"),
    (r"(?<![\w-])sk-(?:proj|svcacct|live|test)-[A-Za-z0-9_-]{20,}", "OpenAI-style API key"),
    (r"(?<![\w-])sk-[A-Za-z0-9]{40,}(?![\w-])", "OpenAI-style API key"),
    (r"\bgh[pousr]_[A-Za-z0-9]{36}\b", "GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{22,}", "GitHub fine-grained token"),
    (r"\bglpat-[A-Za-z0-9\-]{20,}", "GitLab token"),
    (r"\bxox[bpsa]-[A-Za-z0-9\-]{10,}", "Slack token"),
    (r"hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]{8,}", "Slack webhook URL"),
    (r"\b[sr]k_live_[A-Za-z0-9]{20,}", "Stripe live key"),
    (r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}", "SendGrid API key"),
    (r"\bAIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"\bya29\.[0-9A-Za-z_\-]{20,}", "Google OAuth token"),
    (r"\bnpm_[A-Za-z0-9]{36}\b", "npm token"),
    (r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JSON Web Token"),
    (r"AZURE[A-Z_]*[=:]\s*['\"][A-Za-z0-9+/=]{40,}['\"]", "Azure credential"),
]
PRIVATE_KEY_RE = re.compile(r"-----BEGIN\s+(?:[A-Z]+\s+)*PRIVATE KEY(?: BLOCK)?-----")

# key: value in JSON / YAML / .env / code, value optionally quoted or backticked
ASSIGN_RE = re.compile(
    r"""(?im)["']?(?P<key>password|passwd|pwd|secret|api[_-]?key|apikey|auth[_-]?token|access[_-]?token|
        private[_-]?key|client[_-]?secret|signing[_-]?key|secret[_-]?access[_-]?key|
        [a-z][a-z0-9_]*_(?:password|passwd|secret|token|api_key|apikey))["']?\s*[:=]\s*["'`]?(?P<val>[^\s"'`,;]{8,})""",
    re.VERBOSE,
)
# Anything that says "this is not a literal secret": lookups, templates, placeholders, test values
SKIP_RE = re.compile(
    r"""env\(|process\.env|os\.environ|os\.getenv|getenv\(|config\(|ENV\[|settings\.|secrets\.|vault|
        \$\{|\$[A-Za-z_]|\{\{|%\(|<[-\w ]+>|\[REDACTED\]|\*{3,}|\.{3}|xxx|placeholder|changeme|change[-_]me|
        example|your[-_]|dummy|fake|mock|sample|\btest|fixture|redacted|hunter2|password123|p@ssw0rd""",
    re.I | re.VERBOSE,
)
CONN_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp|mssql)://(?P<user>[^:/\s@]+):(?P<pw>[^@\s]+)@(?P<host>[^/\s:?]+)"
)
DEV_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "db", "database", "postgres", "mysql", "mariadb", "redis",
             "mongo", "mongodb", "host.docker.internal", "rabbitmq", "broker"}
DEV_PASSWORDS = {"password", "postgres", "mysql", "root", "secret", "example", "test", "dev", "admin",
                 "changeme", "pass", "redis", "guest", "mongo"}
SQLSERVER_RE = re.compile(r"(?i)Server=[^;]+;.*Password=(?P<pw>[^;\s]{8,})")


def read_hook_input():
    return json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))


def content_of(tool_input):
    pieces = [tool_input.get("content"), tool_input.get("new_string"), tool_input.get("new_source")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            pieces.append(edit.get("new_string"))
    return "\n".join(p for p in pieces if isinstance(p, str) and p)


def line_of(text, pos):
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start: end if end != -1 else len(text)]


def judge(content):
    """(reason, pattern_name) for the first secret found, else (None, None)."""
    for pattern, name in TOKEN_PATTERNS:
        if re.search(pattern, content):
            return f"{name} detected. Use environment variables or a secrets manager.", name
    if PRIVATE_KEY_RE.search(content):
        return "Private key detected. Never commit private keys to source.", "private key"
    for m in CONN_RE.finditer(content):
        pw, host, user = m.group("pw"), m.group("host").lower(), m.group("user")
        if SKIP_RE.search(pw) or pw.startswith("$"):
            continue
        if host in DEV_HOSTS and (pw.lower() in DEV_PASSWORDS or pw == user):
            continue
        return "Connection string with an embedded password detected. Use environment variables.", "connection string"
    for m in SQLSERVER_RE.finditer(content):
        if not SKIP_RE.search(m.group("pw")) and not m.group("pw").startswith("$"):
            return "SQL Server connection string with a password detected.", "sqlserver connection string"
    for m in ASSIGN_RE.finditer(content):
        val = m.group("val")
        line = line_of(content, m.start())
        if SKIP_RE.search(val) or SKIP_RE.search(line) or val.startswith("$"):
            continue
        if re.match(r"^[A-Za-z_][\w.]*\(", val) or val.lower() == m.group("key").lower():
            continue  # a function call or the key name itself
        if len(set(val)) < 4:
            continue  # "********", "aaaaaaaa"
        return "Possible hardcoded credential detected. Use environment variables or a secrets manager.", "hardcoded credential"
    return None, None


try:
    data = read_hook_input()
except Exception:
    sys.exit(0)

try:
    from hook_telemetry import TelemetryLogger
except Exception:
    class TelemetryLogger:  # no-op stand-in: the filter still judges
        def __init__(self, *a, **k): pass
        def log(self, *a, **k): pass

try:
    tool = data.get("tool_name", "Write")
    ti = data.get("tool_input") or {}
    logger = TelemetryLogger("secret-filter", "PreToolUse", tool, hook_input=data)
    content = content_of(ti) if isinstance(ti, dict) else ""
    if not content:
        logger.log("allow")
        sys.exit(0)

    reason, name = judge(content)
    if reason:
        logger.log("block", reason=reason, pattern=name)
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
    print(f"secret-filter: internal error ({type(e).__name__}); write allowed by default", file=sys.stderr)
    sys.exit(1)
