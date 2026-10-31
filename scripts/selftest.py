#!/usr/bin/env python3
"""Proves that every governance hook fires, and allows, for the right reasons.

Builds throwaway fixture projects (each with its own .claude/, a copy of the
installed scripts, a settings.json mirroring the project's, a manifest, task
docs, synthetic transcripts with tool_use entries), runs each hook with cwd
inside a fixture, and checks two things per case: the decision the hook
returned, and the decision and reason it logged. An allow row therefore
proves the hook reached the branch it was supposed to reach; under fail-open
a crash would log nothing and the row fails.

Also checks registration: the project's settings run each hook under the
right event with a matcher that covers the tools it needs and an interpreter
that exists on PATH; hooks disabled in the manifest are expected to be
absent; `disableAllHooks` in any settings file is a failure.

Synthetic decisions land in the fixture's hook-log.jsonl, never the real
project's. Payloads are sent as raw UTF-8 bytes, the way Claude Code sends
them, and one fixture lives in a directory with a non-ASCII name.

Usage:
  python selftest.py [--project DIR] [--scripts DIR] [--no-write] [--json]

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
    "secret-filter.py": ("PreToolUse", ("Write", "Edit")),
    "scope-guard.py": ("PreToolUse", ("Write", "Edit")),
    "destructive-guard.py": ("PreToolUse", ("Bash",)),
    "anti-rationalization.py": ("Stop", ()),
    "evidence-check.py": ("Stop", ()),
    "claim-guard.py": ("Stop", ()),
}
HELPERS = ["hook_telemetry", "task_doc", "transcript"]
PYTEST_OK = "========== 12 passed in 0.41s =========="
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--project", default=os.getcwd())
    p.add_argument("--scripts", default=None)
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--json", action="store_true")
    return p.parse_args()


def read_json(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return json.loads(raw.decode("utf-8-sig", "replace"))
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def jsonl(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def prompt(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def use(tid, name, command=None):
    inp = {"command": command} if command is not None else {"file_path": "x"}
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def result(tid, text, as_blocks=False):
    content = [{"type": "text", "text": text}] if as_blocks else text
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": content}]}}


def build_fixture(root, name, scripts_dir, settings, manifest, with_task=True):
    proj = os.path.join(root, name)
    cd = os.path.join(proj, ".claude")
    os.makedirs(os.path.join(cd, "scripts"))
    for sub in ("src/auth", "lib", "docs", "app/Http"):
        os.makedirs(os.path.join(proj, sub), exist_ok=True)
    for fname in os.listdir(scripts_dir):
        if fname.endswith(".py"):
            shutil.copy2(os.path.join(scripts_dir, fname), os.path.join(cd, "scripts", fname))
    with open(os.path.join(cd, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f)
    with open(os.path.join(cd, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    if with_task:
        os.makedirs(os.path.join(cd, "tasks", "2026-01"))
        with open(os.path.join(cd, "tasks", "2026-01", "2026-01-01-fixture.md"), "w", encoding="utf-8") as f:
            f.write("# Fixture task\n\n**Status:** In Progress\n\n## Intent\nx\n\n"
                    "#### Scope (files)\n- `src/**` (all source)\n- app/{Http,Models}/**\n- docs/\n\n## Implementation\n")
    tr = os.path.join(proj, "transcripts")
    os.makedirs(tr)
    jsonl(os.path.join(tr, "ok.jsonl"), [prompt("run tests"), use("t1", "Bash", "pytest -q"), result("t1", PYTEST_OK)])
    jsonl(os.path.join(tr, "stale.jsonl"), [use("t0", "Bash", "pytest -q"), result("t0", PYTEST_OK), prompt("now claim"),
                                            use("t1", "Bash", "ls"), result("t1", "a b", True)])
    jsonl(os.path.join(tr, "partial.jsonl"), [prompt("go"), use("t1", "Bash", "pytest -q"), result("t1", "== 2 failed, 10 passed in 1.2s ==")])
    jsonl(os.path.join(tr, "readfile.jsonl"), [prompt("go"), use("t1", "Read"), result("t1", "PYTEST_OK = '12 passed in 0.41s'")])
    jsonl(os.path.join(tr, "echo.jsonl"), [prompt("go"), use("t1", "Bash", "echo '12 passed in 0.1s'"), result("t1", "12 passed in 0.1s")])
    jsonl(os.path.join(tr, "build.jsonl"), [prompt("go"), use("t1", "Bash", "npm run build"), result("t1", "webpack: Build complete in 3s")])
    jsonl(os.path.join(tr, "silent.jsonl"), [prompt("go"), use("t1", "Bash", "npx tsc --noEmit"), result("t1", "")])
    jsonl(os.path.join(tr, "gate.jsonl"), [prompt("check"), use("t1", "Bash", "make verify"), result("t1", "verifying...\nschema ok\n", True)])
    jsonl(os.path.join(tr, "wrapped.jsonl"), [
        prompt("go"), use("t1", "Bash", "pytest -q"), result("t1", PYTEST_OK),
        {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "<system-reminder>context</system-reminder>"}]}},
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": "Stop hook feedback:\n[python x.py]: do better"}},
        {"type": "user", "isSidechain": True, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t9", "content": "9 passed in 1s"}]}},
        use("t2", "Bash", "ls"), result("t2", "done", True),
    ])
    jsonl(os.path.join(tr, "slash.jsonl"), [
        prompt("go"), use("t1", "Bash", "pytest -q"), result("t1", PYTEST_OK),
        prompt("<command-message>qc</command-message>\n<command-name>/qc</command-name>"),
        use("t2", "Bash", "ls"), result("t2", "done", True),
    ])
    jsonl(os.path.join(tr, "image.jsonl"), [
        prompt("go"), use("t1", "Bash", "pytest -q"), result("t1", PYTEST_OK),
        {"type": "user", "message": {"role": "user", "content": [{"type": "image", "source": {}}, {"type": "text", "text": "and this?"}]}},
        use("t2", "Bash", "ls"), result("t2", "done", True),
    ])
    return proj


# --------------------------------------------------------------------------
# Running hooks
# --------------------------------------------------------------------------

def run_hook(interpreter, proj, script, payload):
    path = os.path.join(proj, ".claude", "scripts", script)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        cp = subprocess.run([interpreter, path], input=data, capture_output=True, cwd=proj, timeout=30, env=ENV)
        return cp.returncode, cp.stdout.decode("utf-8", "replace"), cp.stderr.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as e:
        return -1, "", str(e)


def last_log(proj, hook_name):
    path = os.path.join(proj, ".claude", "hook-log.jsonl")
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
    except OSError:
        return None
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("hook") == hook_name:
            return e
    return None


def judge_output(expect, rc, out, err):
    try:
        out_json = json.loads(out) if out.strip() else None
    except ValueError:
        out_json = None
    if expect == "deny":
        return rc == 0 and bool(out_json) and (out_json.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"
    if expect == "allow":
        return rc == 0 and not out.strip()
    if expect == "feedback":
        return rc == 2 and bool(err.strip())
    if expect == "annotate":
        return rc == 0 and bool(out_json) and bool(out_json.get("systemMessage"))
    if expect == "quiet":
        return rc == 0 and not (out_json and out_json.get("systemMessage"))
    return False


def judge_log(entry, log_decision, log_reason):
    if entry is None:
        return False
    if entry.get("decision") != log_decision:
        return False
    if log_reason and log_reason.lower() not in (entry.get("reason") or "").lower():
        return False
    return True


def cases(fx, fx_notask, fx_block, fx_ascii):
    """(name, fixture, script, payload, expected_output, logged_decision, logged_reason_substring)"""
    def t(fixture, name):
        return os.path.join(fixture, "transcripts", name)

    def w(fixture, rel, tool="Write"):
        p = os.path.join(fixture, *rel.split("/")) if not os.path.isabs(rel) else rel
        ti = {"notebook_path": p, "new_source": "x"} if tool == "NotebookEdit" else {"file_path": p, "content": "x"}
        return {"cwd": fixture, "tool_name": tool, "tool_input": ti}

    def wc(fixture, content, tool="Write"):
        p = os.path.join(fixture, "src", "x.ts")
        if tool == "NotebookEdit":
            ti = {"notebook_path": p, "new_source": content}
        elif tool == "MultiEdit":
            ti = {"file_path": p, "edits": [{"old_string": "a", "new_string": content}]}
        else:
            ti = {"file_path": p, "content": content}
        return {"cwd": fixture, "tool_name": tool, "tool_input": ti}

    def b(fixture, cmd):
        return {"cwd": fixture, "tool_name": "Bash", "tool_input": {"command": cmd}}

    def s(fixture, msg, transcript, active=False):
        return {"cwd": fixture, "stop_hook_active": active, "transcript_path": t(fixture, transcript),
                "last_assistant_message": msg}

    ext_len = "\\\\?\\" + os.path.join(fx, "lib", "x.ts")
    rows = [
        # secret-filter
        ("secret-filter: AWS key", fx, "secret-filter.py", wc(fx, 'KEY="AKIAABCDEFGHIJKLMNOP"'), "deny", "block", "AWS"),
        ("secret-filter: JSON password key", fx, "secret-filter.py", wc(fx, '{"user": "admin", "password": "Sup3rS3cretPassw0rd"}'), "deny", "block", "credential"),
        ("secret-filter: .env password", fx, "secret-filter.py", wc(fx, "DB_PASSWORD=Sup3rS3cretPassw0rd"), "deny", "block", "credential"),
        ("secret-filter: encrypted private key", fx, "secret-filter.py", wc(fx, "-----BEGIN ENCRYPTED PRIVATE KEY-----"), "deny", "block", "private key"),
        ("secret-filter: JWT", fx, "secret-filter.py", wc(fx, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"), "deny", "block", "Web Token"),
        ("secret-filter: NotebookEdit new_source", fx, "secret-filter.py", wc(fx, "token = 'ghp_" + "a" * 36 + "'", "NotebookEdit"), "deny", "block", "GitHub"),
        ("secret-filter: MultiEdit edits[]", fx, "secret-filter.py", wc(fx, "postgres://app:Re4lPr0dPw@db.example.com/x", "MultiEdit"), "deny", "block", "connection"),
        ("secret-filter: clean content", fx, "secret-filter.py", wc(fx, "print(1)"), "allow", "allow", ""),
        ("secret-filter: css class with sk-", fx, "secret-filter.py", wc(fx, '<div className="task-manager-dashboard-view">'), "allow", "allow", ""),
        ("secret-filter: templated connection string", fx, "secret-filter.py", wc(fx, "DATABASE_URL=postgres://app:${DB_PASSWORD}@db:5432/app"), "allow", "allow", ""),
        ("secret-filter: docker-compose default", fx, "secret-filter.py", wc(fx, "postgresql://postgres:postgres@localhost:5432/dev"), "allow", "allow", ""),
        ("secret-filter: test fixture password", fx, "secret-filter.py", wc(fx, 'password = "testpassword"'), "allow", "allow", ""),
        # destructive-guard
        ("destructive-guard: git reset --hard", fx, "destructive-guard.py", b(fx, "git reset --hard HEAD~1"), "deny", "block", "reset"),
        ("destructive-guard: rm -r -f .", fx, "destructive-guard.py", b(fx, "rm -r -f ."), "deny", "block", "rm -rf"),
        ("destructive-guard: rm -rf *", fx, "destructive-guard.py", b(fx, "rm -rf *"), "deny", "block", "rm -rf"),
        ("destructive-guard: compound rm -rf .", fx, "destructive-guard.py", b(fx, "cd build && rm -rf ."), "deny", "block", "rm -rf"),
        ("destructive-guard: xargs rm -rf", fx, "destructive-guard.py", b(fx, "find . -maxdepth 1 | xargs rm -rf"), "deny", "block", "pipe"),
        ("destructive-guard: git push +main", fx, "destructive-guard.py", b(fx, "git push origin +main"), "deny", "block", "protected"),
        ("destructive-guard: git clean -d --force", fx, "destructive-guard.py", b(fx, "git clean -d --force"), "deny", "block", "clean"),
        ("destructive-guard: psql DELETE without WHERE", fx, "destructive-guard.py", b(fx, 'psql -c "DELETE FROM users;"'), "deny", "block", "WHERE"),
        ("destructive-guard: find . -delete", fx, "destructive-guard.py", b(fx, "find . -delete"), "deny", "block", "find"),
        ("destructive-guard: force-with-lease allowed", fx, "destructive-guard.py", b(fx, "git push --force-with-lease origin feature"), "allow", "allow", ""),
        ("destructive-guard: find -name -delete allowed", fx, "destructive-guard.py", b(fx, "find . -name '*.pyc' -delete"), "allow", "allow", ""),
        ("destructive-guard: grep DROP TABLE allowed", fx, "destructive-guard.py", b(fx, "grep -rn 'DROP TABLE' migrations/"), "allow", "allow", ""),
        ("destructive-guard: git clean dry run allowed", fx, "destructive-guard.py", b(fx, "git clean -fdn"), "allow", "allow", ""),
        ("destructive-guard: terraform -var-file allowed", fx, "destructive-guard.py", b(fx, "terraform plan -var-file $VARS"), "allow", "allow", ""),
        ("destructive-guard: pathological token is fast", fx, "destructive-guard.py", b(fx, "rm " + "-rf" * 400), "allow", "allow", ""),
        # scope-guard
        ("scope-guard: in scope via backticked glob", fx, "scope-guard.py", w(fx, "src/auth/x.ts"), "allow", "allow", ""),
        ("scope-guard: in scope via bare directory", fx, "scope-guard.py", w(fx, "docs/a.md"), "allow", "allow", ""),
        ("scope-guard: brace glob", fx, "scope-guard.py", w(fx, "app/Http/C.php"), "allow", "allow", ""),
        ("scope-guard: out of scope", fx, "scope-guard.py", w(fx, "lib/x.ts", "Edit"), "deny", "block", "outside declared scope"),
        ("scope-guard: relative path against hook cwd", fx, "scope-guard.py", {"cwd": fx, "tool_name": "Write", "tool_input": {"file_path": "lib/x.ts", "content": "x"}}, "deny", "block", "outside declared scope"),
        ("scope-guard: dotdot path", fx, "scope-guard.py", w(fx, os.path.join(fx, "src", "..", "lib", "x.ts")), "deny", "block", "outside declared scope"),
        ("scope-guard: extended-length prefix", fx, "scope-guard.py", w(fx, ext_len), "deny", "block", "outside declared scope"),
        ("scope-guard: NotebookEdit path", fx, "scope-guard.py", w(fx, "lib/n.ipynb", "NotebookEdit"), "deny", "block", "outside declared scope"),
        ("scope-guard: governance file not in scope", fx, "scope-guard.py", w(fx, ".claude/rules/x.md"), "deny", "block", "governance"),
        ("scope-guard: hook script not in scope", fx, "scope-guard.py", w(fx, ".claude/scripts/scope-guard.py"), "deny", "block", "governance"),
        ("scope-guard: task doc always allowed", fx, "scope-guard.py", w(fx, ".claude/tasks/note.md"), "allow", "allow", "task doc"),
        ("scope-guard: outside project allowed", fx, "scope-guard.py", w(fx, os.path.join(os.path.dirname(fx), "elsewhere.ts")), "allow", "allow", "outside project"),
        ("scope-guard: no active task", fx_notask, "scope-guard.py", w(fx_notask, "lib/x.ts"), "allow", "allow", "no active task"),
        ("scope-guard: non-ASCII project path", fx_ascii, "scope-guard.py", w(fx_ascii, "lib/x.ts"), "deny", "block", "outside declared scope"),
        # anti-rationalization
        ("anti-rationalization: dismissal", fx, "anti-rationalization.py", s(fx, "That failure is a pre-existing issue unrelated to this task.", "ok.jsonl"), "feedback", "feedback", "dismissal"),
        ("anti-rationalization: unrelated to this task", fx, "anti-rationalization.py", s(fx, "That test failure is unrelated to this task.", "ok.jsonl"), "feedback", "feedback", "dismissal"),
        ("anti-rationalization: vague promise", fx, "anti-rationalization.py", s(fx, "Out of scope, but I'll address it later.", "ok.jsonl"), "feedback", "feedback", "dismissal"),
        ("anti-rationalization: recorded with reference", fx, "anti-rationalization.py", s(fx, "Out of scope for this task; recorded it under Implementation.", "ok.jsonl"), "quiet", "allow", "recorded"),
        ("anti-rationalization: handled now", fx, "anti-rationalization.py", s(fx, "That is a pre-existing issue, and I will fix it now.", "ok.jsonl"), "quiet", "allow", "recorded"),
        ("anti-rationalization: user asked for the scoping", fx, "anti-rationalization.py", s(fx, "As you asked, I kept the CSS changes out of scope.", "ok.jsonl"), "quiet", "allow", "exempt"),
        ("anti-rationalization: programming scope", fx, "anti-rationalization.py", s(fx, "The variable is outside the scope of the closure.", "ok.jsonl"), "quiet", "allow", "exempt"),
        ("anti-rationalization: stop_hook_active", fx, "anti-rationalization.py", s(fx, "out of scope", "ok.jsonl", active=True), "quiet", "allow", "stop_hook_active"),
        ("anti-rationalization: no active task is inert", fx_notask, "anti-rationalization.py", s(fx_notask, "out of scope, left it.", "ok.jsonl"), "quiet", "allow", "no active task"),
        # evidence-check
        ("evidence-check: proof in turn", fx, "evidence-check.py", s(fx, "All tests pass now.", "ok.jsonl"), "quiet", "allow", "evidence in window"),
        ("evidence-check: stale proof", fx, "evidence-check.py", s(fx, "All tests pass now.", "stale.jsonl"), "feedback", "feedback", "without evidence"),
        ("evidence-check: partial failure is not proof", fx, "evidence-check.py", s(fx, "All tests pass now.", "partial.jsonl"), "feedback", "feedback", "without evidence"),
        ("evidence-check: file read is not proof", fx, "evidence-check.py", s(fx, "All tests pass now.", "readfile.jsonl"), "feedback", "feedback", "without evidence"),
        ("evidence-check: echo is not proof", fx, "evidence-check.py", s(fx, "All tests pass now.", "echo.jsonl"), "feedback", "feedback", "without evidence"),
        ("evidence-check: build line is not test proof", fx, "evidence-check.py", s(fx, "All tests pass now.", "build.jsonl"), "feedback", "feedback", "without evidence"),
        ("evidence-check: build claim with build output", fx, "evidence-check.py", s(fx, "The build succeeds.", "build.jsonl"), "quiet", "allow", "evidence in window"),
        ("evidence-check: silent gate", fx, "evidence-check.py", s(fx, "Typecheck is clean.", "silent.jsonl"), "quiet", "allow", "silent"),
        ("evidence-check: manifest gate pattern", fx, "evidence-check.py", s(fx, "All checks pass.", "gate.jsonl"), "quiet", "allow", "gate"),
        ("evidence-check: wrappers, hook feedback, sidechain ignored", fx, "evidence-check.py", s(fx, "Tests are passing.", "wrapped.jsonl"), "quiet", "allow", "evidence in window"),
        ("evidence-check: slash-command prompt is a boundary", fx, "evidence-check.py", s(fx, "Tests are passing.", "slash.jsonl"), "feedback", "feedback", "without evidence"),
        ("evidence-check: image prompt is a boundary", fx, "evidence-check.py", s(fx, "Tests are passing.", "image.jsonl"), "feedback", "feedback", "without evidence"),
        ("evidence-check: inline-code claim counts", fx, "evidence-check.py", s(fx, "Result: `all tests pass`.", "stale.jsonl"), "feedback", "feedback", "without evidence"),
        ("evidence-check: negated is not a claim", fx, "evidence-check.py", s(fx, "I have not verified that the tests pass.", "stale.jsonl"), "quiet", "allow", "negated"),
        ("evidence-check: imperative is not a claim", fx, "evidence-check.py", s(fx, "Make sure the tests pass before merging.", "stale.jsonl"), "quiet", "allow", "negated"),
        ("evidence-check: no claim", fx, "evidence-check.py", s(fx, "Edited the file.", "stale.jsonl"), "quiet", "allow", "no claim"),
        ("evidence-check: stop_hook_active", fx, "evidence-check.py", s(fx, "All tests pass.", "stale.jsonl", active=True), "quiet", "allow", "stop_hook_active"),
        # claim-guard
        ("claim-guard: data claim, no gate", fx, "claim-guard.py", s(fx, "The records are now correct in production.", "ok.jsonl"), "annotate", "annotate", "claim without gate"),
        ("claim-guard: label after the claim does not exempt", fx, "claim-guard.py", s(fx, "The records are now correct. evidence: trust me", "ok.jsonl"), "annotate", "annotate", "claim without gate"),
        ("claim-guard: labelled before", fx, "claim-guard.py", s(fx, "HYPOTHESIS: the records are now correct; falsifier: count differs.", "ok.jsonl"), "quiet", "allow", "labelled"),
        ("claim-guard: code fact is not a data claim", fx, "claim-guard.py", s(fx, "The import path is now correct.", "ok.jsonl"), "quiet", "allow", "no claim"),
        ("claim-guard: negated", fx, "claim-guard.py", s(fx, "I have not confirmed that the data is consistent.", "ok.jsonl"), "quiet", "allow", "negated"),
        ("claim-guard: data gate in window", fx, "claim-guard.py", s(fx, "Verified against the database: the state is consistent.", "gate.jsonl"), "quiet", "allow", "gate in window"),
        ("claim-guard: block mode pushes back", fx_block, "claim-guard.py", s(fx_block, "The data is correct.", "ok.jsonl"), "feedback", "feedback", "claim without gate"),
        ("claim-guard: block mode honours stop_hook_active", fx_block, "claim-guard.py", s(fx_block, "The data is correct.", "ok.jsonl", active=True), "quiet", "allow", "stop_hook_active"),
    ]
    return rows


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

def hook_script_name(hook):
    import re
    import shlex
    cmd = hook.get("command", "") if isinstance(hook, dict) else ""
    if not isinstance(cmd, str) or not cmd.strip():
        return "", ""
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        tokens = cmd.split()
    for tok in tokens:
        t = re.sub(r"^\$\{?CLAUDE_PROJECT_DIR\}?/", "", tok.replace("\\", "/"))
        m = re.search(r"(?:^|/)\.claude/scripts/([^/]+)$", t)
        if m:
            return m.group(1), (tokens[0] if tokens else "")
    return "", ""


def plugin_registrations(settings):
    """script -> list of (event, matcher, interpreter) for the plugin's own hooks."""
    out = {}
    for event, entries in ((settings or {}).get("hooks") or {}).items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for h in entry.get("hooks") or []:
                name, interp = hook_script_name(h)
                if name in HOOK_EVENTS:
                    out.setdefault(name, []).append((event, str(entry.get("matcher", "")), interp))
    return out


