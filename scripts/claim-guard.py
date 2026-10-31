#!/usr/bin/env python3
"""Stop hook: flags claims about data or state that no executed gate backs up.

Reference it reads: the Bash tool results of the last N turns
(`verification.claim_window_turns`, default 1), checked against the project's
declared data gates (`verification.gates` with kind "data"). Only Bash results
count; a Read of a file or a tool input that mentions a check is not evidence.

A claim is about data or state when it names one: records, rows, counts,
status, balances, production, the database. Statements about code
("the import path is correct", "it compiles") are not this hook's business.
A label placed before the claim on its line (VERIFIED, HYPOTHESIS,
evidence:) exempts it; that labelling is the behaviour we want. Negated and
conditional sentences are not claims.

Channel: `verification.claim_guard` = "annotate" (default) shows the user a
note via `systemMessage` and lets the turn end; "block" pushes back to the
model with exit 2, once per turn (honours `stop_hook_active`). An internal
error is reported on stderr with exit 1 (visible, non-blocking).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

NOUNS = (r"(?:data|records?|rows?|entries|status(?:es)?|state|counts?|totals?|balances?|values?|numbers?|"
         r"figures?|database|db|tables?|production|prod|catalog(?:ue)?|registry|ledger|inventory|index|cache)")
CLAIM_RE = re.compile(
    rf"\b(?:verified|confirmed|checked|validated)\s+(?:that\s+)?(?:the\s+|all\s+|every\s+)?{NOUNS}\b"
    rf"|\b{NOUNS}\s+(?:is|are|was|were)\s+(?:now\s+|all\s+)?(?:right|correct|accurate|consistent|in\s+sync|"
    r"up\s+to\s+date|intact|valid|healthy)\b"
    r"|\bmatch(?:es|ed)?\s+(?:production|prod|the\s+(?:database|db|source|expected|spec|ledger))\b"
    r"|\bto\s+the\s+digit\b",
    re.I,
)
# Labels are upper-case words or `evidence:`; the ordinary word "verified" is not a label.
LABEL_RE = re.compile(r"\*{0,2}(?:VERIFIED|HYPOTHESIS|UNVERIFIED|ASSUMPTION)\b|\b[Ee]vidence:")
NEG_RE = re.compile(
    r"\b(?:not|never|haven.t|hasn.t|didn.t|should|must|make\s+sure|ensure|once|if|before|until|when|"
    r"unless|whether|need|assuming)\b\W+(?:[\w'`]+\W+){0,5}$",
    re.I,
)
FAIL_RE = re.compile(r"\b[1-9]\d*\s+(?:failed|failing|failures?|errors?)\b|^FAIL\b|Traceback \(most recent", re.I | re.M)


def read_hook_input():
    return json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))


def find_claim(text):
    """(match, skipped): the first unlabelled, non-negated data claim, or why none counted."""
    skipped = "no claim"
    for m in CLAIM_RE.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if LABEL_RE.search(text[line_start: m.start()]):
            skipped = "labelled claim"
            continue  # labelled: the desired behaviour
        if NEG_RE.search(text[max(0, m.start() - 70): m.start()]):
            skipped = "negated or conditional"
            continue
        return m, None
    return None, skipped


NON_RUNNER_RE = re.compile(r"^\s*(?:echo|printf|cat|grep|rg|ag|head|tail|less|more|type|sed|awk|ls|find)\b", re.I)


def gate_hit(results, gates):
    for r in results:
        text = r.get("text") or ""
        if NON_RUNNER_RE.match(r.get("command") or "") or FAIL_RE.search(text):
            continue
        for g in gates:
            pat = g.get("success_pattern")
            try:
                if pat and re.search(pat, text[-65536:], re.I | re.M):
                    return g.get("name", "gate")
            except re.error:
                continue
            gcmd = str(g.get("command") or "").strip()
            if g.get("success_when_silent") and gcmd and (r.get("command") or "").strip().startswith(gcmd) \
                    and not text.strip():
                return g.get("name", "gate")
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

    logger = TelemetryLogger("claim-guard", "Stop", hook_input=data)

    response = data.get("last_assistant_message") or data.get("response") or ""
    if not isinstance(response, str) or not response:
        logger.log("allow")
        sys.exit(0)

    ver = verification(load_manifest(find_claude_dir(data.get("cwd"))))
    mode = ver.get("claim_guard") if ver.get("claim_guard") in ("annotate", "block") else "annotate"
    window = positive_int(ver.get("claim_window_turns"), 1)

    if mode == "block" and data.get("stop_hook_active"):
        logger.log("allow", reason="stop_hook_active")
        sys.exit(0)

    text = strip_quotes_and_fences(response) or ""
    match, skipped = find_claim(text)
    if not match:
        logger.log("allow", reason=skipped)
        sys.exit(0)

    gates = [g for g in (ver.get("gates") or []) if isinstance(g, dict) and g.get("kind") == "data"]
    results = tool_results(data.get("transcript_path", ""), window, tools=("Bash",))
    if results is None:
        logger.log("allow", reason="transcript unavailable", context={"claim": match.group(0)[:120]})
        sys.exit(0)

    hit = gate_hit(results, gates)
    if hit:
        logger.log("allow", reason="gate in window", context={"gate": hit, "claim": match.group(0)[:120]})
        sys.exit(0)

    snippet = text[max(0, match.start() - 50): match.end() + 50].replace("\n", " ").strip()
    note = (
        f"claim-guard: a data/state claim (\"...{snippet}...\") with no executed data gate in the "
        f"last {window} turn(s). Label it HYPOTHESIS with what would falsify it, or run a declared "
        "data gate first and quote its output."
    )
    if not gates:
        note += (" This project declares no data gates: add the check that would prove this claim to "
                 "manifest.verification.gates with kind \"data\".")
    context = {"claim": match.group(0)[:120], "mode": mode, "data_gates": len(gates)}
    if mode == "block":
        logger.log("feedback", reason="claim without gate", context=context)
        print(note, file=sys.stderr)
        sys.exit(2)
    logger.log("annotate", reason="claim without gate", context=context)
    print(json.dumps({"systemMessage": note}))
    sys.exit(0)

except SystemExit:
    raise
except Exception as e:
    print(f"claim-guard: internal error ({type(e).__name__}); allowed by default", file=sys.stderr)
    sys.exit(1)
