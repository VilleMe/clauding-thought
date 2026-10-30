#!/usr/bin/env python3
"""Proves that every governance hook fires on realistic input.

Builds throwaway fixture projects (each with its own .claude/ directory, a
copy of the hook scripts, a manifest, a task doc with a scope section, and
synthetic transcripts), runs each hook with cwd inside a fixture, and checks
the decision. Synthetic decisions land in the fixture's hook-log.jsonl, never
the real project's.

Also checks registration: that the project's .claude/settings.json runs each
hook script under the expected event, and that the shared helpers import.

Usage:
  python selftest.py                       # project = cwd, scripts = .claude/scripts
  python selftest.py --project DIR         # another project
  python selftest.py --scripts DIR         # test a scripts directory directly (plugin dev)
  python selftest.py --no-write            # do not write .claude/selftest.json

Exit 0 when every row passes, 1 otherwise. Stdlib only.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HOOK_EVENTS = {
    "secret-filter.py": "PreToolUse",
    "destructive-guard.py": "PreToolUse",
    "scope-guard.py": "PreToolUse",
    "anti-rationalization.py": "Stop",
    "evidence-check.py": "Stop",
    "claim-guard.py": "Stop",
}
HELPERS = ["hook_telemetry", "task_doc", "transcript"]

PYTEST_OK = "============ 12 passed in 0.41s ============"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--project", default=os.getcwd())
    p.add_argument("--scripts", default=None)
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--json", action="store_true", help="print the JSON result instead of the table")
    return p.parse_args()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def jsonl(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def prompt(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def tool_result(text, as_blocks=False):
    content = [{"type": "text", "text": text}] if as_blocks else text
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": content}]}}


def build_fixture(root, name, scripts_dir, settings, manifest, with_task=True):
    proj = os.path.join(root, name)
    cd = os.path.join(proj, ".claude")
    os.makedirs(os.path.join(cd, "scripts"))
    os.makedirs(os.path.join(proj, "src"))
    for fname in os.listdir(scripts_dir):
        if fname.endswith(".py"):
            shutil.copy2(os.path.join(scripts_dir, fname), os.path.join(cd, "scripts", fname))
    with open(os.path.join(cd, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f)
    with open(os.path.join(cd, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    if with_task:
        os.makedirs(os.path.join(cd, "tasks"))
        with open(os.path.join(cd, "tasks", "2026-01-01-fixture.md"), "w", encoding="utf-8") as f:
            f.write("# Fixture task\n\n**Status:** In Progress\n\n## Intent\nx\n\n"
                    "## Scope\n- `src/**`\n- app/{Http,Models}/**\n- docs/*.md\n\n## Implementation\n")
    tr = os.path.join(proj, "transcripts")
    os.makedirs(tr)
    jsonl(os.path.join(tr, "ok.jsonl"), [prompt("run tests"), tool_result(PYTEST_OK)])
    jsonl(os.path.join(tr, "stale.jsonl"), [tool_result(PYTEST_OK), prompt("now claim"), tool_result("ls output", True)])
    jsonl(os.path.join(tr, "gate.jsonl"), [prompt("check"), tool_result("verifying...\nschema ok\n", True)])
    # Non-boundary user entries (a system-reminder wrapper, an isMeta hook-feedback
    # entry, a subagent sidechain) must not end the turn or count as evidence.
    jsonl(os.path.join(tr, "wrapped.jsonl"), [
        prompt("go"), tool_result(PYTEST_OK),
        {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "<system-reminder>context</system-reminder>"}]}},
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": "Stop hook feedback:\n[python x.py]: do better"}},
        {"type": "user", "isSidechain": True, "message": {"role": "user", "content": [{"type": "tool_result", "content": "9 passed in 1s"}]}},
        tool_result("done", True),
    ])
    # A slash-command invocation IS a human turn boundary (shape from a captured session).
    jsonl(os.path.join(tr, "slash.jsonl"), [
        prompt("go"), tool_result(PYTEST_OK),
        prompt("<command-message>qc</command-message>\n<command-name>/qc</command-name>"),
        tool_result("done", True),
    ])
    return proj


# --------------------------------------------------------------------------
# Running hooks
# --------------------------------------------------------------------------

def run_hook(interpreter, proj, script, payload):
    path = os.path.join(proj, ".claude", "scripts", script)
    try:
        cp = subprocess.run([interpreter, path], input=json.dumps(payload), capture_output=True,
                            text=True, cwd=proj, timeout=30, encoding="utf-8", errors="replace")
        return cp.returncode, cp.stdout, cp.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return -1, "", str(e)


def judge(expect, rc, out, err):
    out_json = None
    try:
        out_json = json.loads(out) if out.strip() else None
    except ValueError:
        out_json = None
    if expect == "deny":
        return rc == 0 and bool(out_json) and \
            (out_json.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"
    if expect == "allow":
        return rc == 0 and not out.strip()
    if expect == "feedback":
        return rc == 2 and bool(err.strip())
    if expect == "annotate":
        return rc == 0 and bool(out_json) and bool(out_json.get("systemMessage"))
    if expect == "quiet":
        return rc == 0 and not (out_json and out_json.get("systemMessage"))
    return False


def cases(fx, fx_notask, fx_block, with_real_transcript):
    """(name, fixture, script, payload, expectation)"""
    def t(fixture, name):
        return os.path.join(fixture, "transcripts", name)

    src_file = os.path.join(fx, "src", "a.ts")
    win_file = (fx + "\\src\\b.ts").replace("/", "\\")
    brace_file = os.path.join(fx, "app", "Http", "C.php")
    out_file = os.path.join(fx, "lib", "x.ts")
    claude_file = os.path.join(fx, ".claude", "tasks", "note.md")
    outside_file = os.path.join(os.path.dirname(fx), "elsewhere.ts")
    rows = [
        ("secret-filter: AWS key", fx, "secret-filter.py",
         {"tool_name": "Write", "tool_input": {"file_path": src_file, "content": 'KEY="AKIAABCDEFGHIJKLMNOP"'}}, "deny"),
        ("secret-filter: clean content", fx, "secret-filter.py",
         {"tool_name": "Write", "tool_input": {"file_path": src_file, "content": "print(1)"}}, "allow"),
        ("secret-filter: NotebookEdit new_source", fx, "secret-filter.py",
         {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": src_file, "new_source": "token = 'ghp_" + "a" * 36 + "'"}}, "deny"),
        ("secret-filter: MultiEdit edits[]", fx, "secret-filter.py",
         {"tool_name": "MultiEdit", "tool_input": {"file_path": src_file, "edits": [{"old_string": "x", "new_string": "postgres://u:pw@db/x"}]}}, "deny"),
        ("destructive-guard: git reset --hard", fx, "destructive-guard.py",
         {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}}, "deny"),
        ("destructive-guard: compound rm -rf .", fx, "destructive-guard.py",
         {"tool_name": "Bash", "tool_input": {"command": "cd build && rm -rf ."}}, "deny"),
        ("destructive-guard: harmless", fx, "destructive-guard.py",
         {"tool_name": "Bash", "tool_input": {"command": "git push --force-with-lease origin feature"}}, "allow"),
        ("scope-guard: in scope", fx, "scope-guard.py",
         {"tool_name": "Write", "tool_input": {"file_path": src_file, "content": "x"}}, "allow"),
        ("scope-guard: out of scope", fx, "scope-guard.py",
         {"tool_name": "Edit", "tool_input": {"file_path": out_file, "old_string": "a", "new_string": "b"}}, "deny"),
        ("scope-guard: Windows backslash path", fx, "scope-guard.py",
         {"tool_name": "Write", "tool_input": {"file_path": win_file, "content": "x"}}, "allow"),
        ("scope-guard: brace glob", fx, "scope-guard.py",
         {"tool_name": "Write", "tool_input": {"file_path": brace_file, "content": "x"}}, "allow"),
        ("scope-guard: governance dir always allowed", fx, "scope-guard.py",
         {"tool_name": "Write", "tool_input": {"file_path": claude_file, "content": "x"}}, "allow"),
        ("scope-guard: outside project allowed", fx, "scope-guard.py",
         {"tool_name": "Write", "tool_input": {"file_path": outside_file, "content": "x"}}, "allow"),
        ("scope-guard: no active task", fx_notask, "scope-guard.py",
         {"tool_name": "Write", "tool_input": {"file_path": os.path.join(fx_notask, "lib", "x.ts"), "content": "x"}}, "allow"),
        ("anti-rationalization: dismissal", fx, "anti-rationalization.py",
         {"stop_hook_active": False, "last_assistant_message": "That failure is a pre-existing issue unrelated to this task."}, "feedback"),
        ("anti-rationalization: negated", fx, "anti-rationalization.py",
         {"stop_hook_active": False, "last_assistant_message": "That is a pre-existing issue, and I will fix it next."}, "quiet"),
        ("anti-rationalization: stop_hook_active", fx, "anti-rationalization.py",
         {"stop_hook_active": True, "last_assistant_message": "out of scope"}, "quiet"),
        ("evidence-check: proof in turn", fx, "evidence-check.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "ok.jsonl"), "last_assistant_message": "All tests pass now."}, "quiet"),
        ("evidence-check: stale proof", fx, "evidence-check.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "stale.jsonl"), "last_assistant_message": "All tests pass now."}, "feedback"),
        ("evidence-check: manifest gate pattern", fx, "evidence-check.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "gate.jsonl"), "last_assistant_message": "All checks pass."}, "quiet"),
        ("evidence-check: wrappers, hook feedback, sidechain ignored", fx, "evidence-check.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "wrapped.jsonl"), "last_assistant_message": "Tests are passing."}, "quiet"),
        ("evidence-check: slash-command prompt is a turn boundary", fx, "evidence-check.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "slash.jsonl"), "last_assistant_message": "Tests are passing."}, "feedback"),
        ("evidence-check: no claim", fx, "evidence-check.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "stale.jsonl"), "last_assistant_message": "Edited the file."}, "quiet"),
        ("claim-guard: data claim, no gate", fx, "claim-guard.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "ok.jsonl"), "last_assistant_message": "The records are now correct in production."}, "annotate"),
        ("claim-guard: labelled claim", fx, "claim-guard.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "ok.jsonl"), "last_assistant_message": "HYPOTHESIS: the records are now correct; falsifier: count differs."}, "quiet"),
        ("claim-guard: claim inside a fence", fx, "claim-guard.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "ok.jsonl"), "last_assistant_message": "Example:\n```\nthe data is correct\n```\nDone."}, "quiet"),
        ("claim-guard: data gate in window", fx, "claim-guard.py",
         {"stop_hook_active": False, "transcript_path": t(fx, "gate.jsonl"), "last_assistant_message": "Verified against the database: the state is consistent."}, "quiet"),
        ("claim-guard: block mode pushes back", fx_block, "claim-guard.py",
         {"stop_hook_active": False, "transcript_path": t(fx_block, "ok.jsonl"), "last_assistant_message": "The data is correct."}, "feedback"),
        ("claim-guard: block mode honours stop_hook_active", fx_block, "claim-guard.py",
         {"stop_hook_active": True, "transcript_path": t(fx_block, "ok.jsonl"), "last_assistant_message": "The data is correct."}, "quiet"),
    ]
    return rows


def real_transcript_row(interpreter, scripts_dir, fixture_path):
    """The reader must find a human prompt boundary and tool results in a transcript
    captured from a real Claude Code session, not only in hand-written ones."""
    code = (
        "import sys; sys.path.insert(0, %r); import transcript as t\n"
        "es = t._entries(%r) or []\n"
        "kinds = [t.classify(e)[0] for e in es]\n"
        "out = t.tool_results_in_window(%r, 1)\n"
        "assert 'prompt' in kinds, 'no human prompt boundary found'\n"
        "assert 'tool_result' in kinds, 'no tool results found'\n"
        "assert isinstance(out, str) and out.strip(), 'reader returned no text for the last turn'\n"
        "print('ok')\n"
    ) % (scripts_dir, fixture_path, fixture_path)
    try:
        cp = subprocess.run([interpreter, "-c", code], capture_output=True, text=True, timeout=30)
        ok = cp.returncode == 0 and "ok" in cp.stdout
        return ("transcript reader: captured real session fixture", ok, "" if ok else cp.stderr.strip()[-300:])
    except (OSError, subprocess.SubprocessError) as e:
        return ("transcript reader: captured real session fixture", False, str(e))


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

def read_settings(project):
    path = os.path.join(project, ".claude", "settings.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def interpreter_from(settings):
    try:
        for entries in (settings or {}).get("hooks", {}).values():
            for entry in entries:
                for h in entry.get("hooks", []):
                    cmd = (h.get("command") or "").strip()
                    if ".claude/scripts/" in cmd and cmd:
                        name = cmd.split()[0]
                        found = shutil.which(name)
                        if found:
                            return found, name
    except Exception:
        pass
    return sys.executable, os.path.basename(sys.executable)


def registration_rows(settings, scripts_present):
    rows = []
    if settings is None:
        rows.append(("registration: settings.json present", False, "no .claude/settings.json in project"))
        return rows
    hooks = settings.get("hooks", {}) or {}
    for script, event in HOOK_EVENTS.items():
        if script not in scripts_present:
            rows.append((f"registration: {script} installed", False, "script missing from .claude/scripts"))
            continue
        found = False
        for entry in hooks.get(event, []) or []:
            for h in entry.get("hooks", []):
                cmd = h.get("command") or ""
                if cmd.rstrip('"').strip().endswith(script) or script in cmd:
                    found = True
        rows.append((f"registration: {script} under {event}", found, "" if found else f"not registered under {event}"))
    return rows


def helpers_row(interpreter, scripts_dir):
    code = "import sys; sys.path.insert(0, %r); import %s" % (scripts_dir, ", ".join(HELPERS))
    try:
        cp = subprocess.run([interpreter, "-c", code], capture_output=True, text=True, timeout=30)
        ok = cp.returncode == 0
        return ("helpers importable: " + ", ".join(HELPERS), ok, "" if ok else cp.stderr.strip()[-300:])
    except (OSError, subprocess.SubprocessError) as e:
        return ("helpers importable", False, str(e))


# --------------------------------------------------------------------------

def main():
    args = parse_args()
    project = os.path.abspath(args.project)
    scripts_dir = os.path.abspath(args.scripts) if args.scripts else os.path.join(project, ".claude", "scripts")
    if not os.path.isdir(scripts_dir):
        print(json.dumps({"status": "error", "error": f"no scripts directory at {scripts_dir}"}))
        sys.exit(1)

    settings = read_settings(project)
    interpreter, interpreter_name = interpreter_from(settings)
    fixture_settings = settings or {"hooks": {}}
    base_manifest = {
        "version": "1.1",
        "task_docs": {"directory": "tasks", "headings": {"scope": "Scope", "thesis": "Thesis"}},
        "verification": {
            "test_command": "pytest",
            "gates": [
                {"name": "unit tests", "command": "pytest", "success_pattern": r"\d+ passed in", "kind": "test"},
                {"name": "schema check", "command": "make verify", "success_pattern": "schema ok", "kind": "data"},
            ],
            "claim_guard": "annotate",
            "claim_window_turns": 1,
        },
    }
    block_manifest = json.loads(json.dumps(base_manifest))
    block_manifest["verification"]["claim_guard"] = "block"

    # The captured-session fixture ships with the plugin next to this script,
    # not with the copies of the hook scripts in a project.
    real_transcript = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "transcript.jsonl")
    real_transcript = real_transcript if os.path.isfile(real_transcript) else None

    results = []
    root = tempfile.mkdtemp(prefix="ct-selftest-")
    try:
        fx = build_fixture(root, "withtask", scripts_dir, fixture_settings, base_manifest, with_task=True)
        fx_notask = build_fixture(root, "notask", scripts_dir, fixture_settings, base_manifest, with_task=False)
        fx_block = build_fixture(root, "blockmode", scripts_dir, fixture_settings, block_manifest, with_task=True)

        for name, fixture, script, payload, expect in cases(fx, fx_notask, fx_block, real_transcript):
            if not os.path.isfile(os.path.join(fixture, ".claude", "scripts", script)):
                results.append({"name": name, "ok": False, "detail": "script missing"})
                continue
            rc, out, err = run_hook(interpreter, fixture, script, payload)
            ok = judge(expect, rc, out, err)
            detail = "" if ok else f"expected {expect}; exit={rc} stdout={out.strip()[:160]!r} stderr={err.strip()[:160]!r}"
            results.append({"name": name, "ok": ok, "detail": detail})

        scripts_present = set(os.listdir(scripts_dir))
        for name, ok, detail in registration_rows(settings, scripts_present):
            results.append({"name": name, "ok": ok, "detail": detail})
        name, ok, detail = helpers_row(interpreter, scripts_dir)
        results.append({"name": name, "ok": ok, "detail": detail})
        if real_transcript:
            name, ok, detail = real_transcript_row(interpreter, scripts_dir, real_transcript)
            results.append({"name": name, "ok": ok, "detail": detail})
    finally:
        shutil.rmtree(root, ignore_errors=True)

    passed = sum(1 for r in results if r["ok"])
    report = {
        "status": "pass" if passed == len(results) else "fail",
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "interpreter": interpreter_name,
        "scripts_dir": scripts_dir,
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    if not args.no_write and os.path.isdir(os.path.join(project, ".claude")):
        try:
            with open(os.path.join(project, ".claude", "selftest.json"), "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        except OSError:
            pass

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        width = max(len(r["name"]) for r in results)
        for r in results:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']:<{width}}  {r['detail']}")
        print(f"\n{passed}/{len(results)} passed  (interpreter: {interpreter_name})")
    sys.exit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
