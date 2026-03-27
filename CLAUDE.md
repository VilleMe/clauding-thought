# Clauding Thought -- Project Rules

## Overview

Clauding Thought is an AI code governance framework distributed as a Claude Agent SDK plugin.
It analyzes codebases and generates project-specific `.claude/` governance directories with
rules, patterns, security checks, and agent skills.

## Structure

- `skills/` -- Each subdirectory is a skill with SKILL.md as entrypoint and optional supporting files
- `hooks/hooks.json` -- Hook definitions for security enforcement and workflow automation
- `scripts/` -- Hook implementation scripts (Python 3)
- `rules/` -- Rule file templates with `{{placeholder}}` syntax (hydrated by /init)
- `patterns/` -- Pattern file templates with `{{placeholder}}` syntax (hydrated by /init)
- `packs/` -- Community rule packs with reusable security/convention rules
- `schema/` -- JSON Schema for manifest.json (canonical copy)
- `.claude-plugin/plugin.json` -- Plugin manifest

## Conventions

- Skills contain full agent logic in SKILL.md (no thin wrappers referencing separate specs)
- SKILL.md files use YAML frontmatter (name, description, argument-hint, allowed-tools, etc.)
- Template placeholders use `{{variable}}` syntax
- Template conditionals use `{{#if}}` / `{{/if}}`
- Template loops use `{{#each}}` / `{{/each}}`
- The manifest schema is the contract -- skills and templates must stay in sync with it
- All schema changes must be backwards-compatible (add fields, don't remove)
- Hook scripts exit 0 with JSON `{"decision":"block","reason":"..."}` on stdout to deny, exit 0 with empty stdout to allow, exit 2 with stderr feedback for non-blocking messages
- SKILL.md files end with `$ARGUMENTS` — this is replaced by the Claude Agent SDK with the user's invocation arguments at runtime

## Key Principles

1. **Extract, don't invent** -- Rules codify what projects actually do
2. **Specific over generic** -- Every generated rule references the actual codebase
3. **Fewer, sharper rules** -- 10 precise rules beat 50 vague ones
4. **Security is non-negotiable** -- PreToolUse hooks enforce in real-time, QC reviews post-hoc
5. **Stack-agnostic schema** -- The manifest works for any language/framework
6. **Plugin-native** -- Distributed as a Claude Agent SDK plugin, not a copy-paste installer