def registration_rows(settings, scripts_present, disabled, project):
    rows = []
    if settings is None:
        rows.append(("registration: settings.json present", False, "no .claude/settings.json in project"))
        return rows
    regs = plugin_registrations(settings)
    for script, (event, needs) in HOOK_EVENTS.items():
        hook = script[:-3]
        if hook in disabled:
            ok = script not in regs
            rows.append((f"registration: {hook} disabled in manifest, not registered", ok,
                         "" if ok else "disabled in governance.disabled_hooks but still registered"))
            continue
        if script not in scripts_present:
            rows.append((f"registration: {script} installed", False, "script missing from .claude/scripts"))
            continue
        found = [r for r in regs.get(script, []) if r[0] == event]
        if not found:
            rows.append((f"registration: {script} under {event}", False, f"not registered under {event}"))
            continue
        ev, matcher, interp = found[0]
        if needs and not all(n in matcher for n in needs):
            rows.append((f"registration: {script} matcher covers {'|'.join(needs)}", False, f"matcher is {matcher!r}"))
            continue
        on_path = bool(shutil.which(interp))
        rows.append((f"registration: {script} under {event} via {interp}", on_path,
                     "" if on_path else f"interpreter {interp!r} is not on PATH; the hook cannot launch"))
    for name, path in (("settings.local.json", os.path.join(project, ".claude", "settings.local.json")),
                       ("settings.json", os.path.join(project, ".claude", "settings.json")),
                       ("user settings.json", os.path.join(os.path.expanduser("~"), ".claude", "settings.json"))):
        d = read_json(path)
        if isinstance(d, dict) and d.get("disableAllHooks"):
            rows.append((f"registration: disableAllHooks off in {name}", False, f"{name} sets disableAllHooks: true; no hook will run"))
    return rows


