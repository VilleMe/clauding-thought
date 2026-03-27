#!/usr/bin/env python3
"""PreToolUse hook for Write/Edit — scans for hardcoded secrets."""
import sys, json, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    logger = TelemetryLogger("secret-filter", "PreToolUse", data.get("tool_name", "Write"))

    ti = data.get("tool_input", {})
    content = ti.get("content", "") or ti.get("new_string", "") or ""

    if not content:
        logger.log("allow")
        sys.exit(0)

    def block(reason, pattern_name=""):
        logger.log("block", reason=reason, pattern=pattern_name,
                   context={"tool": data.get("tool_name", ""), "file_path": ti.get("file_path", "")})
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # --- AWS ---
    if re.search(r"AKIA[0-9A-Z]{16}", content):
        block("AWS access key detected. Use environment variables instead.", "AKIA[0-9A-Z]{16}")

    # --- Private keys (multi-line aware) ---
    if re.search(r"-----BEGIN\s+(RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", content):
        block("Private key detected. Never commit private keys to source.", "PRIVATE KEY")

    # --- Cloud provider tokens ---
    token_patterns = [
        (r"sk-[a-zA-Z0-9_-]{20,}", "OpenAI API key"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
        (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth token"),
        (r"ghs_[a-zA-Z0-9]{36}", "GitHub server token"),
        (r"ghu_[a-zA-Z0-9]{36}", "GitHub user token"),
        (r"glpat-[a-zA-Z0-9\-]{20,}", "GitLab personal access token"),
        (r"xox[bpsa]-[a-zA-Z0-9\-]{10,}", "Slack token"),
        (r"sk_live_[a-zA-Z0-9]{20,}", "Stripe live secret key"),
        (r"rk_live_[a-zA-Z0-9]{20,}", "Stripe live restricted key"),
        (r"SG\.[a-zA-Z0-9_\-]{22}\.[a-zA-Z0-9_\-]{43}", "SendGrid API key"),
        (r"key-[a-zA-Z0-9]{32}", "Mailgun API key"),
        (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
        (r"ya29\.[0-9A-Za-z_\-]+", "Google OAuth access token"),
        (r"AZURE[A-Z_]*[=:]\s*['\"][a-zA-Z0-9+/=]{40,}['\"]", "Azure credential"),
    ]

    for pattern, name in token_patterns:
        if re.search(pattern, content):
            block(f"{name} detected. Use environment variables or a secrets manager.", pattern)

    # --- Connection strings with embedded credentials ---
    conn_patterns = [
        (r"(postgres|mysql|mongodb|redis|amqp)://[^:]+:[^@]+@", "Database/service connection string with embedded password"),
        (r"DefaultEndpointsProtocol=.*AccountKey=[a-zA-Z0-9+/=]{40,}", "Azure storage connection string"),
        (r"Server=.*Password=[^;]{8,}", "SQL Server connection string with password"),
    ]

    for pattern, name in conn_patterns:
        if re.search(pattern, content, re.I):
            block(f"{name} detected. Use environment variables for credentials.", pattern)

    # --- Hardcoded passwords/secrets in assignments ---
    assign_pattern = re.compile(
        r'(password|secret|api_key|apikey|auth_token|access_token|private_key|client_secret|signing_key)'
        r'\s*[:=]\s*["\'][^"\']{8,}["\']',
        re.I
    )
    skip_pattern = re.compile(
        r'(env\(|process\.env|os\.environ|os\.getenv|config\(|ENV\[|Settings\.'
        r'|placeholder|changeme|xxxxxxx|example|your[-_]|<[-\w]+>|\{\{)',
        re.I
    )
    for match in assign_pattern.finditer(content):
        if not skip_pattern.search(match.group(0)):
            block("Possible hardcoded credential detected. Use environment variables or a secrets manager.", "hardcoded-credential-assign")

    logger.log("allow")
    sys.exit(0)

except SystemExit:
    raise  # let sys.exit() through
except Exception:
    sys.exit(0)  # fail-open: unexpected errors must not block the tool
