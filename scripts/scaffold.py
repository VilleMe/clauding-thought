#!/usr/bin/env python3
"""Scaffolds the .claude/ governance directory for a project.

Creates the directory tree, copies the hook scripts, merges the governance
hooks into .claude/settings.json, creates stub files, and runs the hook
self-test. Run by the plugin's init skill (/clauding-thought:init) before the analysis phase.

Usage:
  python scaffold.py [--project DIR]           # Full scaffold for a new project
  python scaffold.py --update [--project DIR]  # Refresh scripts and hooks only

The project is --project, else $CLAUDE_PROJECT_DIR, else the current directory.

Output: JSON with status, paths, what was created, what remains for the agent,
and the self-test summary.
"""
import json
import os
import shutil
import subprocess
import sys

# Scripts copied into <project>/.claude/scripts/: hooks, their helpers, and the
# tool scripts that generated skills call (project skills cannot reach the plugin root).
HOOK_SCRIPTS = [
    "secret-filter.py",
    "destructive-guard.py",
    "scope-guard.py",
    "anti-rationalization.py",
    "evidence-check.py",
    "claim-guard.py",
    "hook_telemetry.py",
    "task_doc.py",
    "transcript.py",
    "complexity.py",
    "report_data.py",  # the generated evolve skill reads telemetry through it
]

# Scripts whose hook registrations this plugin owns (by file name).
PLUGIN_HOOK_SCRIPTS = {
    "secret-filter.py", "destructive-guard.py", "scope-guard.py",
    "anti-rationalization.py", "evidence-check.py", "claim-guard.py",
}

# Scripts earlier plugin versions installed and this version no longer ships.
# Their registrations are removed and the files deleted from .claude/scripts/.
RETIRED_SCRIPTS = {
    "skill-reminder.py", "rule-context.py", "deferral-check.py", "thesis-check.py",
    "setup-user-dir.py",
}

# Plugin-owned skills that earlier versions copied into projects. 3.1 ships
# them as plugin skills (/clauding-thought:init, /clauding-thought:report).
RETIRED_PROJECT_SKILLS = ("init", "report")
PLUGIN_SKILL_MARKER = "Clauding Thought"

GENERATED_SKILLS = ["preflight", "qc", "qc-fix", "evolve", "task-doc", "close-task"]

LLM_JUDGE_MARKER = "[clauding-thought llm-judge]"
LLM_JUDGE_PROMPT = (
    LLM_JUDGE_MARKER + " You are reviewing the final message of a coding-agent turn. "
    "Input: $ARGUMENTS. Answer ok=false only if the message (1) dismisses a problem "
    "it found with phrases like out of scope, pre-existing, acceptable tradeoff, "
    "without committing to fix or track it, or (2) asserts a fact about data, "
    "records, or system state as verified or correct while the message quotes no "
    "command output or query result that shows it. Quoted or fenced text does not "
    "count as the message's own claim. Otherwise ok=true. In reason, quote the "
    "sentence and say what evidence or commitment is missing."
)


def resolve_plugin_root():
    """Priority: CLAUDE_PLUGIN_ROOT > CLAUDE_SKILL_DIR/../.. > this file's location."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if not root or not os.path.isdir(root):
        skill_dir = os.environ.get("CLAUDE_SKILL_DIR", "")
        if skill_dir:
            root = os.path.normpath(os.path.join(skill_dir, "..", ".."))
    if not root or not os.path.isdir(root):
        root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return root if os.path.isdir(os.path.join(root, "scripts")) else ""


def python_command():
    """Interpreter name for hook commands. Windows ships `python`; Unix ships `python3`."""
    return "python" if sys.platform.startswith("win") else "python3"


def plugin_hooks(py, llm_judge=False):
    def cmd(script):
        return {"type": "command", "command": f"{py} .claude/scripts/{script}"}

    stop_hooks = [cmd("anti-rationalization.py"), cmd("evidence-check.py"), cmd("claim-guard.py")]
    if llm_judge:
        stop_hooks.append({"type": "prompt", "prompt": LLM_JUDGE_PROMPT, "timeout": 30})
    return {
        "PreToolUse": [
            {"matcher": "Write|Edit|MultiEdit|NotebookEdit",
             "hooks": [cmd("secret-filter.py"), cmd("scope-guard.py")]},
            {"matcher": "Bash", "hooks": [cmd("destructive-guard.py")]},
        ],
        "Stop": [
            {"matcher": "", "hooks": stop_hooks},
        ],
    }


def hook_script_name(hook):
    cmd = hook.get("command", "") if isinstance(hook, dict) else ""
    return os.path.basename(cmd.strip().strip('"').split()[-1]) if cmd.strip() else ""


def is_plugin_hook(hook):
    """True when a hook runs one of this plugin's current or retired scripts,
    or is the plugin's prompt-type judge."""
    if not isinstance(hook, dict):
        return False
    if hook.get("type") == "prompt":
        return str(hook.get("prompt", "")).startswith(LLM_JUDGE_MARKER)
    return hook_script_name(hook) in PLUGIN_HOOK_SCRIPTS | RETIRED_SCRIPTS


