#!/usr/bin/env python3
"""PreToolUse hook for Write/Edit — scans for hardcoded secrets."""
import sys, json, re

try:
    data = json.load(sys.stdin)
except:
    sys.exit(0)

ti = data.get("tool_input", {})
content = ti.get("content", "") or ti.get("new_string", "") or ""

if not content:
    sys.exit(0)

# AWS access key
if re.search(r"AKIA[0-9A-Z]{16}", content):
    print(json.dumps({"decision": "block", "reason": "AWS access key detected. Use environment variables instead."}))
    sys.exit(0)

# Private keys
if "BEGIN" in content and "PRIVATE KEY" in content:
    print(json.dumps({"decision": "block", "reason": "Private key detected. Never commit private keys to source."}))
    sys.exit(0)

# Common API key patterns
if re.search(r"(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|glpat-[a-zA-Z0-9\-]{20,})", content):
    print(json.dumps({"decision": "block", "reason": "API key/token detected. Use environment variables instead."}))
    sys.exit(0)

# Hardcoded passwords in assignments
pattern = re.compile(r'(password|secret|api_key|apikey|auth_token)\s*[:=]\s*["\'][^"\']{8,}["\']', re.I)
skip = re.compile(r'(env\(|process\.env|os\.environ|config\(|ENV\[|placeholder|changeme|xxxxxxx)', re.I)
for match in pattern.finditer(content):
    if not skip.search(match.group(0)):
        print(json.dumps({"decision": "block", "reason": "Possible hardcoded credential detected. Use environment variables or a secrets manager."}))
        sys.exit(0)

sys.exit(0)
