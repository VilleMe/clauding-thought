## A05:2021 — Security Misconfiguration
<!-- severity: warning -->

Security misconfiguration is the most common issue in the OWASP Top 10. It occurs when security settings are defined, implemented, or maintained improperly. This includes missing security hardening, unnecessary features enabled, default accounts, and overly permissive configurations.

Reference: [OWASP A05:2021](https://owasp.org/Top10/A05_2021-Security_Misconfiguration/), CWE-16, CWE-611, CWE-1004

### Debug Mode in Production

**Rule:** Debug mode, verbose error reporting, and development-only features must be disabled in production configurations. Use environment-based configuration to ensure debug settings cannot leak into production.

**Detect:**
- `DEBUG = True` or `APP_DEBUG=true` in production environment files
- `display_errors = On` in PHP production config
- `NODE_ENV` not set to `production` in deployment scripts
- Stack trace middleware enabled without environment guards

### Security Headers

**Rule:** All HTTP responses must include security headers. At minimum: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (or `SAMEORIGIN`), `Strict-Transport-Security`, `Content-Security-Policy`.

**Detect:** Missing security header middleware in the application pipeline. Response objects without security headers in custom response handlers.

### CORS Configuration

**Rule:** Never use wildcard (`*`) for `Access-Control-Allow-Origin` on endpoints that serve authenticated or sensitive data. Explicitly list allowed origins. Never reflect the `Origin` header as-is without validation.

**Detect:**
- `Access-Control-Allow-Origin: *` in middleware or response headers
- Origin header reflected without allowlist check
- `Access-Control-Allow-Credentials: true` combined with wildcard origin

**Good:**
```python
CORS_ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://admin.example.com",
]
```

**Bad:**
```python
CORS_ALLOW_ALL_ORIGINS = True
# or
response["Access-Control-Allow-Origin"] = request.headers["Origin"]
```

### Default Credentials

**Rule:** Never ship default passwords, admin accounts, or API keys. Require credential setup during installation or first run. Remove or disable sample/demo accounts before deployment.

**Detect:** Hardcoded usernames/passwords in seed files, migration scripts, or configuration that appear to be default credentials (`admin`/`admin`, `root`/`password`, `test`/`test`).

### Unnecessary Features and Services

**Rule:** Disable or remove features, frameworks, and components that are not in use. This includes sample applications, debug endpoints, unused API routes, and development-only middleware.

**Detect:**
- Debug/profiler routes (`/_debugbar`, `/phpinfo`, `/__debug__`) without environment guards
- Development-only packages in production dependencies (not devDependencies)
- Enabled but unused services in configuration files

### XML External Entity Processing (CWE-611)

**Rule:** Disable external entity processing in all XML parsers. Use JSON where possible. If XML is required, configure parsers to disallow DTDs, external entities, and parameter entities.

**Detect:** XML parser instantiation without explicitly disabling external entities. `LIBXML_NOENT`, `resolve_entities=True`, or missing `setFeature(XMLConstants.FEATURE_SECURE_PROCESSING)`.

**Good:**
```python
from defusedxml import ElementTree
tree = ElementTree.parse(xml_file)
```

**Bad:**
```python
from xml.etree.ElementTree import parse
tree = parse(user_uploaded_xml)
```
