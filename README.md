# Clauding Thought

**Project-specific governance for Claude Code, generated from your codebase.**

Clauding Thought is a Claude Code plugin. Run `/clauding-thought:init` in a project and it reads the code, works out the stack, the tenancy model, the authorization pattern, the module boundaries and the conventions, and writes a `.claude/` governance layer that fits that project: a manifest, path-scoped rule files, pattern files with real examples, and a small set of skills for the task loop. It also installs six hooks that catch things Claude Code does not catch on its own, and a self-test that proves each hook fires.

It is stack-agnostic and project-agnostic. Nothing in this repository is specific to any one codebase; every rule a project ends up with was extracted from that project.

## What Claude Code already does, and what this adds

Claude Code ships rules (`.claude/rules/` with `paths:` scoping), auto-memory, skills, hooks, `/init` for a starter `CLAUDE.md`, and `/code-review`, `/security-review`, `/verify`. Clauding Thought builds on those rather than replacing them. What it adds:

| Gap in Claude Code | What Clauding Thought does |
|---|---|
| `/init` writes a generic CLAUDE.md | Deep analysis into a manifest: tenancy, auth, boundaries, conventions, archetypes, verification gates |
| Rules are hand-written | Rule files hydrated from the codebase, with `paths:` frontmatter so they load only when relevant |
| No notion of "how a handler looks here" | One pattern file per archetype, canonical example copied from the project |
| Review is generic | `/qc` checks the project's own declared rules in a read-only subagent, with severity tiers and a suppressions table; `/qc-fix` diagnoses first, fixes at the root cause, and undoes an attempt that did not work |
| Nothing routes a big change into plan mode | `/preflight` scores complexity from the files a task will touch and sends medium and high tasks into plan mode before any edit |
| Nothing stops a task from quietly touching files it never declared | `scope-guard` denies writes outside the active task's declared scope |
| No real-time secret or destructive-command guard on writes and shell | `secret-filter` and `destructive-guard` |
| Nothing stops "tests pass" without a test run, or "the data is correct" without a check, or quiet dismissal of findings | `evidence-check`, `claim-guard`, `anti-rationalization` |
| No way to know whether your hooks are working | A self-test that runs every hook on realistic input, and a report that says inert or compliant |
| No per-task audit trail | Task docs with intent, scope, a thesis, decisions, QC verdicts, lessons |
| Every gate can be green while the user sees no change | Each task states a user-visible claim and its observable; `/close-task` demonstrates it with the bundled `/verify` before closing, or the task opts out in writing |
| Rules drift from the code and bloat the context | `/evolve` reads the telemetry (rule candidates from closed tasks, repeat suppressions, where the guards fire), folds what it finds into the rules, and keeps rule files scoped and small |

## Prerequisites

- Claude Code with plugin support
- Python 3 on the PATH as `python` (Windows) or `python3` (macOS, Linux); the scaffold picks the right name
- The analysis in the init skill reads a lot of files. A high-throughput plan is recommended.

## Quick start

```bash
# From an interactive claude session: add the marketplace and install the plugin
/plugin marketplace add <path-or-url-to-this-repo>
/plugin install clauding-thought@clauding-thought
```

Then in the project:

```
/clauding-thought:init                 # analyze the codebase, generate .claude/, run the self-test
/preflight "Add invoice export"        # context brief, proposed scope, complexity score and routing
/task-doc "Add invoice export"         # start the task document (with its scope section)
# ... plan first if preflight said so, then write code ...
/qc                                    # review changes against the project's rules (read-only subagent)
/qc-fix                                # or: review, diagnose, fix at the root cause, re-review, undo what failed, max 3 cycles per task
/close-task                            # demonstrate the thesis via /verify, record lessons, refuse on BLOCK
/evolve                                # periodically: read telemetry, re-analyze, update rules, keep them scoped
/clauding-thought:report               # what the governance layer is actually doing
/clauding-thought:init --update        # after a plugin upgrade: refresh scripts, hooks, self-test
```

## What the init skill generates

```
.claude/
├── manifest.json          project DNA: stack, architecture, conventions, boundaries, security, verification
├── CLAUDE.md              governance summary, loaded every session
├── CHANGELOG.md           governance version history
├── settings.json          the six hooks (merged into existing settings)
├── selftest.json          last self-test result
├── rules/
│   ├── security.md        always loaded
│   ├── architecture.md    paths: scoped to source globs
│   ├── conventions.md     paths: scoped to source globs
│   └── <module>.md        one per module when there are several, scoped to the module path
├── patterns/
│   └── <archetype>.md     one per archetype found: handler, entity, migration, test, ...
├── skills/
│   └── preflight/  qc/  qc-fix/  task-doc/  close-task/  evolve/    generated for this project
├── agents/
│   └── qc-reviewer.md     the read-only subagent /qc runs in
├── scripts/               hook scripts, their helpers, the complexity scorer, the telemetry aggregator
└── tasks/                 INDEX.md plus one document per task
```

