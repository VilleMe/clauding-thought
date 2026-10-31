# Clauding Thought — Project Rules

## Overview

Clauding Thought is a Claude Code plugin that generates a project-specific `.claude/` governance layer (manifest, path-scoped rules, patterns, task-loop skills) from a codebase and installs six enforcement hooks that are proven to fire. This repository is the plugin. It must stay generic: it is added to other projects, it never belongs to one.

## Structure

- `.claude-plugin/plugin.json`, `marketplace.json` — plugin manifest and marketplace entry; bump `version` in both on every release
- `skills/init/SKILL.md` — the bootstrap skill, invoked as `/clauding-thought:init`; `skills/report/SKILL.md` — `/clauding-thought:report`. Both run scripts via `${CLAUDE_PLUGIN_ROOT}`
- `scripts/` — Python 3, stdlib only: the six hook scripts, `scaffold.py`, `selftest.py`, `scaffoldtest.py` (scaffold scenarios against throwaway projects, run by developers of this repo, never copied into projects), `report_data.py` and `complexity.py` (both copied into projects, for the evolve and preflight skills), shared helpers `hook_telemetry.py`, `task_doc.py`, `transcript.py`, and `fixtures/transcript.jsonl`
- `templates/evolve/changelog-spec.md` — copied next to the generated evolve skill
- `rules/` — rule templates with `{{placeholder}}` syntax, hydrated by the init skill into `.claude/rules/`
- `patterns/archetype.md` — pattern template, hydrated once per detected archetype
- `packs/` — reusable rule packs (plain Markdown plus `pack.json`)
- `schema/manifest.schema.json` — the manifest schema; the init skill reads it from the plugin root

The plugin ships no SessionStart hook and copies no skills into projects. Generated skills (preflight, qc, qc-fix, evolve, task-doc, close-task) and the `qc-reviewer` subagent are written per project by the init skill. `qc` runs with `context: fork` in that subagent; `qc-fix` orchestrates from the main conversation. Project skills cannot reach `${CLAUDE_PLUGIN_ROOT}`, so any script a generated skill calls must be in the scaffold's copy list.

## Conventions

- **Project-agnostic.** No consumer project's names, paths, identifiers, locales, or stack-specific syntax anywhere in this repo. Templates use neutral vocabulary (handler, entity, migration) and placeholders. Examples in docs use fictional projects. Telemetry numbers from real projects stay out of the README.
- **Native-first.** Before adding a mechanism, check whether rules with `paths:`, auto-memory, skills (`context: fork`, `agent`), hooks (including `prompt` type), plan mode, or the bundled `/code-review`, `/security-review`, `/verify` already cover it.
- **Watchers read a reference the builder did not produce:** the task doc's scope section, the transcript's tool results, a declared gate's output. Never the model's own prose or diff.
- **Prove it fires, and prove why it allowed.** Every hook has cases in `scripts/selftest.py` (deny/allow, push-back/quiet, loop guard, transcript cases, the adversarial inputs that once slipped through), and every row asserts the decision and reason the hook logged, because under fail-open an allow proves nothing on its own. The scaffold runs the self-test last; a hook that does not fire there does not ship. Fixtures are throwaway projects (one with a non-ASCII name) fed raw UTF-8, so synthetic decisions never reach a real `hook-log.jsonl`.
- **Templates:** `{{variable}}`, `{{#if}}`/`{{/if}}`, `{{#each}}`/`{{/each}}`. Only `rules/` and `patterns/` use this syntax. Hydrated output must contain no `{{`: Claude Code auto-loads `.claude/rules/` and literal braces break it.
- **Rule files use native `paths:` frontmatter.** `security.md` has none (always loaded); `architecture.md` and `conventions.md` scope to source globs. Target under 12 KB per file.
- **Skills** are full agent logic in `SKILL.md` with YAML frontmatter and end with `$ARGUMENTS`.
- **Hook contracts** (Claude Code hooks reference):
  - Input is read from stdin as bytes and decoded as UTF-8 (`task_doc.read_hook_input`), never through the console code page. Hooks resolve `.claude/` from the `cwd` field of the input, and `find_claude_dir` stops at a `.git` boundary and never returns `~/.claude`.
  - PreToolUse denies with `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}` on stdout, exit 0. Empty stdout, exit 0 allows.
  - Stop hooks read `last_assistant_message` (not `response`), check `stop_hook_active` first when they push back, push back with exit 2 plus a message on stderr, or annotate with `{"systemMessage": "..."}` and exit 0.
  - Telemetry is imported with a no-op fallback so a broken logger never changes a decision. An unexpected exception in the detection path prints one line to stderr and exits 1: visible and non-blocking, never silent. Every decision is logged with a reason the self-test can assert; logs carry the session id and project-relative path, never file or command contents (`hook_telemetry.mask`).
  - Shell commands are judged on tokenised argv per pipeline piece (`destructive-guard.judge`), never with a regex over the whole string. Evidence comes only from Bash tool results mapped through their `tool_use` (`transcript.tool_results`).
- **Manifest drives the hooks.** `task_docs.headings` names the sections, `verification.gates` names what counts as evidence (`success_pattern`, or `success_when_silent` for tools that print nothing), `verification.claim_guard` picks annotate or block, `governance.disabled_hooks` turns a hook off. Hooks never hard-code a project convention.
- **Scaffold owns `settings.json`.** It reads and validates settings and manifest before any copy, delete or write, and aborts on a file it cannot parse. It backs settings up, merges the plugin's hooks (owned by the script they run from `.claude/scripts/`, scanning every token, plus the prompt judge by its marker), preserves everything else, and retires only scripts and skills whose text shows the plugin wrote them (`PLUGIN_SCRIPT_MARKERS`, `RETIRED_PROJECT_SKILLS`); anything else under a retired name is kept and reported in `left_alone`. Files under `.claude/rules/` are never retired: hydrated rules are extracted from the project and edited by it, so they are project content even when the plugin wrote the first draft. Scaffold behaviour has scenarios in `scripts/scaffoldtest.py`, including a project-authored file under a retired name surviving an update. New hook scripts go into both `HOOK_SCRIPTS` and `PLUGIN_HOOK_SCRIPTS` and get self-test rows with their logged reason. The agent never writes `settings.json`.
- **Schema changes are additive** within a manifest version.

## Key principles

1. **Extract, don't invent.** Rules codify what a project actually does.
2. **Specific over generic.** Every generated rule references the actual codebase.
3. **Fewer, sharper rules.** Ten precise rules beat fifty vague ones.
4. **Supplement Claude Code, don't duplicate it.**
5. **Security is non-negotiable.** Hooks enforce in real time; `/qc` reviews after the fact.
6. **Prove it fires.** A hook or gate that cannot be shown to trigger on realistic input does not ship.