def plugin_interpreter(settings):
    """Interpreter the plugin's own hooks are registered with, or None."""
    for regs in plugin_registrations(settings).values():
        for _event, _matcher, interp in regs:
            if interp:
                return interp
    return None


def helpers_row(interpreter, fixture_scripts):
    code = "import sys; sys.path.insert(0, %r); import %s; print('ok')" % (fixture_scripts, ", ".join(HELPERS))
    try:
        cp = subprocess.run([interpreter, "-B", "-c", code], capture_output=True, text=True, timeout=30, env=ENV)
        ok = cp.returncode == 0 and "ok" in cp.stdout
        return ("helpers importable: " + ", ".join(HELPERS), ok, "" if ok else cp.stderr.strip()[-300:])
    except (OSError, subprocess.SubprocessError) as e:
        return ("helpers importable", False, str(e))


def thesis_row(interpreter, fixture_scripts):
    code = (
        "import sys; sys.path.insert(0, %r); from task_doc import thesis_status as t\n"
        "full = '## Thesis\\n**Claim:** a\\n**Observable:** b\\n**Demonstrated:** 2026-10-30T10:00:00Z via /verify: saw it\\n'\n"
        "typed = '## Thesis\\n**Claim:** a\\n**Observable:** b\\n**Demonstrated:** not yet, planned for 2026-11-02\\n'\n"
        "att = '## Thesis\\n**Claim:** a\\n**Observable:** b\\n**Demonstrated:** 2026-10-30 attested by Sam: on staging\\n'\n"
        "opt = 'no-user-observable-change: true\\n## Intent\\nrefactor\\n'\n"
        "a, b, c, d = t(full), t(typed), t(att), t(opt)\n"
        "assert a['demonstrated'] and not a['attested'], a\n"
        "assert not b['demonstrated'], b\n"
        "assert c['attested'] and not c['demonstrated'], c\n"
        "assert d['opted_out'] and not d['present'], d\n"
        "print('ok')\n"
    ) % fixture_scripts
    try:
        cp = subprocess.run([interpreter, "-B", "-c", code], capture_output=True, text=True, timeout=30, env=ENV)
        ok = cp.returncode == 0 and "ok" in cp.stdout
        return ("task_doc: thesis status (run, typed date, attested, opt-out)", ok, "" if ok else cp.stderr.strip()[-300:])
    except (OSError, subprocess.SubprocessError) as e:
        return ("task_doc: thesis status", False, str(e))


