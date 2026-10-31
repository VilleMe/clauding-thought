#!/usr/bin/env python3
"""Shared helpers for hook scripts that read the project's .claude/ directory.

All operations are fail-soft: missing files, parse errors, or unexpected
shapes return empty/neutral values so hooks can decide silently.
"""
import json
import os
import re
import sys

IS_WINDOWS = sys.platform.startswith("win")


# --------------------------------------------------------------------------
# Reading hook input and files
# --------------------------------------------------------------------------

def read_hook_input():
    """Hook stdin is UTF-8 whatever the console code page says."""
    raw = sys.stdin.buffer.read()
    return json.loads(raw.decode("utf-8", "surrogateescape"))


def read_text(path):
    """Read a text file whatever its encoding: BOM-aware, UTF-16 tolerant,
    bad bytes replaced. Returns '' on failure."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return ""
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if raw.startswith(bom):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                break
    if len(raw) > 1 and raw[1:2] == b"\x00" and raw[0:1] != b"\x00":
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Locating things
# --------------------------------------------------------------------------

def find_claude_dir(start=None):
    """Nearest `.claude/` walking up from `start` (or cwd), stopping at the
    first directory that contains `.git`, never the user's own `~/.claude`."""
    try:
        home_claude = os.path.normcase(os.path.join(os.path.expanduser("~"), ".claude"))
        current = os.path.abspath(start) if start and os.path.isdir(start) else os.getcwd()
        for _ in range(12):
            candidate = os.path.join(current, ".claude")
            if os.path.isdir(candidate) and os.path.normcase(candidate) != home_claude:
                return candidate
            if os.path.exists(os.path.join(current, ".git")):
                return None
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    except Exception:
        pass
    return None


def project_root(claude_dir):
    return os.path.dirname(os.path.abspath(claude_dir)) if claude_dir else None


def load_manifest(claude_dir):
    """Parsed manifest.json, or {} when missing or unreadable. The second
    return value says whether a file existed but could not be parsed."""
    if not claude_dir:
        return {}
    path = os.path.join(claude_dir, "manifest.json")
    if not os.path.isfile(path):
        return {}
    try:
        data = json.loads(read_text(path))
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def manifest_unreadable(claude_dir):
    path = os.path.join(claude_dir or "", "manifest.json")
    if not claude_dir or not os.path.isfile(path):
        return False
    try:
        json.loads(read_text(path))
        return False
    except (ValueError, TypeError):
        return True


def task_heading(manifest, key, default):
    try:
        value = (manifest or {}).get("task_docs", {}).get("headings", {}).get(key)
        return value.strip() if isinstance(value, str) and value.strip() else default
    except Exception:
        return default


def verification(manifest):
    try:
        block = (manifest or {}).get("verification", {})
        return block if isinstance(block, dict) else {}
    except Exception:
        return {}


def positive_int(value, default):
    try:
        n = int(value)
        return n if n >= 1 else default
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# Task docs
# --------------------------------------------------------------------------

# One status parser for every consumer. Accepts `status: open`, `**Status:** open`,
# `- **Status:** closed 2026-08-25 (note)`, `status: "open"`, `Status: In Progress`,
# `| Status | Closed |`, `**Status:** **closed 2026-08-22**`. The first status line wins;
# the value is its first word, plus a second word for two-word states (in progress, on hold).
_STATUS_LINE_RE = re.compile(
    r"(?im)^[\s|*_+-]*status[*_]*\s*(?::|\|)\s*[*_\"'` ]*([A-Za-z][A-Za-z_-]*(?:\s+(?:progress|review|hold|flight|work|planning))?)"
)
ACTIVE_STATUSES = {"open", "in_progress", "active"}  # a task in review is no longer being written to
CLOSED_STATUSES = {"closed", "done", "complete", "completed", "resolved", "merged", "abandoned", "superseded"}


def task_status(text):
    """Normalised status word (`in_progress`, `closed`, ...) from the first
    status line in the doc, or 'unknown'."""
    if not text:
        return "unknown"
    m = _STATUS_LINE_RE.search(strip_fenced_blocks(text))
    if not m:
        return "unknown"
    return re.sub(r"[\s-]+", "_", m.group(1).strip().lower())


def is_active_status(status):
    return status in ACTIVE_STATUSES


def task_docs_dir(claude_dir, manifest=None):
    directory = (manifest or {}).get("task_docs", {}).get("directory") or "tasks"
    return os.path.join(claude_dir, directory)