## Hooks

| Hook | Event | What it does |
|------|-------|--------------|
| `secret-filter` | PreToolUse on Write, Edit, MultiEdit, NotebookEdit | Denies writes containing cloud and provider keys, private keys of any kind, JWTs, webhook URLs, connection strings with real passwords, and credential assignments in JSON, YAML, env-file and code forms. Templated values, environment lookups, placeholders, test values and local dev defaults pass |
| `scope-guard` | PreToolUse on Write, Edit, MultiEdit, NotebookEdit | Denies writes outside the active task doc's scope section, and writes to the governance files under `.claude/` (rules, scripts, settings, manifest, skills, agents) unless the scope lists them. The denial is a fork: log the discovery and stay in scope, or extend the scope as a visible decision. Inert without an active task |
| `destructive-guard` | PreToolUse on Bash | Tokenises the command (splitting on `;`, `&&`, `\|`, newlines) and judges each piece: recursive forced `rm` on the tree root, parent, home, a glob or a variable; force pushes without lease, `+refspec`, `git reset --hard`, `git clean -f`, `git checkout .`, deleting protected branches; destructive SQL, also inside a database client's quoted argument; `chmod 777`, `dd` to a device, `mkfs`; `find -delete` over a whole tree with no filter. Quoted mentions, dry runs and narrowed finds pass |
| `anti-rationalization` | Stop, only while a task is active | Pushes back once when the final response sets a finding aside ("out of scope", "pre-existing", "unrelated to this task", "flaky", "won't fix") without recording it with a reference or handling it now. Scoping the user asked for and the programming sense of "scope" are exempt |
| `evidence-check` | Stop | Pushes back once when the final response claims tests pass or the build succeeds but no Bash result in the turn shows a passing run with no failures. File reads, echoes and partial-failure output do not count; a declared gate's success pattern or silent success does |
| `claim-guard` | Stop | Notes (or, in block mode, pushes back) when the final response asserts a fact about data or state with no declared data gate output from a Bash result in the turn. A label placed before the claim on its line (`VERIFIED`, `HYPOTHESIS`, `evidence:`) exempts it |

Every hook reads its input as UTF-8 regardless of the console code page. A hook that cannot judge because of an internal error says so on stderr with a non-blocking exit, never silently. Decisions are logged to `.claude/hook-log.jsonl` with the session id and the file path, never with file or command contents; the scaffold adds the log and the self-test result to `.gitignore`. Stop hooks honour `stop_hook_active`, so they fire at most once per turn.

**Self-test.** The scaffold ends by running `scripts/selftest.py`: it builds throwaway fixture projects (one in a directory with a non-ASCII name), sends realistic UTF-8 input through every installed hook, and checks both the decision the hook returned and the decision and reason it logged, so an allow row proves the hook reached the branch it was meant to reach rather than crashing into fail-open. It also checks that `settings.json` registers each hook under the right event with a matcher covering the tools it needs and an interpreter that exists on PATH, that hooks disabled in the manifest are absent, and that no settings file sets `disableAllHooks`. Results go to `.claude/selftest.json`; the init skill stops on any failure.

**Optional LLM judge.** With `verification.llm_judge: true` in the manifest, the scaffold also registers a prompt-type Stop hook that asks the background model whether the response dismissed a finding or asserted a data fact without evidence. One model call per turn end; off by default.

## The manifest

`manifest.json` is derived from the codebase and everything else is derived from it. A trimmed example for a fictional project:

```jsonc
{
  "version": "1.1",
  "governance": { "version": "1.0.0", "initialized": "2026-10-30", "last_evolved": null,
                  "changelog": "CHANGELOG.md", "plugin_version": "3.1.0", "packs": [] },
  "stack": { "language": "typescript", "framework": "nestjs", "frontend": "react",
             "testing": "vitest", "db": "postgresql", "orm": "prisma" },
  "architecture": {
    "tenancy": { "strategy": "column-scoped", "scope_column": "tenant_id",
                 "trait": "TenantScoped", "trait_path": "src/common/tenant-scoped.ts" },
    "modules": [ { "name": "billing", "path": "src/billing" },
                 { "name": "catalog", "path": "src/catalog" } ]
  },
  "boundaries": { "modules_may_import": { "billing": ["core"], "catalog": ["core"] },
                  "shared_layer": "core" },
  "security": { "posture": "strict",
                "checks": [ { "id": "AUTH-001", "name": "Guard on every controller",
                              "severity": "error", "paths": ["src/**/*.controller.ts"] } ] },
  "verification": {
    "test_command": "npm test",
    "gates": [
      { "name": "unit tests",   "command": "npm test",          "success_pattern": "Tests:\\s*\\d+ passed", "kind": "test" },
      { "name": "schema check", "command": "npm run db:verify", "success_pattern": "schema ok",             "kind": "data" }
    ],
    "claim_guard": "annotate", "claim_window_turns": 1, "llm_judge": false
  },
  "task_docs": { "enabled": true, "directory": "tasks", "headings": { "scope": "Scope", "thesis": "Thesis" } }
}
```

