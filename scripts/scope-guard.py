#!/usr/bin/env python3
"""PreToolUse hook for Write, Edit, MultiEdit, NotebookEdit: denies writes outside
the active task's declared scope.

Reference it reads: the active task doc's scope section (heading from
`task_docs.headings.scope`, default "Scope"), one path glob per line, written
before the code. Glob vocabulary is the same as rule `paths:` frontmatter.

Inert when there is no active task or no scope section. Always allowed:
anything under `.claude/` and anything outside the project root (plan files,
the session scratchpad, the native memory directory all live there).

A denial is a fork, not a wall: the reason tells the model to either record
the discovery in the task doc and stay in scope, or add the path to the scope
section as a visible decision and retry. Fail-open on any error.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    from hook_telemetry import TelemetryLogger
    from task_doc import (
        extract_section, find_active_tasks, find_claude_dir, list_items,
        load_manifest, path_matches, project_root, rel_project_path, task_heading,
    )

    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    logger = TelemetryLogger("scope-guard", "PreToolUse", tool, hook_input=data)

    if not path:
        logger.log("allow")
        sys.exit(0)

    claude_dir = find_claude_dir(data.get("cwd"))
    if not claude_dir:
        logger.log("allow", reason="no .claude directory")
        sys.exit(0)

    rel = rel_project_path(path, project_root(claude_dir))
    if rel is None:
        logger.log("allow", reason="outside project")
        sys.exit(0)
    if rel == ".claude" or rel.startswith(".claude/"):
        logger.log("allow", reason="governance directory")
        sys.exit(0)

    manifest = load_manifest(claude_dir)
    active = find_active_tasks(claude_dir, manifest)
    if not active:
        logger.log("allow", reason="no active task")
        sys.exit(0)

    task_path, task_text = active[0]
    heading = task_heading(manifest, "scope", "Scope")
    globs = list_items(extract_section(task_text, heading))
    task_name = os.path.basename(task_path)
    context = {"task": task_name}
    if len(active) > 1:
        context["multiple_active_tasks"] = len(active)

    if not globs:
        logger.log("allow", reason="no scope section", context=context)
        sys.exit(0)

    if path_matches(rel, globs):
        logger.log("allow", context=context)
        sys.exit(0)

    reason = (
        f"SCOPE FORK: `{rel}` is outside the declared `## {heading}` of {task_name}. "
        f"Declared: {', '.join(globs)}. This is a discovery, not a defect. Either "
        f"(a) record it under `## Implementation` in the task doc and continue within "
        f"scope, which is the default; or (b) if the user confirms it belongs to this "
        f"task, add the path to `## {heading}` as a visible decision and retry. "
        f"Do not widen the scope silently."
    )
    logger.log("block", reason="outside declared scope",
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
except Exception:
    sys.exit(0)  # fail-open: the guard must never take down the tool
