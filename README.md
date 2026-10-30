# Clauding Thought

**Project-specific governance for Claude Code, generated from your codebase.**

Clauding Thought is a Claude Code plugin. Run `/init` in a project and it reads the code, works out the stack, the tenancy model, the authorization pattern, the module boundaries and the conventions, and writes a `.claude/` governance layer that fits that project: a manifest, path-scoped rule files, pattern files with real examples, and a small set of skills for the task loop. It also installs four hooks that catch things Claude Code does not catch on its own.

It is stack-agnostic and project-agnostic. Nothing in this repository is specific to any one codebase; every rule a project ends up with was extracted from that project.

## What Claude Code already does, and what this adds

Claude Code ships rules (`.claude/rules/` with `paths:` scoping), auto-memory, skills, hooks, `/init` for a starter `CLAUDE.md`, and `/code-review` and `/security-review`. Clauding Thought builds on those rather than replacing them. What it adds:

| Gap in Claude Code | What Clauding Thought does |
|---|---|
| `/init` writes a generic CLAUDE.md | Deep analysis into a manifest: tenancy, auth, boundaries, conventions, archetypes |
| Rules are hand-written | Rule files hydrated from the codebase, with `paths:` frontmatter so they load only when relevant |
| No notion of "how a controller looks here" | One pattern file per archetype, canonical example copied from the project |
| Review is generic | `/qc` checks the project's own declared rules, with severity tiers and a suppressions table |
| No real-time secret or destructive-command guard on writes and shell | `secret-filter` and `destructive-guard` PreToolUse hooks |
| Nothing stops "tests pass" without a test run, or quiet dismissal of findings | `evidence-check` and `anti-rationalization` Stop hooks |
| No per-task audit trail | Task docs with intent, scope, decisions, QC verdicts, lessons |
| Rules drift from the code | `/evolve` re-analyzes and folds rule candidates from closed tasks into the rules |

## Prerequisites

- Claude Code with plugin support
- Python 3 on the PATH as `python` (Windows) or `python3` (macOS, Linux); the scaffold picks the right name
- The analysis in `/init` reads a lot of files. A high-throughput plan is recommended.

## Quick start

```bash
# Add the marketplace and install the plugin (from an interactive claude session)
/plugin marketplace add <path-or-url-to-this-repo>
/plugin install clauding-thought@clauding-thought
```

Then in the project:

```
/init                                  # analyze the codebase, generate .claude/
/preflight "Add invoice export"        # context brief before coding
/task-doc "Add invoice export"         # start the task document
# ... write code ...
/qc                                    # review changes against the project's rules
/close-task                            # record lessons, refuse on BLOCK
/evolve                                # periodically: re-analyze, update rules, bump version
/report                                # what the governance layer is actually doing
/init --update                         # after a plugin upgrade: refresh scripts and hooks
```

## What `/init` generates

```
.claude/
├── manifest.json          project DNA: stack, architecture, conventions, boundaries, security
├── CLAUDE.md              governance summary, loaded every session
├── CHANGELOG.md           governance version history
├── settings.json          the four hooks (merged into existing settings)
├── rules/
│   ├── security.md        always loaded
│   ├── architecture.md    paths: scoped to source globs
│   └── conventions.md     paths: scoped to source globs
├── patterns/
│   └── <archetype>.md     one per archetype found: handler, entity, migration, test, ...
├── skills/
│   ├── init/              project-local copy, so /init --update works later
│   ├── preflight/  qc/  task-doc/  close-task/  evolve/    generated for this project
│   └── report/            boilerplate
├── scripts/               hook scripts and the report aggregator
└── tasks/                 INDEX.md plus one document per task
```

## Hooks

| Hook | Event | What it does |
|------|-------|--------------|
| `secret-filter` | PreToolUse on Write and Edit | Denies writes containing cloud keys, private keys, provider tokens, connection strings with passwords, hardcoded credentials |
| `destructive-guard` | PreToolUse on Bash | Denies `rm -rf` on root, home or cwd, force pushes without lease, `git reset --hard`, `git clean -f`, destructive SQL, `chmod 777`, `dd` to devices, `mkfs` |
| `anti-rationalization` | Stop | Pushes back once when the final response dismisses an issue ("out of scope", "pre-existing", "acceptable tradeoff") without committing to fix or track it |
| `evidence-check` | Stop | Pushes back once when the final response claims tests pass or the build succeeds but no test or build output appears in the turn's tool results |

