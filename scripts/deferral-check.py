#!/usr/bin/env python3
"""Stop hook — validates the deferred-item ledger in the active task doc.

Opt-in per check:
- `governance.enforcement.deferred_format` gates free-text detection + dangling
  reference detection (Checks 1 & 2).
- `governance.enforcement.ledger` gates the cross-task ledger threshold (Check 3).

All checks default off. When a check would have fired but its flag is false,
the hook logs `decision: "skipped"` so the user can audit what is not enforced.
"""
import sys, json, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger
from task_doc import (
    find_claude_dir,
    find_active_task,
    extract_section,
    parse_acceptance_criteria,
    count_open_deferrals,
    task_id_exists,
    get_enforcement_flag,
    strip_fenced_blocks,
    is_task_ready_to_close,
)

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    logger = TelemetryLogger("deferral-check", "Stop")

    claude_dir = find_claude_dir()
    if not claude_dir:
        logger.log("allow")
        sys.exit(0)

    task_path, task_text = find_active_task(claude_dir)
    if not task_text:
        logger.log("allow")
        sys.exit(0)

    deferred_format_on = get_enforcement_flag(claude_dir, "deferred_format")
    ledger_on = get_enforcement_flag(claude_dir, "ledger")

    # --- Check 1 & 2: deferred_format checks ---
    criteria = parse_acceptance_criteria(task_text)

    # Free-text detection: look for "deferred" / "follow-up task" etc. inside
    # an acceptance-criteria checkbox line. Strip fenced blocks so documentation
    # examples are not miscounted.
    freetext_defer_re = re.compile(
        r"(?m)^\s*(?:[-*+]|\d+\.)\s+\[[^\]]*\][^\n]*\b"
        r"(deferred?(?!\s*:)|to\s+be\s+done\s+later|follow[- ]up\s+task|"
        r"left\s+for\s+later|tracked\s+for\s+follow[- ]up)\b",
        re.I,
    )
    section = strip_fenced_blocks(extract_section(task_text, "Acceptance Criteria"))
    freetext_matches = freetext_defer_re.findall(section)

    if freetext_matches:
        context = {"count": len(freetext_matches), "task": os.path.basename(task_path)}
        reason = "Free-text deferral in acceptance criteria"
        if deferred_format_on:
            logger.log("feedback", reason=reason, context=context)
            print(
                f"Found {len(freetext_matches)} free-text deferral(s) in the "
                f"Acceptance Criteria of {os.path.basename(task_path)}. "
                "Deferrals must use the `[deferred:TASK-ID]` checkbox form where "
                "TASK-ID resolves to an entry in tasks/INDEX.md.",
                file=sys.stderr,
            )
            sys.exit(2)
        else:
            logger.log("skipped", reason=reason,
                       context={**context, "flag": "deferred_format"})

    dangling = [
        ref for ref in criteria["deferred"]
        if not task_id_exists(claude_dir, ref)
    ]
    if dangling:
        context = {"dangling": dangling[:5]}
        reason = "Deferred reference does not resolve"
        if deferred_format_on:
            logger.log("feedback", reason=reason, context=context)
            print(
                f"Unresolved deferral reference(s): {', '.join(dangling)}. "
                "Create the follow-up task file under .claude/tasks/ or add the "
                "TASK-ID to tasks/INDEX.md before deferring.",
                file=sys.stderr,
            )
            sys.exit(2)
        else:
            logger.log("skipped", reason=reason,
                       context={**context, "flag": "deferred_format"})

    # --- Check 3: ledger threshold ---
    # Trigger: the active task on disk is "ready to close" — every acceptance
    # criterion is [x] or [deferred:TASK-ID] and there are no invalid markers.
    # This is a file-state signal, not a text-sniff of the response, so
    # incidental mentions of close-task/closed/finalizing in the response do
    # not trigger the check.
    if ledger_on and is_task_ready_to_close(criteria):
        threshold = 3
        try:
            manifest_path = os.path.join(claude_dir, "manifest.json")
            if os.path.isfile(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                threshold = manifest.get("governance", {}).get(
                    "deferred_threshold", 3
                )
        except Exception:
            pass

        # Exclude the active (closing) task's own deferrals from the ledger —
        # a task's own close-out plan should not count against its own close.
        total = count_open_deferrals(claude_dir)
        own = len(criteria["deferred"])
        ledger = max(0, total - own)

        if ledger > threshold:
            logger.log(
                "feedback",
                reason="Deferred-item ledger over threshold",
                context={"ledger": ledger, "own": own, "threshold": threshold},
            )
            print(
                f"The active task is ready to close, but the deferred-item ledger "
                f"is {ledger} (excluding this task's own {own} deferrals), over "
                f"threshold {threshold}. Resolve existing deferrals before closing, "
                "or raise `governance.deferred_threshold` in manifest.json if the "
                "current level is intentional.",
                file=sys.stderr,
            )
            sys.exit(2)

    logger.log("allow")
    sys.exit(0)

except SystemExit:
    raise
except Exception:
    sys.exit(0)  # fail-open