def iter_task_docs(claude_dir, manifest=None):
    """(path, text) for every markdown task doc, recursively, INDEX.md excluded."""
    if not claude_dir:
        return
    root = task_docs_dir(claude_dir, manifest)
    if not os.path.isdir(root):
        return
    for dirpath, _dirs, files in os.walk(root):
        for fname in sorted(files):
            if not fname.lower().endswith(".md") or fname.upper() == "INDEX.MD":
                continue
            fpath = os.path.join(dirpath, fname)
            text = read_text(fpath)
            if text:
                yield fpath, text


def find_active_tasks(claude_dir, manifest=None):
    """All active task docs, newest modified first: [(path, text), ...]."""
    try:
        found = []
        for fpath, text in iter_task_docs(claude_dir, manifest):
            if is_active_status(task_status(text)):
                found.append((os.path.getmtime(fpath), fpath, text))
        found.sort(reverse=True)
        return [(p, t) for _, p, t in found]
    except Exception:
        return []


def find_active_task(claude_dir, manifest=None):
    active = find_active_tasks(claude_dir, manifest)
    return active[0] if active else (None, None)


def extract_section(text, heading):
    """Body of a `# Heading` .. `###### Heading` section (case-insensitive,
    trailing colon or parenthetical tolerated, fenced blocks removed first),
    up to the next heading of any level or EOF."""
    if not text or not heading:
        return ""
    clean = strip_fenced_blocks(text)
    pattern = rf"(?im)^#{{1,6}}\s*{re.escape(heading)}\s*(?::|\([^)\n]*\))?\s*$"
    m = re.search(pattern, clean)
    if not m:
        return ""
    rest = clean[m.end():]
    n = re.search(r"(?m)^#{1,6}\s", rest)
    return rest[: n.start()] if n else rest


_LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(.*)$")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")


def list_items(section_text, root=None):
    """Items of a markdown list, read the way people write scope lines:
    the first backticked span if there is one, else the first whitespace-
    delimited token; checkbox markers dropped; a trailing `/` or an existing
    directory becomes `<dir>/**`."""
    items = []
    for line in (section_text or "").splitlines():
        m = _LIST_LINE_RE.match(line)
        if not m:
            continue
        body = m.group(1).strip()
        if not body:
            continue
        bt = _BACKTICK_RE.search(body)
        item = bt.group(1).strip() if bt else body.split()[0].strip()
        item = item.rstrip(",;:")
        if not item or item in ("**", "*"):
            if item:
                items.append(item)
            continue
        if item.endswith("/"):
            item = item + "**"
        elif root and "*" not in item and "?" not in item and "{" not in item:
            candidate = os.path.join(root, normalize_path(item))
            if os.path.isdir(candidate):
                item = item + "/**"
        items.append(item)
    return items


# --------------------------------------------------------------------------
# Thesis section
# --------------------------------------------------------------------------

_OPT_OUT_RE = re.compile(r"no-user-observable-change[\s*_]*:[\s*_]*true\b", re.I)
_CANNOT_RE = re.compile(r"(?im)^\s*\**cannot-demonstrate-here\**\s*:\**\s*(\S.*)$")
_OPT_OUT_HEADING_RE = re.compile(r"(?im)^#{1,6}\s+no\s+user[- ]observable\s+change\b")
_DEMO_RE = re.compile(
    r"^\s*(?P<ts>\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)\s*"
    r"(?P<how>via\s+/verify|via\s+[^:\n]+|attested\s+by\s+[^:\n]+)\s*:?",
    re.I,
)


def _labelled_value(section, label):
    m = re.search(rf"(?im)^\s*(?:[-*+]\s+)?\**{re.escape(label)}\**\s*:\**\s*(.*)$", section)
    return (m.group(1) or "").strip() if m else ""


def thesis_status(text, heading="Thesis"):
    """What a task doc declares about its user-visible outcome.

    opted_out: `no-user-observable-change: true` or a No User-Observable Change section.
    cannot_demonstrate: a `cannot-demonstrate-here: <reason>` line (honest alternative).
    present / claim / observable: the section and its labelled lines exist.
    demonstrated: the Demonstrated line STARTS with a date followed by how it
    was shown (`via /verify: ...`, `via <command>: ...`). attested: same shape
    with `attested by <who>: ...` (recorded by a person, not a run).
    """
    out = {"opted_out": False, "cannot_demonstrate": False, "present": False, "claim": False,
           "observable": False, "demonstrated": False, "attested": False}
    if not text:
        return out
    head = text[:4096]
    if _OPT_OUT_RE.search(head) or _OPT_OUT_HEADING_RE.search(text):
        out["opted_out"] = True
    if _CANNOT_RE.search(head):
        out["cannot_demonstrate"] = True
    section = strip_fenced_blocks(extract_section(text, heading))
    if not section.strip():
        return out
    out["present"] = True
    out["claim"] = bool(_labelled_value(section, "Claim"))
    out["observable"] = bool(_labelled_value(section, "Observable"))
    m = _DEMO_RE.match(_labelled_value(section, "Demonstrated"))
    if m:
        if m.group("how").lower().startswith("attested"):
            out["attested"] = True
        else:
            out["demonstrated"] = True
    return out


