## A07:2021 — Identification and Authentication Failures
<!-- severity: error -->

Authentication and session management flaws allow attackers to compromise passwords, keys, or session tokens, or to exploit implementation flaws to assume other users' identities.

Reference: [OWASP A07:2021](https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/), CWE-287, CWE-384, CWE-613

### Missing Authentication on Sensitive Endpoints

**Rule:** Every endpoint that accesses or modifies user data, administrative functions, or internal resources must require authentication. Apply auth middleware at the route group or controller level, not per-action.

**Detect:** Route definitions or controller classes serving data-mutating or data-reading endpoints without auth middleware. Public methods in controllers that are otherwise authenticated (possible oversight).

### Weak Password Storage (CWE-916)

**Rule:** Always use a modern adaptive hashing algorithm for password storage: bcrypt, scrypt, or Argon2id. Never use MD5, SHA1, SHA256, or any non-salted hash for passwords.

**Detect:** Password hashing calls using `md5()`, `sha1()`, `sha256()`, `hashlib.sha*`, or `MessageDigest.getInstance("SHA")` in contexts related to user passwords or credentials.

**Good:**
```python
# Python
from passlib.hash import argon2
hashed = argon2.hash(password)
```

**Bad:**
```python
import hashlib
hashed = hashlib.md5(password.encode()).hexdigest()
```

### Session Fixation (CWE-384)

**Rule:** Regenerate the session ID after successful authentication. Invalidate old session tokens on login, logout, and privilege escalation.

**Detect:** Login handlers that authenticate the user without calling session regeneration (`session.regenerate()`, `session()->regenerate()`, `request.session.cycle_id`).

### Credential Exposure in Logs

**Rule:** Never log passwords, tokens, API keys, or session identifiers. Mask or redact sensitive fields before logging.

**Detect:** Log statements (`logger.info`, `console.log`, `Log::info`, `syslog`) that include variables named `password`, `token`, `secret`, `api_key`, `session_id`, or `authorization` without masking.

### Brute Force Protection

**Rule:** Rate-limit authentication endpoints. Implement account lockout or progressive delays after repeated failed attempts. Use CAPTCHA for public-facing login forms.

**Detect:** Login routes or auth controllers without rate-limiting middleware (`throttle`, `RateLimiter`, `express-rate-limit`, `@ratelimit`).
