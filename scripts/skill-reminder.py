#!/usr/bin/env python3
"""UserPromptSubmit hook — reminds Claude about available governance skills.
Also tracks prompt count and escalates to suggest checkpoints."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from hook_telemetry import TelemetryLogger
    logger = TelemetryLogger("skill-reminder", "UserPromptSubmit", "")

    # --- Checkpoint counter logic ---
    threshold = 30
    escalate = False
    counter_data = {"count": 0, "last_reset": None}

    # Walk up from cwd to find .claude/ directory
    current = os.getcwd()
    claude_dir = None
    for _ in range(10):
        candidate = os.path.join(current, ".claude")
        if os.path.isdir(candidate):
            claude_dir = candidate
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    if claude_dir:
        # Read threshold from manifest
        try:
            manifest_path = os.path.join(claude_dir, "manifest.json")
            if os.path.isfile(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                threshold = manifest.get("task_docs", {}).get("checkpoint_interval", 30)
        except Exception:
            pass

        # Read and increment counter
        counter_path = os.path.join(claude_dir, "checkpoint-counter.json")
        try:
            if os.path.isfile(counter_path):
                with open(counter_path, "r", encoding="utf-8") as f:
                    counter_data = json.load(f)
        except Exception:
            pass

        # Only track/escalate if there's an active task
        has_active_task = False
        try:
            tasks_dir = os.path.join(claude_dir, "tasks")
            if os.path.isdir(tasks_dir):
                for fname in os.listdir(tasks_dir):
                    if fname.endswith(".md") and fname != "INDEX.md":
                        fpath = os.path.join(tasks_dir, fname)
                        with open(fpath, "r", encoding="utf-8") as tf:
                            head = tf.read(512)
                        if "status: open" in head or "status: in_progress" in head:
                            has_active_task = True
                            break
        except Exception:
            pass

        if has_active_task:
            counter_data["count"] = counter_data.get("count", 0) + 1
            if counter_data["count"] >= threshold:
                escalate = True

        # Write updated counter
        try:
            with open(counter_path, "w", encoding="utf-8") as f:
                json.dump(counter_data, f)
        except Exception:
            pass

    # --- Build reminder message ---
    base_msg = (
        "Available governance skills: "
        "/preflight (context before coding), "
        "/qc (review changes), "
        "/qc --checkpoint (mid-phase review + context refresh), "
        "/task-doc (track work), "
        "/close-task (finalize), "
        "/evolve (update governance), "
        "/export (export to Cursor/Copilot/Windsurf), "
        "/report (governance health), "
        "/insights (cross-project patterns), "
        "/critique (adversarial review)."
    )

    if escalate:
        count = counter_data.get("count", 0)
        msg = (
            f">>> CHECKPOINT SUGGESTED: {count} prompts since last checkpoint "
            f"(threshold: {threshold}). Context drift is likely. "
            f"Run `/qc --checkpoint` to refresh active rules and catch issues early. <<<\n\n"
            f"{base_msg}"
        )
    else:
        msg = f"{base_msg} Consider whether any should run for this task."

    logger.log("feedback")
    print(msg, file=sys.stderr)
    sys.exit(2)
except SystemExit:
    raise
except Exception:
    sys.exit(0)  # fail-open
