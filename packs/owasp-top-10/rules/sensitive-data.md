## A02:2021 — Cryptographic Failures (Sensitive Data Exposure)
<!-- severity: error -->

Sensitive data exposure occurs when applications fail to adequately protect sensitive information such as financial data, healthcare records, or personal identifiers. This includes failures in encryption, key management, and data classification.

Reference: [OWASP A02:2021](https://owasp.org/Top10/A02_2021-Cryptographic_Failures/), CWE-311, CWE-312, CWE-327

### Data in Transit

**Rule:** All data transmitted over networks must use TLS 1.2 or higher. Enforce HTTPS via redirects and HSTS headers. Never transmit sensitive data over plain HTTP.

**Detect:** HTTP URLs in configuration files (non-localhost), missing HSTS headers in security middleware, `verify=False` or `InsecureRequestWarning` suppressions in HTTP client code.

### Data at Rest

**Rule:** Encrypt sensitive data at rest using AES-256-GCM or equivalent. Use database-level encryption for PII columns. Never store sensitive data in plaintext in databases, files, or caches.

**Detect:** Database columns storing PII (email, SSN, credit card, phone, address) without encryption annotations or encrypted cast. Cache operations storing user credentials or tokens without encryption.

### Weak Cryptographic Algorithms (CWE-327)

**Rule:** Use only current, strong cryptographic algorithms. Prohibited: MD5, SHA1 (for security purposes), DES, 3DES, RC4, ECB mode. Required minimums: AES-256 for symmetric, RSA-2048/EC-P256 for asymmetric, SHA-256+ for hashing.

**Detect:**
- `MD5`, `SHA1` usage for integrity or security (not checksums of non-sensitive data)
- `DES`, `3DES`, `RC4` cipher usage
- `ECB` mode in any block cipher
- RSA keys under 2048 bits
- Hardcoded encryption keys, IVs, or salts

**Good:**
```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()  # AES-128-CBC under the hood
cipher = Fernet(key)
```

**Bad:**
```python
from Crypto.Cipher import DES
cipher = DES.new(key, DES.MODE_ECB)
```

### Key Management

**Rule:** Never hardcode cryptographic keys, API keys, or secrets in source code. Use environment variables, secret managers (AWS Secrets Manager, HashiCorp Vault, Azure Key Vault), or encrypted configuration.

**Detect:** String literals assigned to variables named `*key*`, `*secret*`, `*password*` that appear to be actual credential values (not placeholders or environment variable references).

### Sensitive Data in Error Messages

**Rule:** Never expose stack traces, database queries, internal paths, or sensitive data in error responses shown to users. Use generic error messages in production. Log detailed errors server-side only.

**Detect:** Exception handlers that render full stack traces or raw error messages to HTTP responses. Debug mode enabled in production configuration files.
