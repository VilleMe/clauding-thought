#!/usr/bin/env python3
"""Scaffolds the .claude/ governance directory for a project.

Creates the directory tree, copies hook scripts and boilerplate skills, writes
or updates .claude/settings.json with the governance hooks, and creates stub
files. Run by the /init skill before the analysis phase.

Usage:
  python scaffold.py           # Full scaffold for a new project
  python scaffold.py --update  # Refresh scripts, boilerplate skills, and hooks only

Output: JSON with status, paths, and what was created or remains for the agent.
"""
import json
import os
import shutil
import sys

HOOK_SCRIPTS = [
    "secret-filter.py",
    "destructive-guard.py",
    "anti-rationalization.py",
    "evidence-check.py",
    "hook_telemetry.py",
    "task_doc.py",
    "report_data.py",
]

GENERATED_SKILLS = ["preflight", "qc", "evolve", "task-doc", "close-task"]
BOILERPLATE_SKILLS = ["report"]

PLUGIN_HOOK_SCRIPTS = {"secret-filter.py", "destructive-guard.py",
                       "anti-rationalization.py", "evidence-check.py"}

# Scripts earlier plugin versions installed and 3.0 no longer ships. Their hook
# registrations are removed on scaffold and the files deleted from .claude/scripts/.
RETIRED_SCRIPTS = {"skill-reminder.py", "rule-context.py", "deferral-check.py",
                   "thesis-check.py", "setup-user-dir.py"}


def resolve_plugin_root():
    """Priority: env var > CLAUDE_SKILL_DIR > .claude/.plugin-root > this file's location."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if not root:
        skill_dir = os.environ.get("CLAUDE_SKILL_DIR", "")
        if skill_dir:
            root = os.path.normpath(os.path.join(skill_dir, "..", ".."))
    if not root or not os.path.isdir(root):
        marker = os.path.join(os.getcwd(), ".claude", ".plugin-root")
        if os.path.isfile(marker):
            with open(marker, "r", encoding="utf-8") as f:
                root = f.read().strip()
    if not root or not os.path.isdir(root):
        root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return root if os.path.isdir(root) else ""


def python_command():
    """Interpreter name for hook commands. Windows ships `python`; Unix ships `python3`."""
    return "python" if sys.platform.startswith("win") else "python3"


def plugin_hooks(py):
    def cmd(script):
        return {"type": "command", "command": f"{py} .claude/scripts/{script}"}

    return {
        "PreToolUse": [
            {"matcher": "Write|Edit", "hooks": [cmd("secret-filter.py")]},
            {"matcher": "Bash", "hooks": [cmd("destructive-guard.py")]},
        ],
        "Stop": [
            {"matcher": "", "hooks": [cmd("anti-rationalization.py"), cmd("evidence-check.py")]},
        ],
    }


def hook_script_name(hook):
    cmd = hook.get("command", "") if isinstance(hook, dict) else ""
    return os.path.basename(cmd.strip().strip('"').split()[-1]) if cmd.strip() else ""


def is_plugin_hook(hook):
    """True when a hook runs one of this plugin's current or retired scripts."""
    return hook_script_name(hook) in PLUGIN_HOOK_SCRIPTS | RETIRED_SCRIPTS


def merge_hooks(existing, ours):
    """Replace this plugin's hooks in `existing`, keep everything else.

    Only hooks whose command runs one of PLUGIN_HOOK_SCRIPTS are removed. A
    project's own hooks survive even when they sit in the same entry or the
    same directory as the plugin's.
    """
    merged = dict(existing or {})
    for event in set(merged) | set(ours):
        kept = []
        for entry in merged.get(event, []) or []:
            remaining = [h for h in entry.get("hooks", []) if not is_plugin_hook(h)]
            if remaining:
                kept.append({**entry, "hooks": remaining})
        merged[event] = kept + ours.get(event, [])
        if not merged[event]:
            del merged[event]
    return merged


