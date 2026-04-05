---
name: init
description: "Generate .claude/ governance layer for this project"
argument-hint: "[--update]"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---

## Setup Required

This plugin needs a one-time setup before /init works. Run this command in your terminal:

```
python "$CLAUDE_PLUGIN_ROOT/scripts/scaffold.py"
```

This creates the `.claude/` directory with all boilerplate files and a project-local `/init` skill. After running it, type `/init` again and it will analyze your codebase and generate the remaining governance files.

If `$CLAUDE_PLUGIN_ROOT` is not set, find the plugin path with:
```
ls ~/.claude/plugins/cache/clauding-thought/
```

For updates after a plugin version bump, run:
```
python "$CLAUDE_PLUGIN_ROOT/scripts/scaffold.py" --update
```

$ARGUMENTS
