#!/usr/bin/env python3
"""Stop hook — verifies the Thesis Demo section on a ready-to-close task.

Opt-in via `governance.enforcement.thesis_demo`. When the flag is true and
the active task doc is ready to close (all acceptance criteria are [x] or
[deferred:...] — see is_task_ready_to_close), the hook requires:

  1. A `## Thesis Demo` section is present, OR the task carries an opt-out
     marker (`no-user-observable-change: true` / `## No User-Observable Change`).
  2. The section has Claim, Script, Observable subsections.
  3. The section has a `**Demonstrated:**` timestamp within the last 24 hours.

When the flag is off and the section would have failed, the hook logs
`decision: "skipped"` so the user can audit what is not enforced.
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_telemetry import TelemetryLogger
from task_doc import (
    find_claude_dir,
    find_active_task,
    parse_acceptance_criteria,
    is_task_ready_to_close,
    validate_thesis_demo,
    has_opt_out_marker,
    get_enforcement_flag,
)

try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

try:
    logger = TelemetryLogger("thesis-check", "Stop")

    claude_dir = find_claude_dir()
    if not claude_dir:
        logger.log("allow")
        sys.exit(0)

    task_path, task_text = find_active_task(claude_dir)
    if not task_text:
        logger.log("allow")
        sys.exit(0)

    criteria = parse_acceptance_criteria(task_text)
    if not is_task_ready_to_close(criteria):
        # Task isn't trying to close. Nothing to check yet.
        logger.log("allow")
        sys.exit(0)

    if has_opt_out_marker(task_text):
        logger.log("allow", reason="Task opted out (no-user-observable-change)")
        sys.exit(0)

    thesis = validate_thesis_demo(task_text)
    missing = []
    if not thesis["present"]:
        missing.append("section absent")
    else:
        if not thesis["has_claim"]:
            missing.append("Claim subsection")
        if not thesis["has_script"]:
            missing.append("Script subsection")
        if not thesis["has_observable"]:
            missing.append("Observable subsection")
        if thesis["demonstrated_ts"] is None:
            missing.append("Demonstrated timestamp")
        elif not thesis["fresh"]:
            age = thesis["demonstrated_ts"].isoformat()
            missing.append(f"fresh demonstration (last recorded {age})")

    if not missing:
        logger.log("allow")
        sys.exit(0)

    flag_on = get_enforcement_flag(claude_dir, "thesis_demo")
    reason = "Thesis Demo missing or stale"
    context = {
        "task": os.path.basename(task_path),
        "missing": missing,
    }

    if flag_on:
        logger.log("feedback", reason=reason, context=context)
        print(
            f"The active task ({os.path.basename(task_path)}) is ready to close "
            f"but the Thesis Demo is incomplete: {', '.join(missing)}.\n\n"
            "Run `/thesis` to draft or refresh the section, then execute the "
            "Script and record the `**Demonstrated:**` timestamp. If this task "
            "has no user-visible change, add `no-user-observable-change: true` "
            "to the task doc frontmatter to opt out.",
            file=sys.stderr,
        )
        sys.exit(2)
    else:
        logger.log("skipped", reason=reason,
                   context={**context, "flag": "thesis_demo"})

    sys.exit(0)

except SystemExit:
    raise
except Exception:
    sys.exit(0)  # fail-open
