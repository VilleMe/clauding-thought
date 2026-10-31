#!/usr/bin/env python3
"""Stop hook: refuses "tests pass" / "build succeeds" claims with no evidence.

Reference it reads: the Bash tool results of the last N turns
(`verification.claim_window_turns`, default 1), each judged on its own. A
result is evidence for a test claim when it matches a test-runner success
line with a pass count of at least one and no failure line; for a build
claim when it matches a build-tool success line and no failure line. A gate
declared in `manifest.verification.gates` counts when its `success_pattern`
matches, or, for a gate with `success_when_silent: true`, when the command
that ran starts with the gate's command and printed nothing. File reads,
greps and echoes are never evidence.

Negated, conditional and imperative sentences ("make sure the tests pass",
"I have not verified that the tests pass") are not claims. Claims inside
fenced blocks and blockquotes are ignored; inline code is not stripped.

Pushes back with exit 2 once per turn (honours `stop_hook_active`). An
internal error is reported on stderr with exit 1 (visible, non-blocking).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEST_CLAIM_RE = re.compile(
    r"(?:all\s+)?tests?\s+(?:are\s+|now\s+|all\s+|still\s+)?(?:pass(?:ing|ed|es)?|green|ok|clean)\b"
    r"|(?:test\s+)?suite\s+(?:is\s+)?(?:green|pass(?:es|ing)?|clean)\b"
    r"|\d+\s*/\s*\d+\s+tests?\s+pass"
    r"|tests?\s+(?:are\s+)?green",
    re.I,
)
BUILD_CLAIM_RE = re.compile(
    r"build\s+(?:succeed(?:s|ed)?|pass(?:es|ed)?|is\s+green|completes?\s+(?:cleanly|successfully)|works)"
    r"|everything\s+(?:compiles|builds)"
    r"|compiles?\s+(?:cleanly|successfully|without\s+errors)"
    r"|(?:lint(?:er|ing)?|typecheck|type\s*check|tsc|eslint|ruff|mypy|pyright|flake8|clippy)\s+"
    r"(?:is\s+|are\s+)?(?:clean|pass(?:es|ed)?|green|succeed(?:s|ed)?|happy|reports?\s+no\s+errors)"
    r"|no\s+(?:lint|type|compile|build|typecheck)\s+errors"
    r"|ci\s+(?:is\s+)?green|all\s+checks?\s+pass",
    re.I,
)
# a claim preceded (within a few words) by a negation or condition is not a claim
NEG_RE = re.compile(
    r"\b(?:not|never|haven.t|hasn.t|didn.t|don.t|should|must|make\s+sure|ensure|once|if|before|until|when|"
    r"unless|whether|hope|expect|want|need|assuming|so\s+that)\b\W+(?:[\w'`]+\W+){0,5}$",
    re.I,
)

TEST_OK_RE = re.compile("|".join([
    r"\b[1-9]\d*\s+passed\b",
    r"Tests?:\s*[1-9]\d*\s+passed",
    r"Test Suites?:\s*[1-9]\d*\s+passed",
    r"\b[1-9]\d*\s+passing\b",
    r"OK\s*\([1-9]\d*\s+tests?",
    r"Tests:\s*[1-9]\d*,\s*Assertions:",
    r"PASS\s+Tests\\",
    r"^ok\s+\S+\s+[\d.]+s",
    r"^PASS$",
    r"test result: ok\.\s*[1-9]\d*\s+passed",
    r"\b[1-9]\d*\s+examples?,\s*0\s+failures",
    r"\b[1-9]\d*\s+runs,\s*\d+\s+assertions,\s*0\s+failures",
    r"Tests run:\s*[1-9]\d*,\s*Failures:\s*0,\s*Errors:\s*0",
    r"Passed!\s+-\s+Failed:\s*0",
    r"Test Run Successful",
]), re.I | re.M)
BUILD_OK_RE = re.compile("|".join([
    r"BUILD SUCCESS(?:FUL)?",
    r"Compilation finished successfully",
    r"compiled successfully",
    r"Build (?:complete|succeeded|finished)",
    r"Found 0 errors",
    r"All files pass linting",
    r"All checks passed",
    r"no issues found",
]), re.I | re.M)
FAIL_RE = re.compile("|".join([
    r"\b[1-9]\d*\s+(?:failed|failing|failures?|errors?)\b",
    r"^FAIL\b",
    r"(?<![\w])FAILED\b",
    r"BUILD FAILURE",
    r"Errors:\s*[1-9]",
    r"Failures:\s*[1-9]",
    r"error TS\d+",
    r"Traceback \(most recent call last\)",
    r"exit (?:status|code) [1-9]",
    r"✗|✘",
]), re.I | re.M)


def read_hook_input():
    return json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))


def find_claim(text):
    """(kind, match, skipped) for the first real claim; skipped says why
    phrase-shaped matches were not claims ('negated' / 'no claim')."""
    skipped = "no claim"
    for kind, rx in (("test", TEST_CLAIM_RE), ("build", BUILD_CLAIM_RE)):
        for m in rx.finditer(text):
            before = text[max(0, m.start() - 70): m.start()]
            if NEG_RE.search(before):
                skipped = "negated or conditional"
                continue
            return kind, m, None
    return None, None, skipped


NON_RUNNER_RE = re.compile(r"^\s*(?:echo|printf|cat|grep|rg|ag|head|tail|less|more|type|sed|awk|ls|find)\b", re.I)


def result_is_evidence(result, kind, gates):
    text = result.get("text") or ""
    command = result.get("command") or ""
    if NON_RUNNER_RE.match(command):
        return None  # printing text that looks like a result is not running anything
    if FAIL_RE.search(text):
        return None
    if kind == "test" and TEST_OK_RE.search(text):
        return "test output"
    if kind == "build" and (BUILD_OK_RE.search(text) or TEST_OK_RE.search(text)):
        return "build output"
    for g in gates:
        if not isinstance(g, dict):
            continue
        gkind = g.get("kind") or "test"
        if kind == "test" and gkind != "test":
            continue
        pat = g.get("success_pattern")
        try:
            if pat and re.search(pat, text[-65536:], re.I | re.M):
                return f"gate {g.get('name', '')}".strip()
        except re.error:
            pass
        gcmd = str(g.get("command") or "").strip()
        if g.get("success_when_silent") and gcmd and command.strip().startswith(gcmd) and not text.strip():
            return f"gate {g.get('name', '')} (silent success)".strip()
    return None


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
    from task_doc import find_claude_dir, load_manifest, positive_int, strip_quotes_and_fences, verification
    from transcript import tool_results

    logger = TelemetryLogger("evidence-check", "Stop", hook_input=data)

    if data.get("stop_hook_active"):
        logger.log("allow", reason="stop_hook_active")
        sys.exit(0)

    response = data.get("last_assistant_message") or data.get("response") or ""
    if not isinstance(response, str) or not response:
        logger.log("allow")
        sys.exit(0)

    kind, claim, skipped = find_claim(strip_quotes_and_fences(response) or "")
    if not claim:
        logger.log("allow", reason=skipped)
        sys.exit(0)

    ver = verification(load_manifest(find_claude_dir(data.get("cwd"))))
    window = positive_int(ver.get("claim_window_turns"), 1)
    gates = ver.get("gates") or []

    results = tool_results(data.get("transcript_path", ""), window, tools=("Bash",))
    if results is None:
        logger.log("allow", reason="transcript unavailable", context={"claim": claim.group(0)[:120]})
        sys.exit(0)

    for r in results:
        how = result_is_evidence(r, kind, gates)
        if how:
            logger.log("allow", reason=f"evidence in window: {how}", context={"claim": claim.group(0)[:120]})
            sys.exit(0)

    logger.log("feedback", reason="success claim without evidence",
               context={"claim": claim.group(0)[:120], "kind": kind, "bash_results": len(results)})
    print(
        f"You claimed {'the tests pass' if kind == 'test' else 'the build succeeds'}, but no Bash "
        f"result in the last {window} turn(s) shows a passing {'test run' if kind == 'test' else 'build'} "
        "with no failures. Run the actual command and quote its result before claiming success.",
        file=sys.stderr,
    )
    sys.exit(2)

except SystemExit:
    raise
except Exception as e:
    print(f"evidence-check: internal error ({type(e).__name__}); allowed by default", file=sys.stderr)
    sys.exit(1)