def real_transcript_row(interpreter, fixture_scripts, fixture_path):
    code = (
        "import sys; sys.path.insert(0, %r); import transcript as t\n"
        "es = t._entries(%r) or []\n"
        "kinds = [t.classify(e)[0] for e in es]\n"
        "assert kinds and kinds[0] == 'prompt', 'first entry (slash command) must be the turn boundary'\n"
        "assert kinds.count('prompt') == 1, 'only the slash command is a boundary: %%r' %% kinds.count('prompt')\n"
        "metas = [i for i, e in enumerate(es) if e.get('isMeta')]\n"
        "assert metas and all(kinds[i] is None for i in metas), 'isMeta entries must not be boundaries'\n"
        "rs = t.tool_results(%r, 1, tools=('Bash',))\n"
        "assert rs and all(r['tool'] == 'Bash' for r in rs), 'Bash results expected'\n"
        "assert not any('Stop hook feedback' in r['text'] for r in rs)\n"
        "print('ok')\n"
    ) % (fixture_scripts, fixture_path, fixture_path)
    try:
        cp = subprocess.run([interpreter, "-B", "-c", code], capture_output=True, text=True, timeout=30, env=ENV)
        ok = cp.returncode == 0 and "ok" in cp.stdout
        return ("transcript reader: captured real session fixture", ok, "" if ok else cp.stderr.strip()[-300:])
    except (OSError, subprocess.SubprocessError) as e:
        return ("transcript reader: captured real session fixture", False, str(e))


