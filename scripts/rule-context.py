#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write — re-emphasize relevant rules at edit time.

Rules in `.claude/rules/*.md` are auto-loaded by Claude Code at session start.
After many turns they drift to the back of context. This hook matches the
file the agent is about to edit against rule path globs and section scopes,
selects up to 2 most-specific matching sections, and emits them as
PreToolUse `additionalContext` so the relevant rules are fresh in the next
turn's context.

Opt-in via `governance.enforcement.rule_context` (default false). When the
flag is off, the hook still runs the matching and logs `decision: "skipped"`
with the rules it WOULD have surfaced — `/report` reads this to show what
turning the flag on would inject.

Never blocks. Always exits 0. Fail-soft on every error path.
"""
import sys, json, os, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger
from task_doc import find_claude_dir, get_enforcement_flag


MAX_SECTIONS = 2
MAX_SECTION_CHARS = 800
TOTAL_BUDGET_CHARS = 1600


_SECTION_RE = re.compile(r"(?ms)^##\s+(.+?)\s*\n(.*?)(?=^##\s|\Z)")
_SCOPE_RE = re.compile(r"<!--\s*scope:\s*([^>]+?)\s*-->")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_PATHS_LINE_RE = re.compile(r"(?m)^\s+-\s+\"?([^\"\n]+?)\"?\s*$")


def glob_to_regex(glob):
    """Convert a path glob (with **, *, ?) to an anchored regex.

    `**` matches any number of path segments (including zero).
    `*` matches any chars except `/`.
    """
    parts = []
    i = 0
    while i < len(glob):
        if glob[i:i + 2] == "**":
            parts.append(".*")
            i += 2
            if i < len(glob) and glob[i] == "/":
                i += 1
        elif glob[i] == "*":
            parts.append(r"[^/]*")
            i += 1
        elif glob[i] == "?":
            parts.append(r"[^/]")
            i += 1
        elif glob[i] in ".+()[]{}^$|\\":
            parts.append(re.escape(glob[i]))
            i += 1
        else:
            parts.append(glob[i])
            i += 1
    return re.compile("^" + "".join(parts) + "$")


def specificity(glob):
    """Higher = more specific. Wildcards penalize heavily."""
    return len(glob) - glob.count("*") * 5 - glob.count("?") * 2


def parse_frontmatter_paths(text):
    """Return the list of glob strings from the YAML frontmatter `paths:` array."""
    fm = _FRONTMATTER_RE.match(text)
    if not fm:
        return []
    block = fm.group(1)
    # Find a paths: section, then collect indented `- "glob"` lines until dedent
    m = re.search(r"(?m)^paths\s*:\s*\n((?:\s+-\s+.+\n)+)", block + "\n")
    if not m:
        return []
    return [g.strip() for g in _PATHS_LINE_RE.findall(m.group(1))]


def parse_sections(text):
    """Yield (title, body, scope_globs) for each `## Section` in text.

    scope_globs is the parsed `<!-- scope: a, b, c -->` list, or [] if absent.
    """
    for m in _SECTION_RE.finditer(text):
        title = m.group(1).strip()
        body = m.group(2)
        sm = _SCOPE_RE.search(body)
        scopes = []
        if sm:
            scopes = [s.strip() for s in sm.group(1).split(",") if s.strip()]
        yield title, body.strip(), scopes


def normalize_path(file_path, project_root):
    """Return the file path relative to project_root, with forward slashes."""
    if not file_path:
        return ""
    try:
        abs_path = os.path.abspath(file_path)
        rel = os.path.relpath(abs_path, project_root)
        return rel.replace(os.sep, "/")
    except ValueError:
        # Different drive on Windows; treat as best effort
        return file_path.replace(os.sep, "/")


def collect_matches(rules_dir, rel_path):
    """Return [(specificity, file_basename, title, body)] for sections whose
    scope (or file-level paths) matches rel_path.
    """
    if not os.path.isdir(rules_dir):
        return []
    matches = []
    for fname in sorted(os.listdir(rules_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(rules_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        file_globs = parse_frontmatter_paths(text)
        for title, body, scopes in parse_sections(text):
            applicable_globs = scopes or file_globs
            if not applicable_globs:
                continue
            best = None
            for g in applicable_globs:
                try:
                    rx = glob_to_regex(g)
                except re.error:
                    continue
                if rx.match(rel_path):
                    s = specificity(g)
                    if best is None or s > best:
                        best = s
            if best is not None:
                matches.append((best, fname, title, body))
    matches.sort(key=lambda t: -t[0])
    return matches


_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def clean_body(body):
    """Strip HTML comments (severity/scope annotations) from rule body."""
    cleaned = _HTML_COMMENT_RE.sub("", body)
    # Collapse multiple blank lines that may remain after stripping
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def truncate_body(body, limit):
    body = clean_body(body)
    if len(body) <= limit:
        return body
    cut = body[:limit]
    # Prefer to cut at a paragraph or list-item boundary
    for sep in ("\n\n", "\n- ", "\n"):
        idx = cut.rfind(sep)
        if idx > limit // 2:
            return cut[:idx].rstrip() + "\n\n…(truncated)"
    return cut.rstrip() + "…"


def build_context(rel_path, top_matches):
    parts = [f"Rule reminders for editing `{rel_path}`:\n"]
    used = len(parts[0])
    for _spec, fname, title, body in top_matches:
        block = (
            f"\n## {title}  _(from {fname})_\n\n"
            f"{truncate_body(body, MAX_SECTION_CHARS)}\n"
        )
        if used + len(block) > TOTAL_BUDGET_CHARS:
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    logger = TelemetryLogger("rule-context", "PreToolUse", matcher=tool_name)

    if tool_name not in ("Edit", "Write"):
        logger.log("allow")
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        logger.log("allow")
        sys.exit(0)

    claude_dir = find_claude_dir()
    if not claude_dir:
        logger.log("allow")
        sys.exit(0)

    project_root = os.path.dirname(claude_dir)
    rel_path = normalize_path(file_path, project_root)
    if not rel_path or rel_path.startswith(".."):
        # File outside project root — nothing to inject
        logger.log("allow")
        sys.exit(0)

    rules_dir = os.path.join(claude_dir, "rules")
    matches = collect_matches(rules_dir, rel_path)
    top = matches[:MAX_SECTIONS]

    flag_on = get_enforcement_flag(claude_dir, "rule_context")

    if not top:
        # Nothing matched; still log so /report can show no-match cases
        logger.log("allow", reason="no rules match path",
                   context={"file": rel_path})
        sys.exit(0)

    rule_summary = [{"file": fname, "section": title}
                    for _spec, fname, title, _body in top]

    if flag_on:
        context_text = build_context(rel_path, top)
        try:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": context_text,
                }
            }))
        except (OSError, ValueError):
            pass
        logger.log("feedback",
                   reason="Injected rule context",
                   context={"file": rel_path, "rules": rule_summary,
                            "chars": len(context_text)})
    else:
        logger.log("skipped",
                   reason="Rule context would have been injected",
                   context={"file": rel_path, "rules": rule_summary,
                            "flag": "rule_context"})

    sys.exit(0)


try:
    main()
except SystemExit:
    raise
except Exception:
    sys.exit(0)  # fail-open
