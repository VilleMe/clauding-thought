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

If the scaffold output shows `"mode": "update"`, work through its `next_steps` list in order; it is computed from what the project already has. The list can contain:
- A `STOP` item first when the self-test failed: show the failed rows from `.claude/selftest.json` and go no further.
- Set `governance.plugin_version` in `.claude/manifest.json` to the scaffold's `plugin_version`.
- Add a `verification` block when missing: `test_command` and one `kind: "test"` gate from the project's test runner (see Step 1), `claim_guard: "annotate"`, `claim_window_turns: 1`, `llm_judge: false`. Add `task_docs.headings` when missing, using the headings this project's task docs already use.
- Regenerate a generated skill when the scaffold's `skill_state` says it predates a convention (no scope or thesis section in task-doc, no `/verify` in close-task, no telemetry step in evolve, no scorer in preflight, no `context: fork` or `test:<name>` findings in qc, no diagnosis and undo steps in qc-fix), per Steps 4c and 4h. Regenerating means rewriting the plugin-specified parts and keeping every section, rule ID, example and customisation the project added; say in the changelog what was kept.
- Generate `agents/qc-reviewer.md` or `skills/qc-fix/SKILL.md` when missing.
- Tell the user about files the scaffold kept because the plugin did not write them (`left_alone`).
- Add an `[Unreleased]` entry to `.claude/CHANGELOG.md` naming what was refreshed, retired and kept.
- Report what was refreshed, what was retired, and the self-test summary.

Existing task docs are never edited by an update. Do NOT re-analyze the codebase, and do not touch rules or patterns in update mode.

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

