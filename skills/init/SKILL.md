---
name: init
description: "Generate .claude/ governance layer for this project"
argument-hint: "[--update]"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---

Do these two steps in order. Do not do anything else first.

Step 1. Run the scaffold script. If the argument is --update, add --update to the command:

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/scaffold.py"
```

Step 2. The scaffold output JSON contains a `plugin_root` field. Read the instructions file and follow it:

Read the file at: `<plugin_root>/skills/init/INSTRUCTIONS.md`

$ARGUMENTS
