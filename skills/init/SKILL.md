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

Do NOT re-analyze. Do NOT touch preflight, qc, evolve, close-task, rules, or patterns.

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
10. **Governance workflow**: one line each for `/preflight`, `/task-doc`, `/qc`, `/close-task`, `/evolve`, `/clauding-thought:report`, where the detailed rules live (`.claude/rules/`, `.claude/patterns/`), and the hooks in force: writes outside the active task's `## Scope` are denied, claims about data need a declared gate, test claims need test output.

Keep it under 200 lines. Detail belongs in the rule files.

### 4c. Skills

Generate five project-customized skills in `.claude/skills/<name>/SKILL.md`. Each has YAML frontmatter and full agent logic in the body, ends with `$ARGUMENTS`, and references this project's actual files, globs, and rule IDs.

**`preflight`** — context brief before coding. Frontmatter:
```yaml
---
name: preflight
description: "Gathers context before coding. Classifies the task, loads the relevant rules and patterns, finds sibling files, identifies risks, proposes the task's scope."
argument-hint: "<task description>"
user-invocable: true
allowed-tools: ["Read", "Glob", "Grep", "Bash"]
---
```
It classifies the task by archetype, loads only the matching rule sections and pattern files, lists sibling files to imitate, names the security surface, proposes the path globs the task will need (these become the task doc's scope section), and recommends a task doc when the change meets `task_docs.auto_create_threshold`.

**`qc`** — post-generation review. Frontmatter:
```yaml
---
name: qc
description: "Quality control review. Evaluates uncommitted changes against the manifest-driven security, architecture, and convention rules. Returns a QC_VERDICT."
argument-hint: "[--diff | --full]"
user-invocable: true
allowed-tools: ["Read", "Glob", "Grep", "Bash"]
---
```
The body MUST embed these behavioural rules:
1. **Report, don't judge.** Report each violation with its rule ID and severity. Never downgrade a finding as "acceptable", "a deliberate tradeoff", "minor", or "justified". The developer decides what to suppress.
2. **Rules are the source of truth.** If `.claude/rules/` says X and the code does Y, that is a violation. QC does not second-guess rules; `/evolve` changes them.
3. **Check suppressions, not intent.** The only reason to skip a finding is an entry in the active task doc's Suppressions table.
4. **Convention violations can be errors.** Read the inline `<!-- severity: -->` annotation; do not assume conventions are always warnings.
5. **Three tiers, one verdict.** Security, architecture, conventions, each with its own section. `manifest.security.posture` decides whether security findings BLOCK (strict) or WARN on baseline gaps (advisory). The verdict is PASS, WARN, or BLOCK.
6. **Append the verdict** to the active task doc's QC section when one exists.

Claude Code also ships `/code-review` and `/security-review`. QC does not replace them: it checks this project's declared rules; they hunt bugs and generic security issues. Mention both in the skill's closing note.

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
- `## Plan`
- `## Implementation` — running log of decisions, discoveries, and files changed
- `## QC` — verdicts appended by `/qc`
- `## Suppressions` — table: Rule ID, Reason
- `## Lessons`
- `## Closure`

Register the task in `<task_docs.directory>/INDEX.md`. On `update`, append to Implementation and never rewrite the scope list silently.

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
Pre-close checks: the latest QC verdict is not BLOCK; the Implementation section is not empty; every Suppressions row has a reason. Then: record the commit reference, write `## Lessons`, add any lesson that should become a permanent rule under `## Rule Candidates` (tier, proposed wording), set `status: closed`, update the task index.

### 4d. Pattern files

For each archetype sampled in Step 2, hydrate `pattern_template` (from the scaffold output) into `.claude/patterns/<archetype>.md`. Use the project's own archetype names for the file names (`handler.md`, `entity.md`, `migration.md`, `test.md`, `component.md`, `job.md`, ...). The canonical example is real code from this project, copied verbatim with its path.

### 4e. Rule files

Hydrate the three templates in `rule_templates_dir` (from the scaffold output) into `.claude/rules/security.md`, `.claude/rules/architecture.md`, `.claude/rules/conventions.md`, replacing every `{{placeholder}}` and resolving every `{{#if}}` / `{{#each}}` block. No template syntax may remain in the output: Claude Code auto-loads `.claude/rules/` and literal `{{` in a loaded rule file breaks it.

Claude Code reads the `paths:` frontmatter natively: a rule file with `paths:` is loaded only when a matching file is read or edited; a file without `paths:` is always loaded.
- `security.md`: no `paths:` frontmatter. Always loaded.
- `architecture.md` and `conventions.md`: set `paths:` to the source globs from Step 1 so the rules load when source files are touched and stay out of context otherwise.

Keep each rule file under 12 KB. If the project has more to say, make another scoped file rather than a longer one.

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
- Skills: preflight, qc, evolve, task-doc, close-task
- Hooks: secret-filter, destructive-guard, scope-guard, anti-rationalization, evidence-check, claim-guard
```

### 4g. Settings and hooks

Already written by the scaffold. Do not write or edit `.claude/settings.json`; read it only if you need to verify it.

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
| 4 | `.claude/rules/{security,architecture,conventions}.md` | GENERATE by hydrating templates |
| 5 | `.claude/patterns/*.md` | GENERATE, one per archetype |
| 6 | `.claude/skills/{preflight,qc,evolve,task-doc,close-task}/SKILL.md` | GENERATE project-customized |
| 7 | `.claude/settings.json` | scaffold (verify, do not write) |
| 8 | `.claude/tasks/INDEX.md` | scaffold (verify) |
| 9 | `.claude/skills/evolve/changelog-spec.md` | scaffold (verify) |
| 10 | `.claude/scripts/*.py`, `.claude/selftest.json` | scaffold (verify the self-test passed) |

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
