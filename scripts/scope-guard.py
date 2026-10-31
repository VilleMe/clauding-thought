#!/usr/bin/env python3
"""PreToolUse hook for Write, Edit, MultiEdit, NotebookEdit: denies writes outside
the active task's declared scope.

Reference it reads: the active task doc's scope section (heading from
`task_docs.headings.scope`, default "Scope"), one path per line, written
before the code. Scope lines are read the way people write them: a
backticked glob with a comment after it, a bare directory, a checkbox item.
Glob vocabulary is that of rule `paths:` frontmatter.

Paths are resolved with realpath on both sides (extended-length prefixes,
8.3 short names, junctions, symlinks) and relative paths are taken against
the hook's cwd. Inert when there is no active task or no scope section.
Always allowed: files outside the project, and the task docs, changelog,
packs, telemetry and self-test files under `.claude/`. The governance files
under `.claude/` (scripts, settings, manifest, rules, patterns, skills,
agents, CLAUDE.md) are NOT exempt while a task is active: a task that is
meant to change them lists them in its scope, visibly.

A denial is a fork, not a wall: the reason tells the model to either record
the discovery in the task doc and stay in scope, or add the path to the
scope section as a visible decision and retry. An internal error is reported
on stderr with exit 1 (visible, non-blocking).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ALWAYS_ALLOWED_IN_CLAUDE = ("tasks/", "CHANGELOG.md", "packs/", "hook-log", "selftest.json", "checkpoint")
GOVERNANCE_IN_CLAUDE = ("scripts/", "settings", "manifest.json", "rules/", "patterns/", "skills/", "agents/", "CLAUDE.md")


def read_hook_input():
    return json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))


try:
    data = read_hook_input()
except Exception:
    sys.exit(0)

try:
    from hook_telemetry import TelemetryLogger
except Exception:
    class TelemetryLogger:
        def __init__(self, *a, **k): pass
        def log(self, *a, **k): pass

try:
    from task_doc import (
        extract_section, find_active_tasks, find_claude_dir, list_items, load_manifest,
        manifest_unreadable, path_matches, project_root, rel_project_path, scope_is_everything,
        task_heading,
    )

    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    path = (ti.get("file_path") or ti.get("notebook_path") or "") if isinstance(ti, dict) else ""
    logger = TelemetryLogger("scope-guard", "PreToolUse", tool, hook_input=data)

    if not path:
        logger.log("allow")
        sys.exit(0)

    claude_dir = find_claude_dir(data.get("cwd"))
    if not claude_dir:
        logger.log("allow", reason="no .claude directory")
        sys.exit(0)

    root = project_root(claude_dir)
    rel = rel_project_path(path, root, base=data.get("cwd"))
    if rel is None:
        logger.log("allow", reason="outside project")
        sys.exit(0)

    in_claude = rel == ".claude" or rel.startswith(".claude/")
    sub = rel[len(".claude/"):] if rel.startswith(".claude/") else ""
    if in_claude and any(sub.startswith(p) for p in ALWAYS_ALLOWED_IN_CLAUDE):
        logger.log("allow", reason="task doc or telemetry")
        sys.exit(0)

    manifest = load_manifest(claude_dir)
    if manifest_unreadable(claude_dir):
        logger.log("allow", reason="manifest unreadable")  # still evaluated below with defaults
    active = find_active_tasks(claude_dir, manifest)
    if not active:
        logger.log("allow", reason="no active task")
        sys.exit(0)

    task_path, task_text = active[0]
    heading = task_heading(manifest, "scope", "Scope")
    globs = list_items(extract_section(task_text, heading), root=root)
    task_name = os.path.basename(task_path)
    context = {"task": task_name}
    if len(active) > 1:
        context["multiple_active_tasks"] = len(active)

    if not globs:
        logger.log("allow", reason="no scope section", context=context)
        sys.exit(0)
    if scope_is_everything(globs):
        logger.log("allow", reason="scope covers everything", context=context)
        sys.exit(0)

    if path_matches(rel, globs):
        logger.log("allow", context=context)
        sys.exit(0)

    governance = in_claude and any(sub.startswith(p) for p in GOVERNANCE_IN_CLAUDE)
    if governance:
        reason = (
            f"SCOPE FORK: `{rel}` is a governance file and the active task {task_name} does not list "
            f"it under `## {heading}`. A task that is meant to change rules, skills, scripts, settings "
            f"or the manifest says so in its scope. Either add `{rel}` (or a glob such as "
            f"`.claude/rules/**`) to `## {heading}` as a visible decision and retry, or leave it to "
            f"the governance skills outside this task."
        )
    else:
        reason = (
            f"SCOPE FORK: `{rel}` is outside the declared `## {heading}` of {task_name}. "
            f"Declared: {', '.join(globs)}. This is a discovery, not a defect. Either "
            f"(a) record it under `## Implementation` in the task doc and continue within "
            f"scope, which is the default; or (b) if the user confirms it belongs to this "
            f"task, add the path to `## {heading}` as a visible decision and retry. "
            f"Do not widen the scope silently."
        )
    logger.log("block", reason="governance file outside scope" if governance else "outside declared scope",
               context={**context, "scope": globs})
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)

except SystemExit:
    raise
except Exception as e:
    print(f"scope-guard: internal error ({type(e).__name__}); write allowed by default", file=sys.stderr)
    sys.exit(1)