Follow the schema at the `schema` path from the scaffold output. Fill every field you can determine with confidence and omit the rest; the schema accepts `null` only for `governance.last_evolved`. Set `version` to `"1.1"`.

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
10. **Governance workflow**: one line each for `/preflight` (which also scores complexity and says whether to enter plan mode first), `/task-doc`, `/qc` (runs in a read-only subagent and returns a `QC_VERDICT` block; whoever ran it appends that block to the active task doc's `## QC` section), `/qc-fix` (diagnoses first, fixes at the root cause, undoes an attempt that did not work, within a per-task budget), `/close-task`, `/evolve`, `/clauding-thought:report`, where the detailed rules live (`.claude/rules/`, `.claude/patterns/`), and the hooks in force: while a task is active, writes outside its `## <scope heading>` are denied, and so are writes to the governance files under `.claude/` (rules, scripts, settings, manifest, skills, agents) unless the scope lists them; claims about data need a declared data gate; test claims need a passing Bash test run in the turn.

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

It then scores complexity by running the scorer, exactly as written and without changing directory, with the files it expects the task to touch, adding `--new-archetype` when the task creates a file type with no sibling:
```bash
python .claude/scripts/complexity.py --project "${CLAUDE_PROJECT_DIR}" --files <file> <file> ... [--new-archetype]
```
The output's `claude_dir` must be this project's. The brief MUST print the returned score, tier, and factors, and route on the tier:
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
`context: fork` runs the body in the `qc-reviewer` subagent (generated in 4h) with no conversation history, and `background: false` returns its result in the invoking turn. The body therefore MUST gather its own inputs: read the active task doc and, when it records a `base_commit`, diff against it (`git diff <base_commit>` plus uncommitted changes), otherwise `git diff` and `git diff --cached`; with `--full`, read every file under the task's scope section instead. Read `.claude/manifest.json`, the rule files, the matching pattern files, and the task doc's Suppressions table. When `verification.test_command` is set, run it once and report the result on the verdict's `tests:` line. It MUST end by returning the `QC_VERDICT` block as its entire result, with nothing after it.

The body MUST embed these behavioural rules:
1. **Report, don't judge.** Report each violation with its rule ID and severity. Never downgrade a finding as "acceptable", "a deliberate tradeoff", "minor", or "justified". The developer decides what to suppress.
2. **Rules are the source of truth.** If `.claude/rules/` says X and the code does Y, that is a violation. QC does not second-guess rules; `/evolve` changes them.
3. **Check suppressions, not intent.** The only reason to skip a finding is an entry in the active task doc's Suppressions table.
4. **Convention violations can be errors.** Read the inline `<!-- severity: -->` annotation; do not assume conventions are always warnings.
5. **Three tiers, one verdict.** Security, architecture, conventions, each with its own section. `manifest.security.posture` decides whether security findings BLOCK (strict) or WARN on baseline gaps (advisory). The verdict is PASS, WARN, or BLOCK.
6. **Every rule finding names the file, the line, the rule ID, and the rule section it violates**, so a fix pass can work from the verdict alone.
7. **A failing test is a finding.** Name it `test:<name>` on the `tests:` line with its failure message. It makes the verdict BLOCK unless the Suppressions table lists that `test:<name>`. Report the failure; do not diagnose it.

The `QC_VERDICT` block:
```
QC_VERDICT: PASS | WARN | BLOCK
  reviewed_at:  <ISO 8601 timestamp>
  base:         <base_commit or "uncommitted changes">
  security:     <findings or "none">
  architecture: <findings or "none">
  conventions:  <findings or "none">
  suppressed:   <rule IDs skipped via the Suppressions table>
  tests:        <test command and its result, with test:<name> and the message for each failure, or "not run">
  files_reviewed: N
```

Claude Code also ships `/code-review` and `/security-review`. QC does not replace them: it checks this project's declared rules; they hunt bugs and generic security issues. Mention both in the skill's closing note.

**`qc-fix`** — bounded fix-and-recheck loop, run in the main conversation. Frontmatter:
```yaml
---
name: qc-fix
description: "Runs /qc, diagnoses each BLOCK finding, applies the smallest fix at its root cause, and re-runs /qc. Undoes an attempt that did not work instead of patching on top of it. At most three cycles per task; every cycle is appended to the task doc."
argument-hint: "[--max-cycles N] [--include-warnings]"
user-invocable: true
allowed-tools: ["Read", "Edit", "Write", "Glob", "Grep", "Bash", "Agent"]
---
```
A repair loop's failure mode is stacking patches on a symptom until the fix is worse than the finding. The body MUST embed these steps:
1. **Review.** Run `/qc` and append the verdict to the active task doc's `## QC` section. PASS: stop. WARN: list the findings and stop, because a warning is the user's call; `--include-warnings` treats them like BLOCK findings.
2. **Diagnose before any edit.** Read each finding against the code and the task's Intent; for a failing test, run that test alone and read the failure. Record one class per finding under `## QC`:
   - `code`: the code is wrong. Name the root cause's file and line, and say why it causes the finding.
   - `test`: the test is wrong or outdated, for example it asserts behaviour this task changed on purpose.
   - `environment`: flaky, caused by the environment, or failing without this task's change.
   - `rule`: the rule misfires or does not fit this case.
   Only a `code` finding whose root cause is inside the task's scope goes to a fix pass. Any other finding is handed to the user with its evidence, to fix, suppress with a reason, send to `/evolve`, or extend the scope. When nothing is left to fix, go to step 7.
3. **Snapshot.** Record the working tree without touching the index or any file, and keep the printed tree id as the cycle's `before`:
   ```bash
   T=$(mktemp); cp "$(git rev-parse --git-path index)" "$T"; GIT_INDEX_FILE="$T" git add -A; GIT_INDEX_FILE="$T" git write-tree; rm -f "$T"
   ```
4. **Fix pass.** Launch a subagent whose prompt contains the task's Intent, the diagnosis, the findings, the affected files, the violated rule sections, the matching pattern file, and every earlier attempt at these findings with why it failed. Its instructions: make the smallest change at the root cause; prefer changing or removing code to adding it; change nothing else; never weaken, skip or delete a test; report which files each fix changed. If the fix seems to need a new file, class, abstraction, configuration option or dependency, or a special case that only silences the symptom, make no edit and return `NEEDS_DECISION: <what and why>`. On `NEEDS_DECISION`, go to step 7.
5. **Re-review.** Snapshot again as the cycle's `after`, then run `/qc`. Append to `## QC` the verdict, the cycle number, the diagnosis, both tree ids and `git diff --shortstat <before> <after>`, before the next cycle starts.
6. **Judge the attempt.** PASS: stop.
   - A finding that was not in the previous verdict, in a file the fix changed, means the attempt made things worse: undo it and go to step 7.
   - A finding that survived means the attempt did not work: undo it, diagnose again, and try once more with the failed attempt in the prompt. If it survives the second attempt, undo that too and go to step 7, because the diagnosis is what is wrong.
   - Otherwise continue from step 2 with what remains.
   To undo, take the files the attempt changed from `git diff --name-status --no-renames <before> <after>`: delete each one marked `A`, and run `git restore --source=<before> --worktree -- <file>` for the rest. Undoing a shared file also undoes any other fix in it, so that fix is tried again. The `after` tree id stays in the task doc, so the attempt can be recovered until git prunes it. After any undo, run `/qc` once more so the last verdict describes the code on disk.
7. **Stop and report.** Print each cycle (findings, diagnosis, files, diff size, undone or kept) and say what remains and what the user must decide, without softening it, naming the task doc's file. The budget is `--max-cycles` per task, default 3 and hard maximum 5, counted from the cycles already in `## QC`, so running `/qc-fix` again continues the count instead of resetting it. An undone attempt counts. Reaching the budget also leads here.

**`evolve`** — re-analysis and rule maintenance. Frontmatter:
```yaml
---
name: evolve
description: "Re-analyzes the codebase and updates the governance layer. Detects drift, applies rule candidates from closed tasks, keeps rule files scoped and small, bumps the governance version."
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---
```
It re-runs Steps 1-3, diffs against the stored manifest, reads `## Rule Candidates` entries from task docs closed since `last_evolved`, proposes rule and pattern changes, and on acceptance updates the files, `governance.version`, `last_evolved`, and the changelog per `.claude/skills/evolve/changelog-spec.md`. Pack sections between `<!-- pack:... -->` markers are compared with the originals the scaffold copied to `.claude/packs/<name>/` and updated only when not customized.

It MUST include a **telemetry** step before proposing anything. Run the aggregator, exactly as written and without changing directory, for the window since the last evolve:
```bash
python .claude/scripts/report_data.py --project "${CLAUDE_PROJECT_DIR}" --since <governance.last_evolved or the initialized date>
```
confirm the output's `claude_dir` is this project's, and read from it: `tasks.rule_candidates.items` (lessons that `/close-task` filed as rule candidates since the last evolve), `hooks[].top_files` and `top_reasons` (where the guards keep firing), `tasks.scope_coverage` and `tasks.thesis_coverage`, `verification.data_gates`, and `rules` (sizes and scoping). Then read the `## Suppressions` tables of the task docs in the window. Turn these into proposals through the same approval flow as drift, each citing its evidence:
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
Before creating a task doc, check for another active one (`status: open` or `in_progress`). The scope guard reads only the most recently modified active doc, so a second active task silently changes which scope is enforced: ask the user to close the other task or set its status to `paused` first, and refuse to create a second active doc otherwise.

New task docs go in `.claude/<task_docs.directory>/YYYY-MM-DD-slug.md` with `status: open` and `base_commit: <output of git rev-parse HEAD>` near the top, and these sections, in this order, using the heading names from `task_docs.headings` for scope and thesis:
- `## Intent`
- `## <scope heading>` — one path per line, as a markdown list, naming the files this task may write to (`- src/billing/**`; a bare directory means everything under it). The `scope-guard` hook denies writes outside this list while the task is active, and also writes to the governance files under `.claude/` (rules, patterns, skills, scripts, agents, settings, manifest) unless the list names them, so a task that is meant to change a rule writes `- .claude/rules/**` here. The denial tells the model to either log the discovery under Implementation or extend this list as a visible decision. Preflight proposes the initial globs.
- `## <thesis heading>` — three labelled lines:
  ```markdown
  **Claim:** <one sentence, from the user's point of view, that is false until this task ships>
  **Observable:** <the exact output, screen, row, or response that shows the claim is true>
  **Demonstrated:**
  ```
  `Demonstrated:` stays empty until `/close-task` runs the demonstration; when filled it starts with the timestamp and says how: `2026-10-30T10:00Z via /verify: <what was observed>` for a run, or `2026-10-30 attested by <who>: <where it was seen>` when a person saw it somewhere the session cannot reach. A date on its own does not count. A task with no user-visible outcome (a refactor, a dependency bump, tooling) writes `no-user-observable-change: true` on its own line near the top instead of this section, with one sentence under Intent saying why; a task whose outcome exists but cannot be shown from this machine (needs production data, a deployed environment, a scheduled job) writes `cannot-demonstrate-here: <reason>` and keeps the section for an attestation.
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
1. **A review has run on the final code.** `## QC` holds a `QC_VERDICT` with `files_reviewed` above zero and a `reviewed_at` later than the last change to any file in the task's scope (`git log -1 --format=%cI -- <scope paths>`, and the working tree has no newer uncommitted change to them), and it is not BLOCK. An empty QC section, a verdict that reviewed nothing, or one older than the code refuses close: run `/qc` first.
2. The Implementation section is not empty, and every Suppressions row has a reason.
3. **The thesis is demonstrated.** If the doc carries `no-user-observable-change: true`, skip this check and say so. Otherwise read the `## <thesis heading>` section:
   - If it is missing, or Claim or Observable is empty: refuse to close. Ask the author for the claim and the observable, or for one of the opt-out lines with a reason.
   - If `Demonstrated:` is empty and the doc does not carry `cannot-demonstrate-here`: invoke the bundled `/verify` skill with the Claim as what to confirm and the Observable as the acceptance criterion. If it confirms the observable, write `**Demonstrated:** <ISO 8601 timestamp> via /verify: <one line on what was observed>` into the section. If it cannot confirm it, refuse to close and report exactly what differed from the Observable, without softening it.
   - If the doc carries `cannot-demonstrate-here: <reason>` and `Demonstrated:` is empty: ask the user whether they have seen the Observable somewhere (staging, production, a colleague's run). If yes, write `**Demonstrated:** <date> attested by <their name>: <where>`; if no, refuse to close.
   - If `Demonstrated:` already starts with a date followed by `via` or `attested by`, accept it. A bare date, or a date with no "how", does not count: treat it as empty.
   Never fill in `Demonstrated:` without a run that showed the Observable or a named person who did.
Then: record the commit reference, write `## Lessons`, add any lesson that should become a permanent rule under `## Rule Candidates` as a markdown list (one item per candidate: tier, proposed wording, the task that motivated it), set `status: closed`, update the task index.

### 4d. Pattern files

For each archetype sampled in Step 2, hydrate `pattern_template` (from the scaffold output) into `.claude/patterns/<archetype>.md`. Use the project's own archetype names for the file names (`handler.md`, `entity.md`, `migration.md`, `test.md`, `component.md`, `job.md`, ...). The canonical example is real code from this project, copied verbatim with its path.

### 4e. Rule files

Hydrate the three templates in `rule_templates_dir` (from the scaffold output) into `.claude/rules/security.md`, `.claude/rules/architecture.md`, `.claude/rules/conventions.md`, replacing every `{{placeholder}}` and resolving every `{{#if}}` / `{{#each}}` block. No template syntax may remain in the output: Claude Code auto-loads `.claude/rules/` and literal `{{` in a loaded rule file breaks it.

Claude Code reads the `paths:` frontmatter natively: a rule file with `paths:` is loaded only when a matching file is read or edited; a file without `paths:` is always loaded.
- `security.md`: no `paths:` frontmatter. Always loaded.
- `architecture.md` and `conventions.md`: set `paths:` to the source globs from Step 1 so the rules load when source files are touched and stay out of context otherwise.

Keep each rule file under 12 KB. If the project has more to say, make another scoped file rather than a longer one.

**Per-module rule files.** When `architecture.modules` has more than one entry, write one `.claude/rules/<module>.md` per module with `paths: ["<module path>/**"]` (the manifest's `modules[].path` is a directory; the rule file needs the glob), holding only what is specific to that module: its allowed imports from `boundaries.modules_may_import`, its own conventions, and any security checks whose `paths` fall inside it. The shared architecture and conventions files keep what applies everywhere. A module file with nothing specific to say is not written.

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

You review changes in <project name> against the rules in `.claude/rules/` and the manifest in `.claude/manifest.json`. You never create, edit, move or delete a file, through any tool, including shell redirection. Bash is for `git diff`, `git diff --cached`, `git status`, `git log`, and the project's test command (`<verification.test_command>`), nothing else. You report every violation with file, line, rule ID, and the rule section; you never downgrade a finding; you skip a finding only when the active task doc's Suppressions table lists its rule ID. Your entire result is one QC_VERDICT block.
```
Fill in the project name and the test command (omit the test-command clause when the manifest has none). Bash is not sandboxed inside the subagent: the write prohibition is a rule the reviewer follows, not a wall, and the scope guard does not see Bash writes. Keep the agent's tools to Read, Glob, Grep, Bash.

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
7. If the user wants a hook off, the way is `governance.disabled_hooks` in the manifest (hook names without `.py`), then `--update`. Deleting a hook entry from settings.json by hand makes the self-test fail on purpose.

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
