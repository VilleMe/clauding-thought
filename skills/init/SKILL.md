---
name: init
description: "Analyze this codebase and generate its .claude/ governance layer: manifest, path-scoped rules, pattern files, task-loop skills, and enforcement hooks. Pass --update to refresh scripts, hooks, and the self-test without re-analyzing."
argument-hint: "[--update]"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---

# Clauding Thought: Init

**IMPORTANT:** An existing root-level `CLAUDE.md` does NOT mean governance is initialized. Leave it alone. Everything generated here goes inside `.claude/`.

## Step 0: SCAFFOLD

Run the scaffold script from the plugin, exactly as written, without changing directory first. Use `python3` on macOS and Linux if `python` is not on the PATH.

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py" --project "${CLAUDE_PROJECT_DIR}"
```

If `$ARGUMENTS` contains `--update`:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py" --update --project "${CLAUDE_PROJECT_DIR}"
```

The scaffold creates the directory tree, copies the hook scripts, merges the governance hooks into `.claude/settings.json` (preserving the project's own hooks and permissions), creates stub files, retires files from older plugin versions, and runs the hook self-test. Its JSON output tells you what it did, what remains for you, and these paths you need later: `schema`, `rule_templates_dir`, `pattern_template`, `packs_dir`. Keep the output.

**Self-test:** the output's `selftest` block says whether every hook fired on realistic input. If `selftest.status` is not `pass`, show the failed rows from `.claude/selftest.json` and stop. A hook that does not fire in the self-test will not fire in real work either, and silent hooks are the failure this plugin exists to prevent.

## Update Mode

If the scaffold output shows `"mode": "update"`, follow its `next_steps` list and do nothing else:
- Set `governance.plugin_version` in `.claude/manifest.json` to the scaffold's `plugin_version`.
- If the manifest has no `verification` block, add one: `test_command` and one `kind: "test"` gate from the project's test runner (see Step 1 for detection), `claim_guard: "annotate"`, `claim_window_turns: 1`, `llm_judge: false`. If the manifest has no `task_docs.headings`, add `{ "scope": "Scope", "thesis": "Thesis" }`.
- If `task_doc_skill_has_scope` is `false`, regenerate `.claude/skills/task-doc/SKILL.md` so new task docs carry a `## <scope heading>` section (see Step 4c). Keep every other section and customisation the project added.
- Add an `[Unreleased]` entry to `.claude/CHANGELOG.md` naming what was refreshed.
- Report what was refreshed, the retired files, and the self-test summary. STOP.

- If `.claude/agents/qc-reviewer.md` or `.claude/skills/qc-fix/SKILL.md` is missing (projects scaffolded before 3.2), generate them per 4c and 4h, and add `context: fork`, `agent: qc-reviewer`, `background: false` to the existing qc skill's frontmatter if absent. If the manifest has no `task_docs.complexity`, leave it absent; the scorer uses its defaults.
- If the task-doc skill does not write the thesis section, or the close-task skill does not run the thesis check, or the evolve skill has no telemetry step (projects scaffolded before 3.3): regenerate those skills per 4c, preserving the project's customisations. Existing task docs are not edited; one without a thesis section is handled by close-task when it closes.

Do NOT re-analyze. Do NOT touch preflight, evolve, close-task, rules, or patterns beyond the items above.

---

## Full Init

## Step 1: DETECT — Identify the Stack

Read whichever of these exist:

**Package manifests:** `composer.json`, `package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml` / `requirements.txt`, `Gemfile`, `pom.xml` / `build.gradle`, `*.csproj`, `mix.exs`, `pubspec.yaml`.

**Framework markers:** framework CLI entry points, `next.config.*`, `nuxt.config.*`, `manage.py`, `config/routes.rb`, `angular.json`, `svelte.config.*`, `Program.cs`, and similar.

**Config:** `.env.example` (shape of configuration), database config, auth config, build tooling (`vite.config.*`, `webpack.config.*`, `tsconfig.json`), formatter config (`.prettierrc`, `.editorconfig`, `pyproject.toml [tool.*]`, linter configs).

**Test runner:** the test script in the package manifest, a test config file, or CI config. Record the exact command (`npm test`, `pytest`, `go test ./...`, `vendor/bin/phpunit`, `cargo test`, `dotnet test`) and what its success output looks like; this becomes `verification.test_command` and the first gate.

**Directory structure:** list the project root and the main source directories. Map where routes, handlers, entities, services, schema migrations, validation, tests, and frontend code live. Record a glob for each (e.g. `src/handlers/**`, `app/Models/**`, `internal/service/**`). These globs drive the `paths:` frontmatter of the rule files and the `<!-- scope: -->` annotations.

## Step 2: SAMPLE — Extract Patterns

For each archetype present in this project, read 3-5 representative files and extract the common shape. Archetype names depend on the stack; use the project's own vocabulary.

**Backend archetypes (whichever exist):**
- Handlers (controllers, resolvers, command handlers): authorization, response style, dependency injection
- Entities (models, records, aggregates): scoping mechanism, relationships, attribute typing, field exposure
- Services / use cases / actions: where business logic lives, dependency patterns
- Schema migrations: column conventions, foreign keys, indexes, reversibility
- Validation: where rules live, syntax, custom messages
- Authorization policies / guards / permissions
- Tests: setup style, assertion style, data creation
- Background jobs / scheduled tasks, if present

**Frontend archetypes (whichever exist):**
- Pages / views: layout, data loading, prop shapes
- Components: naming, composition, state management
- Forms: validation, submission, error handling
- API layer: how the frontend talks to the backend

**For each archetype, record:**
1. Structural elements that are always present
2. Naming conventions
3. Import patterns
4. Authorization / validation approach
5. One canonical example: the cleanest, most representative file, with its path
6. The directory glob where this archetype lives

## Step 3: ANALYZE — Understand Architecture

### Multi-tenancy
- Look for global query scopes, tenant mixins/base classes, middleware that sets tenant context
- Check whether entities share a tenant column (`tenant_id`, `account_id`, `workspace_id`, ...)
- Name the isolation strategy and the escape hatch that bypasses it

### Authorization
- How do handlers authorize? Per-method checks, constructor-level, route middleware, decorators?
- Policies? Gates? An RBAC package? An owner/admin bypass?

### Module boundaries
- Are there distinct modules or domains? What may import from what? Is there a shared/core layer?

### Internationalization
- How are translations handled, how many locales, are all locales always required?

### Data flow
Map the request lifecycle in this project's terms, e.g. `Route → Middleware → Handler → Validation → Service → Entity → Serializer → Response`. Note which layers exist and which are skipped.

### File storage
If there is storage configuration (a filesystem config, object-storage settings, a media root), record the default location and whether downloads require authentication for `architecture.file_storage`. Omit the field otherwise.

### Data gates
Look for commands that check the state of data rather than code: consistency checks, schema verifiers, seed validators, health commands, "golden" queries in scripts or CI. Each becomes a `kind: "data"` gate in `verification.gates` with the output line that marks success. If none exist, leave the list with only the test gate and say so in the report; the claim-guard hook will ask for one the first time a data claim is made without evidence.

## Step 3.5: DISCOVER — Rule Packs

Read every `pack.json` under `packs_dir` from the scaffold output.

A pack matches when its `stack_filter` is absent or empty, or when ALL of its non-empty filter arrays match the detected stack: `stack_filter.language` (if non-empty) must contain `stack.language`, AND `stack_filter.framework` (if non-empty) must contain `stack.framework`. An empty array means no constraint for that dimension.

Present matching packs to the user:

> These rule packs match your stack:
> - **owasp-top-10** v1.0.0 — OWASP Top 10 security rules for web applications
>
> Apply all / select specific / skip?

Record the selection for Steps 4a and 4e. If nothing matches, skip silently.

## Step 4: GENERATE

Every file must be specific to THIS project. No generic boilerplate.

### 4a. `.claude/manifest.json`

Follow the schema at the `schema` path from the scaffold output. Fill every field you can determine with confidence; use `null` for the rest. Set `version` to `"1.1"`.

Governance, task-doc, and verification blocks:
```json
{
  "governance": {
    "version": "1.0.0",
    "initialized": "<today>",
    "last_evolved": null,
    "changelog": "CHANGELOG.md",
    "plugin_version": "<plugin_version from scaffold output>",
    "packs": [
      { "name": "<pack-name>", "version": "<version>", "applied": "<today>", "customized": false }
    ]
  },
  "task_docs": {
    "enabled": true,
    "directory": "tasks",
    "auto_create_threshold": {
      "min_files": 3,
      "always_for": ["migration", "security", "new-route", "cross-module"]
    },
    "promote_lessons": true,
    "headings": { "scope": "Scope", "thesis": "Thesis" }
  },
  "verification": {
    "test_command": "<from Step 1>",
    "gates": [
      { "name": "<runner name>", "command": "<test_command>", "success_pattern": "<regex matching its success output>", "kind": "test" }
    ],
    "claim_guard": "annotate",
    "claim_window_turns": 1,
    "llm_judge": false
  }
}
```

`governance.packs` is `[]` when no pack was selected. Add the `kind: "data"` gates found in Step 3.

For each `security.checks` entry, set `paths` to the globs from Step 1 that the check targets: authorization checks → handler and route globs; tenancy checks → entity and validation globs; exposure checks → handler and serializer globs; injection and secrets checks → omit `paths` (all files). Use `error` / `warning` / `info` for severity.

### 4b. `.claude/CLAUDE.md`

The governance summary, loaded in every session. Structure:
1. **Overview**: one paragraph on what this project is
2. **Module system**: if modules exist, how they relate
3. **Multi-tenancy**: if present, the rules that must never be broken
4. **Authorization**: the pattern, with a real example from this codebase
5. **Data exposure**: what never reaches a client, and how serialization works
6. **Internationalization**: if present, the locale contract
7. **Where business logic goes**
8. **Security enforcement**: the blocking rules, one line each
9. **Pre-commit checklist**: ordered checks before finishing a change
10. **Governance workflow**: one line each for `/preflight` (which also scores complexity and says whether to enter plan mode first), `/task-doc`, `/qc` (runs in a read-only subagent and returns a `QC_VERDICT` block; whoever ran it appends that block to the active task doc's `## QC` section), `/qc-fix` (the bounded fix-and-recheck loop), `/close-task`, `/evolve`, `/clauding-thought:report`, where the detailed rules live (`.claude/rules/`, `.claude/patterns/`), and the hooks in force: writes outside the active task's `## Scope` are denied, claims about data need a declared gate, test claims need test output.

Keep it under 200 lines. Detail belongs in the rule files.

### 4c. Skills

Generate six project-customized skills in `.claude/skills/<name>/SKILL.md`. Each has YAML frontmatter and full agent logic in the body, ends with `$ARGUMENTS`, and references this project's actual files, globs, and rule IDs.

**`preflight`** — context brief and routing before coding. Frontmatter:
```yaml
---
name: preflight
description: "Gathers context before coding. Classifies the task, loads the relevant rules and patterns, finds sibling files, proposes the task's scope, scores complexity, and says whether to plan first."
argument-hint: "<task description>"
user-invocable: true
allowed-tools: ["Read", "Glob", "Grep", "Bash"]
---
```
It classifies the task by archetype, loads only the matching rule sections and pattern files, lists sibling files to imitate, names the security surface, proposes the path globs the task will need (these become the task doc's scope section), and recommends a task doc when the change meets `task_docs.auto_create_threshold`.

It then scores complexity by running the scorer with the files it expects the task to touch (project-relative), adding `--new-archetype` when the task creates a file type with no sibling:
```bash
python .claude/scripts/complexity.py --files <file> <file> ... [--new-archetype]
```
The brief MUST print the returned score, tier, and factors, and route on the tier:
- **trivial**: proceed with the brief.
- **medium**: tell the user to enter plan mode before any edit, and list what the plan must contain: target files and order, the pattern each file follows, security and tenancy implications, and the rollback story. The brief ends there; coding starts after the plan is approved.
- **high**: as medium, and additionally decompose the work into sub-tasks, each with its own task doc and scope section, before any edit.
Weights and thresholds come from `task_docs.complexity` in the manifest; the brief names them so the user can tune them.

**`qc`** — post-generation review, run in a read-only subagent. Frontmatter:
```yaml
---
name: qc
description: "Quality control review. Evaluates uncommitted changes against the manifest-driven security, architecture, and convention rules in a read-only subagent. Returns a QC_VERDICT."
argument-hint: "[--diff | --full]"
user-invocable: true
context: fork
agent: qc-reviewer
background: false
---
```
`context: fork` runs the body in the `qc-reviewer` subagent (generated in 4h) with no conversation history, and `background: false` returns its result in the invoking turn. The body therefore MUST gather its own inputs: run `git diff` and `git diff --cached` (or, with `--full`, read every file under the active task doc's scope section), read `.claude/manifest.json`, the rule files, the matching pattern files, and the active task doc's Suppressions table. It MUST end by returning the `QC_VERDICT` block as its entire result, with nothing after it.

The body MUST embed these behavioural rules:
1. **Report, don't judge.** Report each violation with its rule ID and severity. Never downgrade a finding as "acceptable", "a deliberate tradeoff", "minor", or "justified". The developer decides what to suppress.
2. **Rules are the source of truth.** If `.claude/rules/` says X and the code does Y, that is a violation. QC does not second-guess rules; `/evolve` changes them.
3. **Check suppressions, not intent.** The only reason to skip a finding is an entry in the active task doc's Suppressions table.
4. **Convention violations can be errors.** Read the inline `<!-- severity: -->` annotation; do not assume conventions are always warnings.
5. **Three tiers, one verdict.** Security, architecture, conventions, each with its own section. `manifest.security.posture` decides whether security findings BLOCK (strict) or WARN on baseline gaps (advisory). The verdict is PASS, WARN, or BLOCK.
6. **Every finding names the file, the line, the rule ID, and the rule section it violates**, so a fix pass can work from the verdict alone.

The `QC_VERDICT` block:
```
QC_VERDICT: PASS | WARN | BLOCK
  security:     <findings or "none">
  architecture: <findings or "none">
  conventions:  <findings or "none">
  suppressed:   <rule IDs skipped via the Suppressions table>
  files_reviewed: N
```

Claude Code also ships `/code-review` and `/security-review`. QC does not replace them: it checks this project's declared rules; they hunt bugs and generic security issues. Mention both in the skill's closing note.

**`qc-fix`** — bounded fix-and-recheck loop, run in the main conversation. Frontmatter:
```yaml
---
name: qc-fix
description: "Runs /qc, and on WARN or BLOCK applies a targeted fix pass limited to the verdict's findings, then re-runs /qc. At most three cycles; every cycle is appended to the task doc."
argument-hint: "[--max-cycles N]"
user-invocable: true
allowed-tools: ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]
---
```
The body: run `/qc` and read the verdict. If PASS, append it to the active task doc's `## QC` section and stop. Otherwise, for at most `--max-cycles` cycles (default 3): launch a fix pass as a subagent whose prompt contains only the verdict, the affected files, and the violated rule sections, with the instruction to change nothing else; then run `/qc` again; append each verdict, with the cycle number and the files changed, to `## QC`. If the verdict is still BLOCK after the last cycle, stop, print the history of the cycles, and say what remains, without softening it. The cap is not configurable above 5: self-correction degrades past a few iterations.

**`evolve`** — re-analysis and rule maintenance. Frontmatter:
```yaml
---
name: evolve
description: "Re-analyzes the codebase and updates the governance layer. Detects drift, applies rule candidates from closed tasks, keeps rule files scoped and small, bumps the governance version."
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---
```
It re-runs Steps 1-3, diffs against the stored manifest, reads `## Rule Candidates` entries from task docs closed since `last_evolved`, proposes rule and pattern changes, and on acceptance updates the files, `governance.version`, `last_evolved`, and the changelog per `skills/evolve/changelog-spec.md`. Pack sections between `<!-- pack:... -->` markers are updated only when not customized.

It MUST include a **telemetry** step before proposing anything. Run the aggregator for the window since the last evolve:
```bash
python .claude/scripts/report_data.py --since <governance.last_evolved or the initialized date>
```
and read from its output: `tasks.rule_candidates.items` (lessons that `/close-task` filed as rule candidates since the last evolve), `hooks[].top_files` and `top_reasons` (where the guards keep firing), `tasks.scope_coverage` and `tasks.thesis_coverage`, `verification.data_gates`, and `rules` (sizes and scoping). Then read the `## Suppressions` tables of the task docs in the window. Turn these into proposals through the same approval flow as drift, each citing its evidence:
- a rule candidate → a new or amended rule section in the right tier, with the wording the task proposed;
- the same rule suppressed in three or more tasks → relax or clarify that rule, or record a permanent exception in it;
- a path that `scope-guard` keeps denying across tasks → propose it for the task-doc skill's scope suggestions or as a module boundary;
- `claim-guard` annotations with no data gates declared → propose `verification.gates` entries for the checks the project already runs;
- any rule file the `rules` block shows as unscoped or over 12 KB → the rule-hygiene proposals below.
After the user accepts, set `governance.last_evolved` to today so the next run starts from here.

It MUST also include a **rule hygiene** step: for each `.claude/rules/*.md`, report its size and whether it has `paths:` frontmatter. Propose adding `paths:` (with globs from the current Step 1 analysis) to any file that lacks it other than `security.md`, splitting any file over 12 KB into scoped files by archetype (for example `rules/frontend.md` with the frontend globs), and moving narrative prose into pattern files. Before offering a frontmatter change, check that it parses as YAML (a `paths:` list of quoted strings) and that each glob matches at least one file in the project tree. A malformed frontmatter makes a rule file never load, which is worse than an unscoped one.

**`task-doc`** — task document lifecycle. Frontmatter:
```yaml
---
name: task-doc
description: "Creates or updates the task document for the current work. Tracks intent, scope, decisions, files changed, QC verdicts, and lessons."
argument-hint: "<task description or 'update'>"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---
```
New task docs go in `.claude/<task_docs.directory>/YYYY-MM-DD-slug.md` with `status: open` near the top and these sections, in this order, using the heading names from `task_docs.headings` for scope and thesis:
- `## Intent`
- `## <scope heading>` — one path glob per line, as a markdown list, naming the files this task may write to (for example `- src/billing/**`). The `scope-guard` hook denies writes outside this list while the task is active, and the denial tells the model to either log the discovery here under Implementation or extend this list as a visible decision. Preflight proposes the initial globs.
- `## <thesis heading>` — three labelled lines:
  ```markdown
  **Claim:** <one sentence, from the user's point of view, that is false until this task ships>
  **Observable:** <the exact output, screen, row, or response that shows the claim is true>
  **Demonstrated:**
  ```
  `Demonstrated:` stays empty until `/close-task` runs the demonstration. A task with no user-visible outcome (a refactor, a dependency bump, tooling) writes `no-user-observable-change: true` on its own line near the top instead of this section, with one sentence under Intent saying why.
- `## Plan`
- `## Implementation` — running log of decisions, discoveries, and files changed
- `## QC` — verdicts appended by `/qc` and `/qc-fix`
- `## Suppressions` — table: Rule ID, Reason
- `## Lessons`
- `## Closure`

Register the task in `<task_docs.directory>/INDEX.md`. On `update`, append to Implementation and never rewrite the scope list or the thesis claim silently.

**`close-task`** — finalization. Frontmatter:
```yaml
---
name: close-task
description: "Finalizes the active task document. Refuses on a BLOCK verdict, records the commit, captures lessons, and files rule candidates for /evolve."
argument-hint: "[optional: lessons learned]"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---
```
Pre-close checks, in order:
1. The latest QC verdict in `## QC` is not BLOCK.
2. The Implementation section is not empty, and every Suppressions row has a reason.
3. **The thesis is demonstrated.** If the doc carries `no-user-observable-change: true`, skip this check and say so. Otherwise read the `## <thesis heading>` section:
   - If it is missing, or Claim or Observable is empty: refuse to close. Ask the author for the claim and the observable, or for the opt-out line with a reason.
   - If `Demonstrated:` is empty: invoke the bundled `/verify` skill with the Claim as what to confirm and the Observable as the acceptance criterion. If it confirms the observable, write `**Demonstrated:** <ISO 8601 timestamp> via /verify: <one line on what was observed>` into the section. If it cannot confirm it, refuse to close and report exactly what differed from the Observable, without softening it.
   - If `Demonstrated:` already carries a date, accept it.
   Never fill in `Demonstrated:` without a run that showed the Observable.
Then: record the commit reference, write `## Lessons`, add any lesson that should become a permanent rule under `## Rule Candidates` as a markdown list (one item per candidate: tier, proposed wording, the task that motivated it), set `status: closed`, update the task index.

### 4d. Pattern files

For each archetype sampled in Step 2, hydrate `pattern_template` (from the scaffold output) into `.claude/patterns/<archetype>.md`. Use the project's own archetype names for the file names (`handler.md`, `entity.md`, `migration.md`, `test.md`, `component.md`, `job.md`, ...). The canonical example is real code from this project, copied verbatim with its path.

### 4e. Rule files

Hydrate the three templates in `rule_templates_dir` (from the scaffold output) into `.claude/rules/security.md`, `.claude/rules/architecture.md`, `.claude/rules/conventions.md`, replacing every `{{placeholder}}` and resolving every `{{#if}}` / `{{#each}}` block. No template syntax may remain in the output: Claude Code auto-loads `.claude/rules/` and literal `{{` in a loaded rule file breaks it.

Claude Code reads the `paths:` frontmatter natively: a rule file with `paths:` is loaded only when a matching file is read or edited; a file without `paths:` is always loaded.
- `security.md`: no `paths:` frontmatter. Always loaded.
- `architecture.md` and `conventions.md`: set `paths:` to the source globs from Step 1 so the rules load when source files are touched and stay out of context otherwise.

Keep each rule file under 12 KB. If the project has more to say, make another scoped file rather than a longer one.

**Per-module rule files.** When `architecture.modules` has more than one entry, write one `.claude/rules/<module>.md` per module with `paths:` set to that module's path, holding only what is specific to that module: its allowed imports from `boundaries.modules_may_import`, its own conventions, and any security checks whose `paths` fall inside it. The shared architecture and conventions files keep what applies everywhere. A module file with nothing specific to say is not written.

Also set the `<!-- scope: -->` annotations on sections to the archetype globs from Step 2, and `<!-- severity: -->` on sections that deviate from the tier default.

**Pack merging:** for each selected pack, append its rule files to the target rule file as delimited sections, and add the pack's `security_checks` to `manifest.security.checks`:
```markdown
<!-- pack:<pack-name>:<section-id>:start -->
## Section Title
[pack rule content]
<!-- pack:<pack-name>:<section-id>:end -->
```

### 4f. Changelog

Create `.claude/CHANGELOG.md`:

```markdown
# Changelog

All notable changes to this project's governance layer are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [1.0.0] - <today>

### Added
- Initial governance layer generated by the Clauding Thought init skill
- Manifest: <what was detected>, verification gates: <list>
- Security rules: <key checks>
- Architecture rules: <key boundaries>
- Convention rules: <key conventions>
- Pattern files: <list>
- Skills: preflight, qc, qc-fix, evolve, task-doc, close-task
- Subagent: qc-reviewer
- Hooks: secret-filter, destructive-guard, scope-guard, anti-rationalization, evidence-check, claim-guard
```

### 4g. Settings and hooks

Already written by the scaffold. Do not write or edit `.claude/settings.json`; read it only if you need to verify it.

### 4h. The reviewer subagent

Write `.claude/agents/qc-reviewer.md`, the subagent the `qc` skill runs in:
```markdown
---
name: qc-reviewer
description: "Read-only reviewer for this project's declared governance rules. Used by the qc skill; returns a QC_VERDICT block."
tools: Read, Glob, Grep, Bash
---

You review changes in <project name> against the rules in `.claude/rules/` and the manifest in `.claude/manifest.json`. You do not edit files. Bash is for `git diff`, `git diff --cached`, `git status`, and `git log`, nothing else. You report every violation with file, line, rule ID, and the rule section; you never downgrade a finding; you skip a finding only when the active task doc's Suppressions table lists its rule ID. Your entire result is one QC_VERDICT block.
```
Fill in the project name and, if the manifest names a test command, allow Bash to run it as well so QC can confirm the suite still passes.

## Step 5: VERIFY — Calibrate

1. Pick 3 existing files from the codebase
2. Run the generated QC rules against them mentally
3. They should PASS, since they are existing, presumably correct code
4. If they would WARN or BLOCK, the rules are too strict. Adjust.
5. Grep `.claude/rules/` and `.claude/patterns/` for `{{`. There must be none.
6. Confirm the scaffold's `selftest.status` was `pass`. If you changed anything under `.claude/scripts/` or `.claude/settings.json` since, rerun:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/selftest.py" --project "${CLAUDE_PROJECT_DIR}"
   ```

## Output

| # | File | Your job |
|---|------|----------|
| 1 | `.claude/manifest.json` | GENERATE, with `verification` and `task_docs.headings` |
| 2 | `.claude/CLAUDE.md` | GENERATE |
| 3 | `.claude/CHANGELOG.md` | GENERATE |
| 4 | `.claude/rules/{security,architecture,conventions}.md`, plus `rules/<module>.md` per module when there is more than one | GENERATE by hydrating templates |
| 5 | `.claude/patterns/*.md` | GENERATE, one per archetype |
| 6 | `.claude/skills/{preflight,qc,qc-fix,evolve,task-doc,close-task}/SKILL.md` | GENERATE project-customized |
| 7 | `.claude/agents/qc-reviewer.md` | GENERATE (4h) |
| 8 | `.claude/settings.json` | scaffold (verify, do not write) |
| 9 | `.claude/tasks/INDEX.md` | scaffold (verify) |
| 10 | `.claude/skills/evolve/changelog-spec.md` | scaffold (verify) |
| 11 | `.claude/scripts/*.py`, `.claude/selftest.json` | scaffold (verify the self-test passed) |

Report what you created, the self-test summary, and any manifest fields left `null`.

## Security Posture Detection

**New project** (few or no handlers, entities, routes): `security.posture = "strict"`. All security rules block from day one. No baseline gaps.

**Existing project** (established handlers, entities, routes): `security.posture = "advisory"`. Scan for gaps and record each in `security.baseline_gaps` with id, category, description, affected files, mitigation, severity. New code must still follow the strict rules; advisory applies only to the existing patterns, and the gap list is the migration backlog toward strict.

Gap categories: `auth` (handlers without authorization), `tenancy` (tenant-owned entities without scoping), `exposure` (raw entities reaching clients), `injection` (string-built queries or commands), `secrets` (credentials in source, raw environment reads in application code), `file-access` (unauthenticated downloads, public user uploads), `csrf`, `session`.

## Principles

- **Specific over generic.** Every rule references patterns found in THIS codebase.
- **Extract, don't invent.** Codify what the project does; do not import outside opinions.
- **Fewer, sharper rules.** Ten precise rules beat fifty vague ones.
- **Real code examples.** Pattern files contain actual code from the project.
- **Security is non-negotiable.** Posture controls enforcement style, not whether security matters.
- **Prove it fires.** The self-test must pass before init is reported as done.

$ARGUMENTS
