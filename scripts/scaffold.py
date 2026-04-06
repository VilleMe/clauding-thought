#!/usr/bin/env python3
"""Scaffolds the .claude/ directory for a new project.

Creates directory structure, copies boilerplate skills, hook scripts,
and stub files. Run before the analysis phase of /init.

Usage:
  python scaffold.py           # Full scaffold for new projects
  python scaffold.py --update  # Refresh boilerplate only (skills, scripts, hooks)

Output: JSON with status, paths, and what was created/remaining.
"""
import json
import os
import shutil
import sys

try:
    # --- Resolve plugin root ---
    # Priority: env var > .claude/.plugin-root file > script's own location
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if not plugin_root:
        skill_dir = os.environ.get("CLAUDE_SKILL_DIR", "")
        if skill_dir:
            plugin_root = os.path.normpath(os.path.join(skill_dir, "..", ".."))

    if not plugin_root or not os.path.isdir(plugin_root):
        # Try reading from .claude/.plugin-root (written by SessionStart hook)
        plugin_root_file = os.path.join(os.getcwd(), ".claude", ".plugin-root")
        if os.path.isfile(plugin_root_file):
            with open(plugin_root_file, "r", encoding="utf-8") as f:
                plugin_root = f.read().strip()

    if not plugin_root or not os.path.isdir(plugin_root):
        # Last resort: derive from this script's own location (scripts/scaffold.py -> plugin root)
        plugin_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

    if not plugin_root or not os.path.isdir(plugin_root):
        print(json.dumps({
            "status": "error",
            "error": "Cannot resolve plugin root directory",
            "CLAUDE_PLUGIN_ROOT": os.environ.get("CLAUDE_PLUGIN_ROOT", "(not set)"),
            "CLAUDE_SKILL_DIR": os.environ.get("CLAUDE_SKILL_DIR", "(not set)"),
            "hint": "Try running /init from the terminal or reinstall the plugin"
        }, indent=2))
        sys.exit(1)

    update_mode = "--update" in sys.argv

    project_root = os.getcwd()
    claude_dir = os.path.join(project_root, ".claude")

    # --- Read plugin version ---
    plugin_json_path = os.path.join(plugin_root, ".claude-plugin", "plugin.json")
    plugin_version = "unknown"
    if os.path.isfile(plugin_json_path):
        with open(plugin_json_path, "r", encoding="utf-8") as f:
            plugin_version = json.load(f).get("version", "unknown")

    # --- Validate for update mode ---
    if update_mode:
        manifest_path = os.path.join(claude_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            print(json.dumps({
                "status": "error",
                "error": "No .claude/manifest.json found — run full /init first",
                "hint": "Run /init without --update to bootstrap the governance layer"
            }, indent=2))
            sys.exit(1)

    # --- 1. Create directory tree ---
    dirs = [
        "skills/preflight", "skills/qc", "skills/evolve", "skills/task-doc",
        "skills/close-task", "skills/export", "skills/report", "skills/insights",
        "skills/critique", "rules", "patterns", "tasks", "memory", "scripts"
    ]
    for d in dirs:
        os.makedirs(os.path.join(claude_dir, d), exist_ok=True)

    # --- 2. Copy boilerplate skills from templates/ ---
    copied_skills = []
    template_skills = ["export", "report", "insights", "critique"]
    for skill in template_skills:
        src = os.path.join(plugin_root, "templates", "skills", skill, "SKILL.md")
        dst = os.path.join(claude_dir, "skills", skill, "SKILL.md")
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied_skills.append(f"skills/{skill}/SKILL.md")

    # Copy changelog-spec.md for evolve skill
    src = os.path.join(plugin_root, "templates", "evolve", "changelog-spec.md")
    dst = os.path.join(claude_dir, "skills", "evolve", "changelog-spec.md")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        copied_skills.append("skills/evolve/changelog-spec.md")

    # --- 3. Copy hook scripts ---
    copied_scripts = []
    scripts_src = os.path.join(plugin_root, "scripts")
    scripts_dst = os.path.join(claude_dir, "scripts")
    hook_scripts = [
        "secret-filter.py", "destructive-guard.py", "anti-rationalization.py",
        "evidence-check.py", "skill-reminder.py", "hook_telemetry.py"
    ]
    for script in hook_scripts:
        src = os.path.join(scripts_src, script)
        dst = os.path.join(scripts_dst, script)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied_scripts.append(script)

    # --- 4. Copy rule templates (for hydration by the agent) ---
    # IMPORTANT: Templates go to rule-templates/, NOT rules/.
    # Claude Code auto-loads .claude/rules/ into the system prompt, and
    # {{handlebars}} syntax in template files crashes Claude Code (exit 3).
    copied_templates = []
    rules_src = os.path.join(plugin_root, "rules")
    templates_dst = os.path.join(claude_dir, "rule-templates")
    os.makedirs(templates_dst, exist_ok=True)
    if os.path.isdir(rules_src):
        for fname in os.listdir(rules_src):
            if fname.endswith(".md"):
                src = os.path.join(rules_src, fname)
                dst = os.path.join(templates_dst, fname)
                shutil.copy2(src, dst)
                copied_templates.append(fname)

    # --- 5. Create project-local init skill from INSTRUCTIONS.md ---
    # Plugin skills don't reliably pass SKILL.md body to the agent.
    # By creating a project-local init skill, /init works correctly.
    init_skill_dst = os.path.join(claude_dir, "skills", "init", "SKILL.md")
    os.makedirs(os.path.dirname(init_skill_dst), exist_ok=True)
    instructions_src = os.path.join(plugin_root, "templates", "init", "INSTRUCTIONS.md")
    if os.path.isfile(instructions_src) and (update_mode or not os.path.isfile(init_skill_dst)):
        with open(instructions_src, "r", encoding="utf-8") as f:
            instructions_content = f.read()
        frontmatter = (
            "---\n"
            "name: init\n"
            'description: "Analyze this codebase and generate the remaining .claude/ governance files. The scaffold script has already created directories and copied boilerplate."\n'
            "user-invocable: true\n"
            'allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]\n'
            "---\n\n"
        )
        with open(init_skill_dst, "w", encoding="utf-8") as f:
            f.write(frontmatter + instructions_content + "\n")
        copied_skills.append("skills/init/SKILL.md (project-local)")

    # Also copy manifest schema for reference
    schema_src = os.path.join(plugin_root, "templates", "init", "manifest.schema.json")
    schema_dst = os.path.join(claude_dir, "skills", "init", "manifest.schema.json")
    if os.path.isfile(schema_src):
        shutil.copy2(schema_src, schema_dst)

    # --- 6. Create settings.json with hooks ---
    # MUST be created by scaffold (not the agent) because Claude Code crashes
    # if settings.json is written mid-session via the Write tool.
    settings_path = os.path.join(claude_dir, "settings.json")
    if not os.path.isfile(settings_path) or update_mode:
        settings = {
            "permissions": {
                "defaultMode": "auto",
                "allow": [
                    "Bash",
                    "Edit",
                    "Write",
                    "WebFetch",
                    "WebSearch",
                    "NotebookEdit"
                ]
            },
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Write|Edit",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python .claude/scripts/secret-filter.py"
                            }
                        ]
                    },
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python .claude/scripts/destructive-guard.py"
                            }
                        ]
                    }
                ],
                "Stop": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python .claude/scripts/anti-rationalization.py"
                            },
                            {
                                "type": "command",
                                "command": "python .claude/scripts/evidence-check.py"
                            }
                        ]
                    }
                ],
                "UserPromptSubmit": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python .claude/scripts/skill-reminder.py"
                            }
                        ]
                    }
                ]
            }
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        copied_skills.append("settings.json (with hooks)")

    # --- 7. Generate stub files (only for full init, skip if they exist) ---
    created_stubs = []
    if not update_mode:
        stubs = {
            "tasks/INDEX.md": (
                "# Task Index\n\n"
                "| Date | Task | Status | Module | Commit |\n"
                "|------|------|--------|--------|--------|\n"
            ),
            "memory/MEMORY.md": (
                "# Project Memory\n\n"
                "Lessons learned and decisions from tasks are recorded here.\n"
                "Lines after 200 will be truncated from auto-loading, so keep this file concise.\n"
                "Use topic files (e.g., `security-lessons.md`, `architecture-decisions.md`) for detailed notes.\n"
            ),
            "memory/decisions.md": (
                "# Governance Decisions\n\n"
                "Timestamped log of changes to the governance layer, maintained by `/evolve`.\n\n"
                "| Date | Decision | Reason | Source |\n"
                "|------|----------|--------|--------|\n"
            ),
        }
        for path, content in stubs.items():
            filepath = os.path.join(claude_dir, path)
            if not os.path.exists(filepath):
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                created_stubs.append(path)

    # --- Build result ---
    result = {
        "status": "success",
        "mode": "update" if update_mode else "full",
        "plugin_root": plugin_root,
        "plugin_version": plugin_version,
        "claude_dir": claude_dir,
        "copied_skills": copied_skills,
        "copied_scripts": copied_scripts,
        "copied_rule_templates": copied_templates,
        "created_stubs": created_stubs,
    }

    if update_mode:
        result["next_steps"] = [
            "Update governance.plugin_version in .claude/manifest.json",
            "Add [Unreleased] changelog entry",
            "Report what was updated"
        ]
    else:
        result["remaining_for_agent"] = [
            ".claude/manifest.json — generate from codebase analysis",
            ".claude/CLAUDE.md — generate governance rules from analysis",
            ".claude/CHANGELOG.md — generate initial version entry",
            ".claude/rules/security.md — hydrate from rule-templates/security.md using analysis",
            ".claude/rules/architecture.md — hydrate from rule-templates/architecture.md using analysis",
            ".claude/rules/conventions.md — hydrate from rule-templates/conventions.md using analysis",
            ".claude/patterns/*.md — generate from code samples",
            ".claude/skills/preflight/SKILL.md — generate project-customized",
            ".claude/skills/qc/SKILL.md — generate project-customized",
            ".claude/skills/evolve/SKILL.md — generate project-customized",
            ".claude/skills/task-doc/SKILL.md — generate project-customized",
            ".claude/skills/close-task/SKILL.md — generate project-customized",
        ]

    print(json.dumps(result, indent=2))
    sys.exit(0)

except SystemExit:
    raise
except Exception as e:
    print(json.dumps({"status": "error", "error": str(e)}, indent=2))
    sys.exit(1)
