#!/usr/bin/env python3
"""SessionStart hook: creates project-local /init skill if missing.

Ensures /init works by creating .claude/skills/init/SKILL.md from the
plugin's INSTRUCTIONS.md. Also writes .claude/.plugin-root so the init
skill can locate scaffold.py.

Idempotent — does not overwrite existing init skill.
Fail-open: errors exit 0 so they never block the session.
"""
import os
import shutil
import sys

try:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if not plugin_root or not os.path.isdir(plugin_root):
        sys.exit(0)

    project_root = os.getcwd()
    claude_dir = os.path.join(project_root, ".claude")

    # Always write .plugin-root so init skill can find scaffold.py
    os.makedirs(claude_dir, exist_ok=True)
    plugin_root_file = os.path.join(claude_dir, ".plugin-root")
    with open(plugin_root_file, "w", encoding="utf-8") as f:
        f.write(plugin_root)

    # Create project-local init skill if it doesn't exist
    init_skill_dst = os.path.join(claude_dir, "skills", "init", "SKILL.md")
    if not os.path.isfile(init_skill_dst):
        instructions_src = os.path.join(plugin_root, "templates", "init", "INSTRUCTIONS.md")
        if not os.path.isfile(instructions_src):
            sys.exit(0)

        os.makedirs(os.path.dirname(init_skill_dst), exist_ok=True)

        with open(instructions_src, "r", encoding="utf-8") as f:
            instructions_content = f.read()

        frontmatter = (
            "---\n"
            "name: init\n"
            'description: "Analyze this codebase and generate .claude/ governance files"\n'
            'argument-hint: "[--update]"\n'
            "user-invocable: true\n"
            'allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]\n'
            "---\n\n"
        )

        with open(init_skill_dst, "w", encoding="utf-8") as f:
            f.write(frontmatter + instructions_content + "\n")

        # Copy manifest schema
        schema_src = os.path.join(plugin_root, "templates", "init", "manifest.schema.json")
        schema_dst = os.path.join(claude_dir, "skills", "init", "manifest.schema.json")
        if os.path.isfile(schema_src):
            shutil.copy2(schema_src, schema_dst)

    sys.exit(0)

except SystemExit:
    raise
except Exception:
    # Fail open — never block session start
    sys.exit(0)