`verification.gates` is how a project declares what counts as evidence: test gates back "tests pass", data gates back "the data is correct". `task_docs.headings` is how the hooks find the task doc sections even if a project renames them. The full schema is in `schema/manifest.schema.json`.

## Security posture

**Strict** is the default for new projects: every security rule blocks. **Advisory** is set automatically for existing codebases: new code is still held to the strict rules, known gaps are recorded as `baseline_gaps` with a mitigation each, and the goal is to migrate to strict. Advisory is an on-ramp, not an exemption.

## What it costs

- A file write launches two interpreters (`secret-filter`, `scope-guard`), a Bash call one, and the end of every turn three (the Stop hooks), each a few tens of milliseconds. The guards are registered on broad matchers on purpose: a prefix filter such as `Bash(rm *)` would miss compound commands, which is the case the guard exists for.
- Hook commands use `python` on Windows and `python3` elsewhere. The self-test fails when the registered interpreter is not on the PATH, so a team on mixed machines finds out at scaffold time.
- Bash-side writes (`echo > file`, heredocs) bypass `scope-guard` and `secret-filter`; those hooks see the file tools only. The reviewer subagent is read-only by instruction, not by sandbox.
- The guards are heuristics on the shapes seen so far, not a security boundary. Claude Code's own permission rules and sandbox remain the boundary where they apply.
- To turn a hook off, list it in `governance.disabled_hooks` in the manifest and run `--update`. The scaffold then leaves it out and the self-test expects it to be absent. Deleting the entry from `settings.json` by hand makes the self-test fail on purpose.

## Rule packs

`packs/` holds reusable rule sets that the init skill offers when their `stack_filter` matches. The bundled `owasp-top-10` pack covers injection, authentication failures, sensitive data exposure, and security misconfiguration, with good and bad examples in several languages. Applied packs are copied into the project so `/evolve` can tell a customised section from an untouched one. See `packs/README.md` to write one.

## Repository layout

```
clauding-thought/
├── .claude-plugin/        plugin.json, marketplace.json
├── skills/
│   ├── init/SKILL.md      /clauding-thought:init
│   └── report/SKILL.md    /clauding-thought:report
├── scripts/               hook scripts, scaffold.py, selftest.py, scaffoldtest.py, report_data.py (Python 3, stdlib only)
├── templates/evolve/      changelog-spec.md, copied next to the generated evolve skill
├── rules/                 rule templates with {{placeholders}}, hydrated by the init skill
├── patterns/archetype.md  pattern template, one copy per archetype
├── packs/                 rule packs
└── schema/                manifest schema
```

## Changes in 3.4.2

`/qc-fix` could stack patches on a symptom: its fix pass saw only the verdict, could not undo an earlier attempt, and left every attempt in the code when the cycles ran out. Now every finding is diagnosed before any edit, and only a code fault inside the task's scope gets an automatic fix; a wrong test, a flaky or environmental failure, or a misfiring rule goes to the user with its evidence. A fix pass gets the task's intent and earlier attempts, makes the smallest change at the root cause, and returns `NEEDS_DECISION` rather than add a new file, abstraction, option, dependency or symptom-only special case. Each cycle is snapshotted, so an attempt that survives or causes new findings is undone; a finding that survives two attempts stops the loop. The budget is per task, so running `/qc-fix` again no longer resets it, and WARN is reported instead of auto-fixed unless `--include-warnings` is passed. `/qc` now reports a failing test as a BLOCK finding named `test:<name>`, which the Suppressions table can list. `--update` flags `qc` and `qc-fix` skills that predate this, because generated skills are not copied into projects.

## Changes in 3.4.1

