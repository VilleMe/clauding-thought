## A03:2021 — Injection
<!-- severity: error -->

Injection flaws (SQL, NoSQL, OS command, LDAP, XSS) occur when untrusted data is sent to an interpreter as part of a command or query. The attacker's hostile data can trick the interpreter into executing unintended commands or accessing data without authorization.

Reference: [OWASP A03:2021](https://owasp.org/Top10/A03_2021-Injection/), CWE-79, CWE-89, CWE-78

### SQL Injection (CWE-89)

**Rule:** Never concatenate or interpolate user input into SQL query strings. Always use parameterized queries or the ORM's query builder.

**Detect:** Look for string concatenation (`+`, `f""`, `$""`, `.format()`) inside SQL strings, or raw query methods (`DB::raw`, `cursor.execute`, `createNativeQuery`) receiving unparameterized input.

**Good:**
```
-- Parameterized (any language)
SELECT * FROM users WHERE id = ?
SELECT * FROM users WHERE id = :id
```

**Bad:**
```
-- Concatenated
"SELECT * FROM users WHERE id = " + userId
f"SELECT * FROM users WHERE id = {user_id}"
```

### Command Injection (CWE-78)

**Rule:** Never pass user-controlled input to shell execution functions without validation. Prefer library functions over shell commands. If shell execution is unavoidable, use allowlists for permitted values — never blocklists.

**Detect:** `exec()`, `system()`, `shell_exec()`, `popen()`, `subprocess.run(..., shell=True)`, backtick operators, or `child_process.exec()` where any argument originates from request parameters, query strings, or form data.

**Good:**
```python
# Use library functions instead of shell
import shutil
shutil.copy(src, dst)

# If shell is unavoidable, use subprocess without shell=True
subprocess.run(["ls", "-la", validated_path], shell=False)
```

**Bad:**
```python
os.system(f"convert {user_filename} output.pdf")
subprocess.run(f"grep {user_input} /var/log/app.log", shell=True)
```

### Cross-Site Scripting / XSS (CWE-79)

**Rule:** Always escape user-supplied data before rendering it in HTML. Use the framework's default escaping. Only use raw/unescaped output for content that has been explicitly sanitized through a trusted HTML sanitizer.

**Detect:** Raw output directives (`{!! !!}` in Blade, `|safe` in Jinja/Django, `dangerouslySetInnerHTML` in React, `v-html` in Vue, `[innerHTML]` in Angular) where the data source traces back to user input, database content, or external APIs.

**Good:**
```html
<!-- Auto-escaped (default in most frameworks) -->
{{ user.name }}
<p>{userName}</p>
```

**Bad:**
```html
{!! $userComment !!}
<div dangerouslySetInnerHTML={{__html: userContent}} />
<div v-html="userMessage"></div>
```

### Path Traversal (CWE-22)

**Rule:** Validate and canonicalize file paths before use. Reject paths containing `..` sequences. Resolve the canonical path and verify it falls within the expected base directory.

**Detect:** File operations (`open()`, `readFile()`, `file_get_contents()`, `File.read()`) where the path argument includes user-controlled segments without canonicalization and base-directory checks.
