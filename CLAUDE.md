# Clauding Thought — Project Rules

## Overview

Clauding Thought is a Claude Code plugin that generates a project-specific `.claude/` governance layer (manifest, rules, patterns, skills) from a codebase and installs four enforcement hooks. This repository is the plugin. It must stay generic: it is added to other projects, it never belongs to one.

## Structure

- `.claude-plugin/plugin.json`, `marketplace.json` — plugin manifest and marketplace entry; bump `version` in both on every release
- `hooks/hooks.json` — the plugin's only hook: SessionStart runs `scripts/ensure-init-skill.py`
- `scripts/` — Python 3, stdlib only: hook scripts, `scaffold.py`, `report_data.py`, shared helpers `hook_telemetry.py` and `task_doc.py`
- `templates/init/INSTRUCTIONS.md` — body of the `/init` skill; `templates/init/manifest.schema.json` — bundled schema copy
- `templates/skills/report/SKILL.md` — boilerplate skill copied into projects unchanged
- `templates/evolve/changelog-spec.md` — copied next to the generated evolve skill
- `rules/` — rule templates with `{{placeholder}}` syntax, hydrated by `/init` into `.claude/rules/`
- `patterns/archetype.md` — pattern template, hydrated once per detected archetype
- `packs/` — reusable rule packs (plain Markdown plus `pack.json`)
- `schema/manifest.schema.json` — canonical schema; `templates/init/manifest.schema.json` must be byte-identical

## Conventions

- **Project-agnostic.** No consumer project's names, paths, identifiers, locales, or stack-specific syntax anywhere in this repo. Templates use neutral vocabulary (handler, entity, migration) and placeholders. Examples in docs use fictional projects.
- **Templates:** `{{variable}}`, `{{#if}}`/`{{/if}}`, `{{#each}}`/`{{/each}}`. Only `rules/` and `patterns/` use this syntax. Hydrated output must contain no `{{`: Claude Code auto-loads `.claude/rules/` and literal braces break it.
- **Rule files use native `paths:` frontmatter.** `security.md` has none (always loaded); `architecture.md` and `conventions.md` scope to source globs.
- **Skills** are full agent logic in `SKILL.md` with YAML frontmatter and end with `$ARGUMENTS`. The plugin ships no skills of its own; `/init` is written project-locally by the SessionStart hook.
- **Hook contracts** (Claude Code hooks reference):
  - PreToolUse denies with `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}` on stdout, exit 0. Empty stdout, exit 0 allows.
  - Stop hooks read `last_assistant_message` (not `response`), check `stop_hook_active` first and allow when set, and push back with exit 2 plus a message on stderr.
  - Every hook fails open: parse errors and exceptions exit 0. Every decision is logged through `hook_telemetry.py`.
- **Scaffold owns `settings.json`.** It merges the plugin's hook entries (identified by `.claude/scripts/` in the command) and preserves everything else. The agent never writes `settings.json`.
- **Schema changes are additive** within a manifest version. Both schema copies change together.

## Key principles

1. **Extract, don't invent.** Rules codify what a project actually does.
2. **Specific over generic.** Every generated rule references the actual codebase.
3. **Fewer, sharper rules.** Ten precise rules beat fifty vague ones.
4. **Supplement Claude Code, don't duplicate it.** Before adding a mechanism, check whether rules, memory, skills, permissions, or bundled review skills already cover it.
5. **Security is non-negotiable.** Hooks enforce in real time; `/qc` reviews after the fact.
6. **Prove it fires.** A hook or gate that cannot be shown to trigger on realistic input does not ship.
