#!/usr/bin/env python3
"""Stop hook: flags claims about data or state that no executed gate backs up.

Reference it reads: the transcript's tool results in the last N turns
(`verification.claim_window_turns`, default 1), checked against the project's
declared data gates (`verification.gates` with kind "data"). Only tool results
count; a tool input that mentions a check is the model typing the word.

Claims the author already labelled (VERIFIED, HYPOTHESIS, evidence:) are
exempt: that labelling is the behaviour we want. Test and build claims are
evidence-check's job, not this hook's.

Channel: `verification.claim_guard` = "annotate" (default) shows the user a
note via `systemMessage` and lets the turn end; "block" pushes back to the
model with exit 2, once per turn (honours `stop_hook_active`).
Fail-open on any error.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CLAIM_RE = re.compile("|".join([
    r"\bverified\s+(against|on|in|that)\b",
    r"\bconfirmed\s+(that\s+)?(the\s+)?(data|records?|rows?|status(es)?|state|counts?|values?|"
    r"database|db|tables?|production|prod|catalog(ue)?|registry|ledger)\b",
    r"\b(data|records?|rows?|status(es)?|state|counts?|values?|catalog(ue)?|registry|ledger)\s+"
    r"(is|are)\s+(now\s+)?(right|correct|accurate|consistent|in\s+sync|up\s+to\s+date)\b",
    r"\bis\s+now\s+correct\b",
    r"\bmatch(es|ed)?\s+(production|prod|the\s+(database|db|source|expected|spec))\b",
    r"\bworking\s+as\s+designed\b",
    r"\bnothing\s+(is\s+)?wrong\s+with\b",
    r"\bto\s+the\s+digit\b",
]), re.I)

LABELED_RE = re.compile(r"\*\*VERIFIED\b|\bVERIFIED:|\bHYPOTHESIS\b|\(evidence:|\bevidence:", re.I)

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    from hook_telemetry import TelemetryLogger
    from task_doc import find_claude_dir, load_manifest, strip_code_and_quotes, verification
    from transcript import tool_results_in_window

    logger = TelemetryLogger("claim-guard", "Stop", hook_input=data)

    response = data.get("last_assistant_message") or data.get("response") or ""
    if not response:
        logger.log("allow")
        sys.exit(0)

    claude_dir = find_claude_dir(data.get("cwd"))
    ver = verification(load_manifest(claude_dir))
    mode = ver.get("claim_guard") if ver.get("claim_guard") in ("annotate", "block") else "annotate"
    window = ver.get("claim_window_turns") or 1

    if mode == "block" and data.get("stop_hook_active"):
        logger.log("allow", reason="stop_hook_active")
        sys.exit(0)

    text = strip_code_and_quotes(response)
    match = CLAIM_RE.search(text or "")
    if not match:
        logger.log("allow")
        sys.exit(0)

    near = text[max(0, match.start() - 80): match.end() + 80]
    if LABELED_RE.search(near):
        logger.log("allow", reason="labelled claim")
        sys.exit(0)

    gates = [g for g in (ver.get("gates") or [])
             if isinstance(g, dict) and g.get("kind") == "data" and g.get("success_pattern")]

    output = tool_results_in_window(data.get("transcript_path", ""), window)
    if output is None:
        logger.log("allow", reason="transcript unavailable",
                   context={"claim": match.group(0)[:120]})
        sys.exit(0)

    for g in gates:
        try:
            if re.search(g["success_pattern"], output, re.I | re.M):
                logger.log("allow", reason="gate in window",
                           context={"gate": g.get("name", ""), "claim": match.group(0)[:120]})
                sys.exit(0)
        except re.error:
            continue

    snippet = text[max(0, match.start() - 50): match.end() + 50].replace("\n", " ").strip()
    note = (
        f"claim-guard: a data/state claim (\"...{snippet}...\") with no executed gate in the "
        f"last {window} turn(s). Label it HYPOTHESIS with what would falsify it, or run a "
        f"declared data gate first and quote its output."
    )
    if not gates:
        note += (" This project declares no data gates: add the check that would prove this "
                 "claim to manifest.verification.gates with kind \"data\".")

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
except Exception:
    sys.exit(0)  # fail-open