# --------------------------------------------------------------------------
# Path globs (same vocabulary as rule `paths:` frontmatter)
# --------------------------------------------------------------------------

def normalize_path(path):
    return (path or "").replace("\\", "/")


def strip_dot_slash(rel):
    rel = normalize_path(rel)
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def real(path):
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return os.path.abspath(path)


def rel_project_path(file_path, root, base=None):
    """Project-relative, forward-slash path, or None when outside the project.

    Resolves extended-length (verbatim) prefixes, 8.3 short names, junctions
    and symlinks through realpath on both sides. A relative file_path is taken relative to `base`
    (the hook's cwd), not the process cwd. For a file that does not exist
    yet, its nearest existing ancestor is resolved.
    """
    if not file_path or not root:
        return None
    try:
        fp = normalize_path(file_path)
        if fp.startswith("//?/") or fp.startswith("\\\\?\\"):
            fp = fp[4:]
        if not os.path.isabs(fp):
            fp = os.path.join(base or os.getcwd(), fp)
        # resolve the deepest existing ancestor, then re-append the rest
        parts = []
        probe = os.path.abspath(fp)
        while not os.path.exists(probe):
            parent, leaf = os.path.split(probe)
            if parent == probe:
                break
            parts.append(leaf)
            probe = parent
        resolved = real(probe)
        for leaf in reversed(parts):
            resolved = os.path.join(resolved, leaf)
        rt = real(root)
        try:
            common = os.path.commonpath([os.path.normcase(resolved), os.path.normcase(rt)])
        except ValueError:
            return None
        if os.path.normcase(common) != os.path.normcase(rt):
            return None
        rel = os.path.relpath(resolved, rt)
        return normalize_path(rel)
    except Exception:
        return None


def expand_braces(glob):
    m = re.search(r"\{([^{}]*)\}", glob)
    if not m:
        return [glob]
    head, tail = glob[: m.start()], glob[m.end():]
    out = []
    for alt in m.group(1).split(","):
        out.extend(expand_braces(head + alt.strip() + tail))
    return out


def glob_to_regex(glob):
    parts = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            parts.append(".*")
            i += 2
        elif glob[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            parts.append("[^/]")
            i += 1
        elif glob[i] == "[":
            j = glob.find("]", i + 1)
            if j > i:
                parts.append("[" + glob[i + 1:j].replace("\\", "\\\\") + "]")
                i = j + 1
            else:
                parts.append(re.escape(glob[i]))
                i += 1
        else:
            parts.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(parts) + "$", re.I)


def path_matches(rel_path, globs):
    """True when rel_path matches any glob. A glob without `/` also matches
    the basename, so `*.md` means any markdown file at any depth."""
    rel = strip_dot_slash(rel_path)
    base = rel.rsplit("/", 1)[-1]
    for raw in globs or []:
        for g in expand_braces(strip_dot_slash(raw.strip())):
            if not g:
                continue
            try:
                rx = glob_to_regex(g)
            except re.error:
                continue
            if rx.match(rel):
                return True
            if "/" not in g and rx.match(base):
                return True
            if g.endswith("/**") and rel.lower() == g[:-3].lower():
                return True
    return False


def scope_is_everything(globs):
    return any(g.strip() in ("**", "*", "**/*") for g in globs or [])


# --------------------------------------------------------------------------
# Text cleanup
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"(?ms)^\s*(```|~~~)[^\n]*\n.*?^\s*\1\s*$")
_INLINE_CODE_RE = re.compile(r"`{1,2}[^`\n]+?`{1,2}")
_BLOCKQUOTE_RE = re.compile(r"(?m)^\s*>.*$")


def strip_fenced_blocks(text):
    if not text:
        return text
    return _FENCE_RE.sub("", text)


def strip_quotes_and_fences(text):
    """Fenced blocks and blockquotes removed; inline code kept (a claim in
    backticks is still a claim)."""
    if not text:
        return text
    return _BLOCKQUOTE_RE.sub("", _FENCE_RE.sub("", text))


def strip_code_and_quotes(text):
    """Fenced blocks, inline code, and blockquotes removed."""
    if not text:
        return text
    return _BLOCKQUOTE_RE.sub("", _INLINE_CODE_RE.sub("", _FENCE_RE.sub("", text)))