All hooks fail open: a parse error or crash never blocks the tool. Every decision is logged to `.claude/hook-log.jsonl`, which `/report` aggregates. The Stop hooks honour `stop_hook_active`, so they fire at most once per turn.

## The manifest

`manifest.json` is derived from the codebase and everything else is derived from it. A trimmed example for a fictional project:

```jsonc
{
  "version": "1.1",
  "governance": { "version": "1.0.0", "initialized": "2026-10-30", "last_evolved": null,
                  "changelog": "CHANGELOG.md", "plugin_version": "3.0.0", "packs": [] },
  "stack": { "language": "typescript", "framework": "nestjs", "frontend": "react",
             "testing": "vitest", "db": "postgresql", "orm": "prisma" },
  "architecture": {
    "tenancy": { "strategy": "column-scoped", "scope_column": "tenant_id",
                 "trait": "TenantScoped", "trait_path": "src/common/tenant-scoped.ts" },
    "auth": { "authorization": { "strategy": "middleware",
              "patterns": [ { "pattern": "guard", "scope": "all controllers" } ] } },
    "modules": [ { "name": "billing", "path": "src/billing" },
                 { "name": "catalog", "path": "src/catalog" } ]
  },
  "boundaries": { "modules_may_import": { "billing": ["core"], "catalog": ["core"] },
                  "shared_layer": "core" },
  "security": { "posture": "strict",
                "checks": [ { "id": "AUTH-001", "name": "Guard on every controller",
                              "severity": "error", "paths": ["src/**/*.controller.ts"] } ] },
  "conventions": { "translation": { "system": "i18next", "locales": ["en", "de"],
                                    "all_locales_required": true } },
  "task_docs": { "enabled": true, "directory": "tasks" }
}
```

The full schema is in `schema/manifest.schema.json`.

## Security posture

**Strict** is the default for new projects: every security rule blocks. **Advisory** is set automatically for existing codebases: new code is still held to the strict rules, known gaps are recorded as `baseline_gaps` with a mitigation each, and the goal is to migrate to strict. Advisory is an on-ramp, not an exemption.

## Rule packs

`packs/` holds reusable rule sets that `/init` offers when their `stack_filter` matches. The bundled `owasp-top-10` pack covers injection, authentication failures, sensitive data exposure, and security misconfiguration with language-neutral examples. See `packs/README.md` to write one.

## Repository layout

```
clauding-thought/
├── .claude-plugin/        plugin.json, marketplace.json
├── hooks/hooks.json       SessionStart hook that installs the project-local /init skill
├── scripts/               hook scripts, scaffold.py, report_data.py (Python 3, stdlib only)
├── templates/
│   ├── init/              INSTRUCTIONS.md (the /init skill body) and the bundled schema
│   ├── skills/report/     boilerplate skill copied into projects
│   └── evolve/            changelog-spec.md
├── rules/                 rule templates with {{placeholders}}, hydrated by /init
├── patterns/archetype.md  pattern template, one copy per archetype
├── packs/                 rule packs
└── schema/                canonical manifest schema
```

The plugin itself ships no skills. Its SessionStart hook writes a project-local `/init` skill from `templates/init/INSTRUCTIONS.md`, and `/init` generates the rest inside the project. That keeps every skill project-local and editable.

## Changes in 3.0

Removed everything Claude Code now provides natively or that never fired in practice: the rule re-injection hook (native `paths:` scoping covers it), the project-local memory directory (native auto-memory covers it), the skill-reminder hook, the critique, export, insights and thesis skills, the delivery tier, and the opt-in task-doc gates. The two Stop hooks were rewritten for the current hook contract (`last_assistant_message`, transcript scanning); the two PreToolUse hooks now use `hookSpecificOutput.permissionDecision`. All templates and the schema are stack-agnostic.

## License

MIT
