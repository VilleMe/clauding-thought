#!/usr/bin/env python3
"""UserPromptSubmit hook — reminds Claude about available governance skills."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from hook_telemetry import TelemetryLogger
    logger = TelemetryLogger("skill-reminder", "UserPromptSubmit", "")
    logger.log("feedback")
    print("Available governance skills: /preflight (gather context before coding), /qc (review changes), /task-doc (track work), /close-task (finalize), /evolve (update governance), /export (export rules to Cursor/Copilot/Windsurf), /report (governance health metrics). Consider whether any should run for this task.", file=sys.stderr)
    sys.exit(2)
except SystemExit:
    raise  # let sys.exit() through
except Exception:
    sys.exit(0)  # fail-open