def merge_hooks(existing, ours):
    """Replace this plugin's hooks in `existing`, keep everything else.

    Only hooks the plugin owns are removed. A project's own hooks survive even
    when they sit in the same entry or the same directory as the plugin's.
    Events left empty are dropped.
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


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def task_doc_skill_has_scope(claude_dir, heading):
    """True when the generated task-doc skill mentions the scope section heading."""
    path = os.path.join(claude_dir, "skills", "task-doc", "SKILL.md")
    if not os.path.isfile(path):
        return None  # no skill yet: nothing to check
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    return (f"## {heading}" in text) or (f"`{heading}`" in text)


def run_selftest(plugin_root, project_root):
    script = os.path.join(plugin_root, "scripts", "selftest.py")
    if not os.path.isfile(script):
        return {"status": "missing"}
    try:
        cp = subprocess.run([sys.executable, script, "--project", project_root, "--json"],
                            capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
        report = json.loads(cp.stdout) if cp.stdout.strip() else {}
        failed = [r["name"] for r in report.get("results", []) if not r.get("ok")]
        return {"status": report.get("status", "error"), "passed": report.get("passed"),
                "total": report.get("total"), "failed": failed[:10],
                "result_file": os.path.join(project_root, ".claude", "selftest.json")}
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return {"status": "error", "error": str(e)[:300]}


try:
    plugin_root = resolve_plugin_root()
    if not plugin_root:
        print(json.dumps({
            "status": "error",
            "error": "Cannot resolve the plugin root directory",
            "CLAUDE_PLUGIN_ROOT": os.environ.get("CLAUDE_PLUGIN_ROOT", "(not set)"),
            "hint": "Reinstall the plugin, or run the init skill from an interactive session",
        }, indent=2))
        sys.exit(1)

    update_mode = "--update" in sys.argv
    project_root = None
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        if idx + 1 < len(sys.argv):
            project_root = sys.argv[idx + 1]
    project_root = os.path.abspath(project_root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    claude_dir = os.path.join(project_root, ".claude")

    plugin_version = load_json(os.path.join(plugin_root, ".claude-plugin", "plugin.json")).get("version", "unknown")

    manifest_path = os.path.join(claude_dir, "manifest.json")
    if update_mode and not os.path.isfile(manifest_path):
        print(json.dumps({
            "status": "error",
            "error": "No .claude/manifest.json found. Run a full init first.",
        }, indent=2))
        sys.exit(1)
    manifest = load_json(manifest_path) if os.path.isfile(manifest_path) else {}

    # --- 1. Directory tree ---
    for d in ["skills/" + s for s in GENERATED_SKILLS] + ["agents", "rules", "patterns", "tasks", "scripts"]:
        os.makedirs(os.path.join(claude_dir, d), exist_ok=True)

    # --- 2. Files copied next to generated skills ---
    copied = []
    src = os.path.join(plugin_root, "templates", "evolve", "changelog-spec.md")
    dst = os.path.join(claude_dir, "skills", "evolve", "changelog-spec.md")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        copied.append("skills/evolve/changelog-spec.md")

    # --- 3. Hook scripts ---
    copied_scripts = []
    for script in HOOK_SCRIPTS:
        s = os.path.join(plugin_root, "scripts", script)
        d = os.path.join(claude_dir, "scripts", script)
        if os.path.isfile(s):
            shutil.copy2(s, d)
            copied_scripts.append(script)
    retired_scripts = []
    for script in sorted(RETIRED_SCRIPTS):
        path = os.path.join(claude_dir, "scripts", script)
        if os.path.isfile(path):
            os.remove(path)
            retired_scripts.append(script)

    # --- 4. Retire plugin-owned project skills (now plugin skills) ---
    retired_skills = []
    for name in RETIRED_PROJECT_SKILLS:
        skill_dir = os.path.join(claude_dir, "skills", name)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if os.path.isfile(skill_md):
            try:
                with open(skill_md, "r", encoding="utf-8") as f:
                    owned = PLUGIN_SKILL_MARKER in f.read()
            except OSError:
                owned = False
            if owned:
                shutil.rmtree(skill_dir, ignore_errors=True)
                retired_skills.append(f"skills/{name}")
    for stale in (".plugin-root",):
        path = os.path.join(claude_dir, stale)
        if os.path.isfile(path):
            os.remove(path)

    # --- 5. settings.json: hooks only. Permissions are the project's own business. ---
    settings_path = os.path.join(claude_dir, "settings.json")
    settings = load_json(settings_path) if os.path.isfile(settings_path) else {}
    llm_judge = bool((manifest.get("verification") or {}).get("llm_judge"))
    settings["hooks"] = merge_hooks(settings.get("hooks"), plugin_hooks(python_command(), llm_judge))
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    copied.append("settings.json (hooks merged)")

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

    # --- 7. Does the generated task-doc skill know the scope section? ---
    scope_heading = ((manifest.get("task_docs") or {}).get("headings") or {}).get("scope") or "Scope"
    has_scope = task_doc_skill_has_scope(claude_dir, scope_heading)

    # --- 8. Self-test ---
    selftest = run_selftest(plugin_root, project_root)

    result = {
        "status": "success" if selftest.get("status") in ("pass", "missing") else "warning",
        "mode": "update" if update_mode else "full",
        "project_root": project_root,
        "plugin_root": plugin_root,
        "plugin_version": plugin_version,
        "claude_dir": claude_dir,
        "python_command": python_command(),
        "copied": copied,
        "copied_scripts": copied_scripts,
        "retired_scripts": retired_scripts,
        "retired_project_skills": retired_skills,
        "created_stubs": created_stubs,
        "llm_judge_registered": llm_judge,
        "scope_heading": scope_heading,
        "task_doc_skill_has_scope": has_scope,
        "selftest": selftest,
        "schema": os.path.join(plugin_root, "schema", "manifest.schema.json"),
        "rule_templates_dir": os.path.join(plugin_root, "rules"),
        "pattern_template": os.path.join(plugin_root, "patterns", "archetype.md"),
        "packs_dir": os.path.join(plugin_root, "packs"),
    }
    if update_mode:
        steps = [
            "Update governance.plugin_version in .claude/manifest.json",
            "If verification is missing from the manifest, add it (test_command and a test gate from the project's runner)",
            "Add an [Unreleased] entry to .claude/CHANGELOG.md naming what was refreshed",
            "Report what was refreshed and the self-test summary",
        ]
        if has_scope is False:
            steps.insert(1, f"Regenerate .claude/skills/task-doc/SKILL.md so new task docs carry a `## {scope_heading}` section; preserve the project's other customisations")
        if selftest.get("status") not in ("pass", "missing"):
            steps.insert(0, "STOP: the hook self-test failed; show the failed rows from selftest.json and do not continue until they pass")
        result["next_steps"] = steps
    else:
        result["remaining_for_agent"] = [
            ".claude/manifest.json: generate from codebase analysis (include verification and task_docs.headings)",
            ".claude/CLAUDE.md: generate governance rules from analysis",
            ".claude/CHANGELOG.md: generate the initial version entry",
            ".claude/rules/security.md: hydrate from the plugin's rules/security.md template",
            ".claude/rules/architecture.md: hydrate from the plugin's rules/architecture.md template",
            ".claude/rules/conventions.md: hydrate from the plugin's rules/conventions.md template",
            ".claude/patterns/<archetype>.md: one per sampled archetype, from patterns/archetype.md",
            ".claude/rules/<module>.md: one per module when architecture.modules has more than one entry, scoped with paths:",
            ".claude/agents/qc-reviewer.md: the read-only subagent the qc skill runs in",
        ] + [f".claude/skills/{s}/SKILL.md: generate project-customized" for s in GENERATED_SKILLS]

    print(json.dumps(result, indent=2))
    sys.exit(0)

except SystemExit:
    raise
except Exception as e:
    print(json.dumps({"status": "error", "error": str(e)}, indent=2))
    sys.exit(1)
