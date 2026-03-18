#!/usr/bin/env bash
# secret-filter.sh — PreToolUse hook for Write/Edit
# Scans proposed file content for hardcoded secrets and credentials.

INPUT=$(cat)

# Extract content using python3 (cross-platform, no jq dependency)
CONTENT=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    print(ti.get('content', '') or ti.get('new_string', '') or '')
except: pass
" 2>/dev/null)

if [ -z "$CONTENT" ]; then
  exit 0
fi

# AWS access key
if echo "$CONTENT" | grep -q 'AKIA[0-9A-Z]'; then
  echo '{"decision":"block","reason":"AWS access key detected. Use environment variables instead."}'
  exit 0
fi

# Private keys
if echo "$CONTENT" | grep -q 'BEGIN.*PRIVATE KEY'; then
  echo '{"decision":"block","reason":"Private key detected. Never commit private keys to source."}'
  exit 0
fi

# Common API key patterns
if echo "$CONTENT" | grep -qE '(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|glpat-[a-zA-Z0-9-]{20,})'; then
  echo '{"decision":"block","reason":"API key/token detected. Use environment variables instead."}'
  exit 0
fi

# Hardcoded passwords — use python for the complex regex
BLOCKED=$(echo "$CONTENT" | python3 -c "
import sys, re
text = sys.stdin.read()
pattern = re.compile(r'(password|secret|api_key|apikey|auth_token)\s*[:=]\s*[\"'"'"'][^\"'"'"']{8,}[\"'"'"']', re.I)
skip = re.compile(r'(env\(|process\.env|os\.environ|config\(|ENV\[|placeholder|changeme|xxxxxxx)', re.I)
for match in pattern.finditer(text):
    if not skip.search(match.group(0)):
        print('yes')
        break
" 2>/dev/null)

if [ "$BLOCKED" = "yes" ]; then
  echo '{"decision":"block","reason":"Possible hardcoded credential detected. Use environment variables or a secrets manager."}'
  exit 0
fi

exit 0