def complexity_rows(interpreter, fixture):
    script = os.path.join(fixture, ".claude", "scripts", "complexity.py")
    if not os.path.isfile(script):
        return [("complexity: scorer installed", False, "complexity.py missing from .claude/scripts")]
    cases = [
        ("complexity: one file is trivial", ["src/alpha/x.ts"], "trivial"),
        ("complexity: five files is medium", ["src/alpha/%d.ts" % i for i in range(5)], "medium"),
        ("complexity: cross-module plus security surface is high", ["src/alpha/x.ts", "src/beta/y.controller.ts"], "high"),
        ("complexity: absolute paths score the same", [os.path.join(fixture, "src", "alpha", "x.ts"), os.path.join(fixture, "src", "beta", "y.controller.ts")], "high"),
    ]
    rows = []
    for name, files, expect in cases:
        try:
            cp = subprocess.run([interpreter, "-B", script, "--project", fixture, "--files", *files],
                                capture_output=True, text=True, cwd=fixture, timeout=30, env=ENV)
            got = json.loads(cp.stdout).get("tier") if cp.stdout.strip() else None
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            got = str(e)
        ok = got == expect
        rows.append((name, ok, "" if ok else f"expected {expect}, got {got}"))
    return rows


# --------------------------------------------------------------------------