try:
    plugin_root = resolve_plugin_root()
    if not plugin_root:
        print(json.dumps({
            "status": "error",
            "error": "Cannot resolve plugin root directory",
            "CLAUDE_PLUGIN_ROOT": os.environ.get("CLAUDE_PLUGIN_ROOT", "(not set)"),
            "hint": "Reinstall the plugin, or run /init from a terminal session",
        }, indent=2))
        sys.exit(1)

    update_mode = "--update" in sys.argv
    project_root = os.getcwd()
    claude_dir = os.path.join(project_root, ".claude")

    plugin_version = "unknown"
    plugin_json_path = os.path.join(plugin_root, ".claude-plugin", "plugin.json")
    if os.path.isfile(plugin_json_path):
        with open(plugin_json_path, "r", encoding="utf-8") as f:
            plugin_version = json.load(f).get("version", "unknown")

    if update_mode and not os.path.isfile(os.path.join(claude_dir, "manifest.json")):
        print(json.dumps({
            "status": "error",
            "error": "No .claude/manifest.json found. Run a full /init first.",
        }, indent=2))
        sys.exit(1)

    # --- 1. Directory tree ---
    dirs = ["skills/" + s for s in GENERATED_SKILLS + BOILERPLATE_SKILLS]
    dirs += ["rules", "patterns", "tasks", "scripts"]
    for d in dirs:
        os.makedirs(os.path.join(claude_dir, d), exist_ok=True)

    # --- 2. Boilerplate skills (identical for every project) ---
    copied_skills = []
    for skill in BOILERPLATE_SKILLS:
        src = os.path.join(plugin_root, "templates", "skills", skill, "SKILL.md")
        dst = os.path.join(claude_dir, "skills", skill, "SKILL.md")
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied_skills.append(f"skills/{skill}/SKILL.md")

    src = os.path.join(plugin_root, "templates", "evolve", "changelog-spec.md")
    dst = os.path.join(claude_dir, "skills", "evolve", "changelog-spec.md")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        copied_skills.append("skills/evolve/changelog-spec.md")

    # --- 3. Hook scripts ---
    copied_scripts = []
    for script in HOOK_SCRIPTS:
        src = os.path.join(plugin_root, "scripts", script)
        dst = os.path.join(claude_dir, "scripts", script)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied_scripts.append(script)
    retired_scripts = []
    for script in sorted(RETIRED_SCRIPTS):
        path = os.path.join(claude_dir, "scripts", script)
        if os.path.isfile(path):
            os.remove(path)
            retired_scripts.append(script)

    # --- 4. Project-local init skill (so /init --update works later) ---
    init_skill_dst = os.path.join(claude_dir, "skills", "init", "SKILL.md")
    instructions_src = os.path.join(plugin_root, "templates", "init", "INSTRUCTIONS.md")
    if os.path.isfile(instructions_src) and (update_mode or not os.path.isfile(init_skill_dst)):
        os.makedirs(os.path.dirname(init_skill_dst), exist_ok=True)
        with open(instructions_src, "r", encoding="utf-8") as f:
            body = f.read()
        frontmatter = (
            "---\n"
            "name: init\n"
            'description: "Analyze this codebase and generate the .claude/ governance layer '
            '(manifest, rules, patterns, skills). Pass --update to refresh scripts and '
            'boilerplate without re-analyzing."\n'
            'argument-hint: "[--update]"\n'
            "user-invocable: true\n"
            'allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]\n'
            "---\n\n"
        )
        with open(init_skill_dst, "w", encoding="utf-8") as f:
            f.write(frontmatter + body + "\n")
        copied_skills.append("skills/init/SKILL.md")

    schema_src = os.path.join(plugin_root, "templates", "init", "manifest.schema.json")
    schema_dst = os.path.join(claude_dir, "skills", "init", "manifest.schema.json")
    if os.path.isfile(schema_src):
        os.makedirs(os.path.dirname(schema_dst), exist_ok=True)
        shutil.copy2(schema_src, schema_dst)

    # --- 5. settings.json: hooks only. Permissions are the project's own business. ---
    settings_path = os.path.join(claude_dir, "settings.json")
    settings = {}
    if os.path.isfile(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f) or {}
        except (OSError, ValueError):
            settings = {}
    settings["hooks"] = merge_hooks(settings.get("hooks"), plugin_hooks(python_command()))
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    copied_skills.append("settings.json (hooks merged)")

    # --- 6. Stub files (full init only, never overwritten) ---
    created_stubs = []
    if not update_mode:
        stubs = {
            "tasks/INDEX.md": (
                "# Task Index\n\n"
                "| Date | Task | Status | Module | Commit |\n"
                "|------|------|--------|--------|--------|\n"
            ),
        }
        for rel, content in stubs.items():
            path = os.path.join(claude_dir, rel)
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                created_stubs.append(rel)

    result = {
        "status": "success",
        "mode": "update" if update_mode else "full",
        "plugin_root": plugin_root,
        "plugin_version": plugin_version,
        "claude_dir": claude_dir,
        "python_command": python_command(),
        "copied_skills": copied_skills,
        "copied_scripts": copied_scripts,
        "retired_scripts": retired_scripts,
        "created_stubs": created_stubs,
        "rule_templates_dir": os.path.join(plugin_root, "rules"),
        "pattern_template": os.path.join(plugin_root, "patterns", "archetype.md"),
        "packs_dir": os.path.join(plugin_root, "packs"),
    }
    if update_mode:
        result["next_steps"] = [
            "Update governance.plugin_version in .claude/manifest.json",
            "Add an [Unreleased] entry to .claude/CHANGELOG.md",
            "Report what was refreshed",
        ]
    else:
        result["remaining_for_agent"] = [
            ".claude/manifest.json: generate from codebase analysis",
            ".claude/CLAUDE.md: generate governance rules from analysis",
            ".claude/CHANGELOG.md: generate the initial version entry",
            ".claude/rules/security.md: hydrate from the plugin's rules/security.md template",
            ".claude/rules/architecture.md: hydrate from the plugin's rules/architecture.md template",
            ".claude/rules/conventions.md: hydrate from the plugin's rules/conventions.md template",
            ".claude/patterns/<archetype>.md: one per sampled archetype, from patterns/archetype.md",
        ] + [f".claude/skills/{s}/SKILL.md: generate project-customized" for s in GENERATED_SKILLS]

    print(json.dumps(result, indent=2))
    sys.exit(0)

except SystemExit:
    raise
except Exception as e:
    print(json.dumps({"status": "error", "error": str(e)}, indent=2))
    sys.exit(1)