The scaffold no longer retires any file under `.claude/rules/`. 3.4.0 deleted `rules/delivery.md` when its text contained the word "delivery", which every delivery rule file does, so a project's own rules written under that name were lost on update. Hydrated rules are extracted from the project and edited by it, so they are project content even when the plugin wrote the first draft, and nothing in 3.x replaces that file. The scaffold scenarios that verified 3.4 now live in the repository as `scripts/scaffoldtest.py` and include a project-authored `rules/delivery.md`, with and without the generated header, surviving an update unchanged. If 3.4.0 deleted the file in your project, restore it from version control.

## Changes in 3.4

A fix release from an adversarial review of 3.3 (three independent reviewers, every finding reproduced). The scaffold reads settings and manifest before touching anything, refuses a settings file it cannot parse instead of replacing it, keeps a backup, owns hooks by the script they run from `.claude/scripts/` rather than by file name, and retires only files whose text shows the plugin wrote them. `destructive-guard` judges tokenised commands instead of regexes over the whole string, which closes the `rm -r -f .`, `rm -rf *`, `+refspec` and `git clean -d --force` gaps, stops flagging greps, dry runs and `-var-file`, and removes a pattern that took seconds on long tokens. `secret-filter` detects JSON, YAML, env-file and backtick credential forms, encrypted and PGP keys, JWTs and webhooks, and stops flagging CSS class names and local dev defaults. `evidence-check` accepts only Bash results, rejects partial failures, ties evidence to the kind of claim, and supports silent-success gates. `claim-guard` claims must name data or state, and a label exempts only when it precedes the claim. `anti-rationalization` runs only during a task, needs a reference or an immediate commitment to pass, and exempts scoping the user asked for and the programming sense of scope. `scope-guard` resolves real paths (prefixes, short names, junctions), takes relative paths against the hook's cwd, parses scope lines as people write them, finds the section at any heading level, reads task docs in subfolders and any encoding, and no longer exempts the governance files under `.claude/`. All hooks read UTF-8 input and report internal errors visibly. Task docs record a base commit, the QC verdict carries its time and base, close-task requires a review newer than the code and a demonstration with a stated method, and a change that cannot be shown locally has an honest opt-out. The self-test asserts the logged reason for every row, runs a non-ASCII fixture, checks interpreters, matchers and `disableAllHooks`, and covers the adversarial cases above. The aggregator parses every status form the same way, reads inline and unindented `paths:` lists, dates rule candidates by the task's closed date, and rejects a bad window. Hooks can be turned off through `governance.disabled_hooks`. The captured transcript fixture was re-sanitised with JSON-aware scrubbing.

## Changes in 3.3

Every task doc now carries a thesis: a user-visible claim, the observable that proves it, and a `Demonstrated:` line that stays empty until `/close-task` runs the bundled `/verify` skill against the observable and records the result with a timestamp. A task with no user-visible outcome says so in writing with `no-user-observable-change: true`. Close is refused when the thesis is missing or its demonstration fails, and the report shows how many recent tasks had a thesis, demonstrated it, or opted out. `/evolve` starts from telemetry: the aggregator is copied into projects again so the generated evolve skill can read rule candidates filed by closed tasks, where the guards keep firing and on which files, scope and thesis coverage, and rule-file sizes, and turn them into proposals through its normal approval flow.

## Changes in 3.2

`/qc` now runs in a generated read-only subagent (`.claude/agents/qc-reviewer.md`) and returns only its verdict, so the review never pollutes the main context; whoever ran it appends the verdict to the task doc. `/qc-fix` is the closed loop: review, a fix pass limited to the verdict's findings, re-review, at most three cycles, every cycle recorded. `/preflight` scores complexity with `scripts/complexity.py` from the files the task will touch (file count, module spread, security surface, new archetype; weights and thresholds in `task_docs.complexity`) and routes medium tasks into native plan mode and high tasks into plan mode plus decomposition. Projects with several modules get one scoped rule file per module. The report shows which rule files load every session and which load on touch. The self-test covers the scorer.

## Changes in 3.1

Two new hooks that read references the model did not write: `scope-guard` (the task doc's declared scope) and `claim-guard` (declared data gates in the transcript). A manifest `verification` block that declares what counts as evidence, and `task_docs.headings` so the hooks never hard-code a section name. A self-test that runs every hook on realistic input in isolation and is part of every scaffold run. Hooks now log the session id and the file path on every decision. The bootstrap and report skills ship as plugin skills (`/clauding-thought:init`, `/clauding-thought:report`), so the project-local init copy and the SessionStart seed are gone and Claude Code's own `/init` is no longer shadowed; `--update` retires both from projects scaffolded by 3.0. An opt-in LLM judge on Stop. Rule hygiene in `/evolve`.

Changes in 3.0 removed everything Claude Code now provides natively or that never fired in practice, and made all templates stack-agnostic.

## License

MIT
