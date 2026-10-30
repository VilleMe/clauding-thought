# Clauding Thought — Project Rules

## Overview

Clauding Thought is a Claude Code plugin that generates a project-specific `.claude/` governance layer (manifest, path-scoped rules, patterns, task-loop skills) from a codebase and installs six enforcement hooks that are proven to fire. This repository is the plugin. It must stay generic: it is added to other projects, it never belongs to one.

## Structure

- `.claude-plugin/plugin.json`, `marketplace.json` — plugin manifest and marketplace entry; bump `version` in both on every release
- `skills/init/SKILL.md` — the bootstrap skill, invoked as `/clauding-thought:init`; `skills/report/SKILL.md` — `/clauding-thought:report`. Both run scripts via `${CLAUDE_PLUGIN_ROOT}`
- `scripts/` — Python 3, stdlib only: the six hook scripts, `scaffold.py`, `selftest.py`, `report_data.py`, shared helpers `hook_telemetry.py`, `task_doc.py`, `transcript.py`
- `templates/evolve/changelog-spec.md` — copied next to the generated evolve skill
- `rules/` — rule templates with `{{placeholder}}` syntax, hydrated by the init skill into `.claude/rules/`
- `patterns/archetype.md` — pattern template, hydrated once per detected archetype
- `packs/` — reusable rule packs (plain Markdown plus `pack.json`)
- `schema/manifest.schema.json` — the manifest schema; the init skill reads it from the plugin root

The plugin ships no SessionStart hook and copies no skills into projects. Generated skills (preflight, qc, evolve, task-doc, close-task) are written per project by the init skill.

## Conventions

- **Project-agnostic.** No consumer project's names, paths, identifiers, locales, or stack-specific syntax anywhere in this repo. Templates use neutral vocabulary (handler, entity, migration) and placeholders. Examples in docs use fictional projects. Telemetry numbers from real projects stay out of the README.
- **Native-first.** Before adding a mechanism, check whether rules with `paths:`, auto-memory, skills (`context: fork`, `agent`), hooks (including `prompt` type), plan mode, or the bundled `/code-review`, `/security-review`, `/verify` already cover it.
- **Watchers read a reference the builder did not produce:** the task doc's scope section, the transcript's tool results, a declared gate's output. Never the model's own prose or diff.
- **Prove it fires.** Every hook has cases in `scripts/selftest.py` (deny/allow, push-back/quiet, loop guard, transcript cases). The scaffold runs the self-test last; a hook that does not fire there does not ship. The self-test runs hooks inside throwaway fixture projects so synthetic decisions never reach a real `hook-log.jsonl`.
- **Templates:** `{{variable}}`, `{{#if}}`/`{{/if}}`, `{{#each}}`/`{{/each}}`. Only `rules/` and `patterns/` use this syntax. Hydrated output must contain no `{{`: Claude Code auto-loads `.claude/rules/` and literal braces break it.
- **Rule files use native `paths:` frontmatter.** `security.md` has none (always loaded); `architecture.md` and `conventions.md` scope to source globs. Target under 12 KB per file.
- **Skills** are full agent logic in `SKILL.md` with YAML frontmatter and end with `$ARGUMENTS`.
- **Hook contracts** (Claude Code hooks reference):
  - PreToolUse denies with `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}` on stdout, exit 0. Empty stdout, exit 0 allows.
  - Stop hooks read `last_assistant_message` (not `response`), check `stop_hook_active` first when they push back, push back with exit 2 plus a message on stderr, or annotate with `{"systemMessage": "..."}` and exit 0.
  - Imports live inside the fail-open `try`, so a missing helper exits 0 (logged), never 1. Every decision is logged through `hook_telemetry.py` with the session id and, for file tools, the project-relative path.
- **Manifest drives the hooks.** `task_docs.headings` names the sections, `verification.gates` names what counts as evidence, `verification.claim_guard` picks annotate or block. Hooks never hard-code a project convention.
- **Scaffold owns `settings.json`.** It merges the plugin's hooks (identified by script file name, plus the prompt judge by its marker), preserves everything else, retires hooks and scripts listed in `RETIRED_SCRIPTS`, and removes plugin-owned project skills listed in `RETIRED_PROJECT_SKILLS`. New hook scripts go into both `HOOK_SCRIPTS` and `PLUGIN_HOOK_SCRIPTS` and get self-test cases. The agent never writes `settings.json`.
- **Schema changes are additive** within a manifest version.

## Key principles

1. **Extract, don't invent.** Rules codify what a project actually does.
2. **Specific over generic.** Every generated rule references the actual codebase.
3. **Fewer, sharper rules.** Ten precise rules beat fifty vague ones.
4. **Supplement Claude Code, don't duplicate it.**
5. **Security is non-negotiable.** Hooks enforce in real time; `/qc` reviews after the fact.
6. **Prove it fires.** A hook or gate that cannot be shown to trigger on realistic input does not ship.