def main():
    args = parse_args()
    project = os.path.abspath(args.project)
    scripts_dir = os.path.abspath(args.scripts) if args.scripts else os.path.join(project, ".claude", "scripts")
    if not os.path.isdir(scripts_dir):
        print(json.dumps({"status": "error", "error": f"no scripts directory at {scripts_dir}"}))
        sys.exit(1)

    settings = read_json(os.path.join(project, ".claude", "settings.json"))
    manifest = read_json(os.path.join(project, ".claude", "manifest.json")) or {}
    disabled = {h for h in ((manifest.get("governance") or {}).get("disabled_hooks") or []) if isinstance(h, str)}
    plugin_version = None
    pj = read_json(os.path.join(os.path.dirname(scripts_dir), ".claude-plugin", "plugin.json"))
    if isinstance(pj, dict):
        plugin_version = pj.get("version")

    registered = plugin_interpreter(settings)
    interpreter = shutil.which(registered) if registered else None
    interpreter_note = ""
    if not interpreter:
        interpreter = sys.executable
        interpreter_note = (f"registered interpreter {registered!r} not on PATH; behavioural rows ran with "
                            f"{os.path.basename(sys.executable)}") if registered else "no plugin hooks registered; behavioural rows ran with the current interpreter"

    base_manifest = {
        "version": "1.1",
        "task_docs": {"directory": "tasks", "headings": {"scope": "Scope", "thesis": "Thesis"}},
        "architecture": {"modules": [{"name": "alpha", "path": "src/alpha"}, {"name": "beta", "path": "src/beta"}]},
        "security": {"posture": "strict", "checks": [{"id": "AUTH-001", "name": "guard", "severity": "error",
                                                       "paths": ["src/**/*.controller.ts"]}]},
        "verification": {
            "test_command": "pytest",
            "gates": [
                {"name": "unit tests", "command": "pytest", "success_pattern": r"\d+ passed in", "kind": "test"},
                {"name": "schema check", "command": "make verify", "success_pattern": "schema ok", "kind": "data"},
                {"name": "typecheck", "command": "npx tsc --noEmit", "success_when_silent": True, "kind": "test"},
            ],
            "claim_guard": "annotate",
            "claim_window_turns": 1,
        },
    }
    block_manifest = json.loads(json.dumps(base_manifest))
    block_manifest["verification"]["claim_guard"] = "block"
    fixture_settings = settings if isinstance(settings, dict) else {"hooks": {}}

    real_transcript = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "transcript.jsonl")
    real_transcript = real_transcript if os.path.isfile(real_transcript) else None

    results = []
    root = tempfile.mkdtemp(prefix="ct-selftest-")
    try:
        fx = build_fixture(root, "withtask", scripts_dir, fixture_settings, base_manifest, True)
        fx_notask = build_fixture(root, "notask", scripts_dir, fixture_settings, base_manifest, False)
        fx_block = build_fixture(root, "blockmode", scripts_dir, fixture_settings, block_manifest, True)
        fx_ascii = build_fixture(root, "Työ-ä", scripts_dir, fixture_settings, base_manifest, True)

        for name, fixture, script, payload, expect, log_decision, log_reason in cases(fx, fx_notask, fx_block, fx_ascii):
            hook = script[:-3]
            if hook in disabled:
                results.append({"name": name, "ok": True, "detail": "skipped: hook disabled in manifest"})
                continue
            if not os.path.isfile(os.path.join(fixture, ".claude", "scripts", script)):
                results.append({"name": name, "ok": False, "detail": "script missing"})
                continue
            rc, out, err = run_hook(interpreter, fixture, script, payload)
            out_ok = judge_output(expect, rc, out, err)
            entry = last_log(fixture, hook)
            log_ok = judge_log(entry, log_decision, log_reason)
            ok = out_ok and log_ok
            detail = ""
            if not ok:
                detail = (f"expected {expect} logged {log_decision}/{log_reason!r}; exit={rc} stdout={out.strip()[:120]!r} "
                          f"stderr={err.strip()[:120]!r} logged={json.dumps({k: entry.get(k) for k in ('decision', 'reason')}) if entry else None}")
            results.append({"name": name, "ok": ok, "detail": detail})

        for name, ok, detail in complexity_rows(interpreter, fx):
            results.append({"name": name, "ok": ok, "detail": detail})

        scripts_present = set(os.listdir(scripts_dir))
        for name, ok, detail in registration_rows(settings, scripts_present, disabled, project):
            results.append({"name": name, "ok": ok, "detail": detail})
        if interpreter_note and registered:
            results.append({"name": "registration: plugin interpreter on PATH", "ok": False, "detail": interpreter_note})

        fixture_scripts = os.path.join(fx, ".claude", "scripts")
        for row in (helpers_row(interpreter, fixture_scripts), thesis_row(interpreter, fixture_scripts)):
            results.append({"name": row[0], "ok": row[1], "detail": row[2]})
        if real_transcript:
            name, ok, detail = real_transcript_row(interpreter, fixture_scripts, real_transcript)
            results.append({"name": name, "ok": ok, "detail": detail})
    finally:
        shutil.rmtree(root, ignore_errors=True)

    passed = sum(1 for r in results if r["ok"])
    report = {
        "status": "pass" if passed == len(results) else "fail",
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "interpreter": registered or os.path.basename(interpreter),
        "interpreter_note": interpreter_note,
        "plugin_version": plugin_version,
        "scripts_dir": scripts_dir,
        "disabled_hooks": sorted(disabled),
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
        print(f"\n{passed}/{len(results)} passed  (interpreter: {report['interpreter']}){'  ' + interpreter_note if interpreter_note else ''}")
    sys.exit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
