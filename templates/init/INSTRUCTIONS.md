# Clauding Thought — Full Init Instructions

**IMPORTANT:** An existing root-level `CLAUDE.md` does NOT mean governance is initialized. Leave it alone. All generated files go inside `.claude/`.

## Step 0: SCAFFOLD — Create Directory Structure

Read `.claude/.plugin-root` to get the plugin installation path. Then run the scaffold script directly — it auto-resolves its own plugin root from `.plugin-root` or its file location, so no environment variables are needed:

```bash
python "<plugin_root_path>/scripts/scaffold.py"
```

If `$ARGUMENTS` contains `--update`, add `--update`:

```bash
python "<plugin_root_path>/scripts/scaffold.py" --update
```

If `.claude/.plugin-root` does not exist, look for the script at `~/.claude/plugins/cache/clauding-thought/` or ask the user.

The scaffold creates the directory tree, copies boilerplate skills, hook scripts, settings.json, and rule templates. Its JSON output tells you what was created and what remains. Save the output for reference in later steps.

## Update Mode

If the scaffold output showed `"mode": "update"`, do ONLY these steps:
1. Merge hooks into `.claude/settings.json` (preserve existing permissions)
2. Update `governance.plugin_version` in `.claude/manifest.json` to `plugin_version` from scaffold output
3. Add `[Unreleased]` changelog entry to `.claude/CHANGELOG.md`
4. Report what was updated, then STOP

Do NOT re-analyze. Do NOT touch preflight, qc, evolve, task-doc, close-task.

---

## Full Init — Steps 1 through 5

## Step 1: DETECT — Identify the Stack

Read these files to determine the technology stack:

**Package manifests** (read whichever exist):
- `composer.json` → PHP/Laravel
- `package.json` → Node/frontend frameworks
- `Cargo.toml` → Rust
- `go.mod` → Go
- `pyproject.toml` / `requirements.txt` → Python
- `Gemfile` → Ruby
- `pom.xml` / `build.gradle` → Java

**Framework markers**:
- `artisan` file → Laravel
- `next.config.*` → Next.js
- `nuxt.config.*` → Nuxt
- `manage.py` / `settings.py` → Django
- `config/routes.rb` → Rails

**Config files**:
- `.env.example` → environment variables and their shape
- Database config → DB type
- Auth config → authentication strategy
- `vite.config.*` / `webpack.config.*` → build tooling
- `tailwind.config.*` or CSS `@import "tailwindcss"` → Tailwind version
- `.prettierrc` / `pint.json` / `.editorconfig` → formatting conventions

**Directory structure**:
- Run a directory listing of the project root and key subdirectories
- Map the application layer structure

## Step 2: SAMPLE — Extract Patterns

For each file archetype, read 3-5 representative files and extract the common shape.

### File Archetypes to Sample

**Backend:**
- Controllers — authorization pattern, response style, dependency injection
- Models — traits used, relationships, casts, fillable/guarded, scopes
- Services/Actions — where business logic lives, dependency patterns
- Migrations — column conventions, foreign keys, indexes
- Form Requests / Validation — rule syntax, custom messages
- Policies / Gates — permission checking pattern
- Tests — setup style, assertion patterns, data creation

**Frontend:**
- Pages/Views — layout structure, data fetching, prop types
- Components — naming, composition, state management
- Forms — validation, submission, error handling
- API layer — how frontend calls backend

**For each archetype, record:**
1. The common structural elements (what's always present)
2. The naming conventions
3. The import patterns
4. The authorization/validation approach
5. One canonical example (the cleanest, most representative file)
6. The directory glob pattern where this archetype lives (e.g., `app/Http/Controllers/**`, `app/Models/**`, `database/migrations/**`). These become the `paths:` scope for rule files and `<!-- scope: -->` annotations.

## Step 3: ANALYZE — Understand Architecture

### Multi-Tenancy Detection
- Search for global scopes, tenant traits, or middleware that sets tenant context
- Check if models have a common tenant column (`organization_id`, `tenant_id`, `team_id`)
- Identify the isolation strategy

### Authorization Mapping
- How do controllers authorize? Per-method `$this->authorize()`, constructor middleware, or route middleware?
- Are there policies? Gates? An RBAC package?
- Is there an owner/admin bypass?

### Module Boundaries
- Are there distinct modules/domains in the codebase?
- What's the dependency graph between them?
- Is there a shared/core layer?

### Translation System
- How are translations handled?
- How many locales?
- Nested or flat keys?
- Are all locales always required?

### Data Flow
Map the request lifecycle:
```
Route → Middleware → Controller → [FormRequest] → Service → Model → [Resource] → Response
```
Which layers exist? Which are skipped?

### Delivery Patterns

Detect patterns where correctness alone is insufficient — where code can pass every test and yet fail to deliver user value. These become candidate rules for the `delivery` tier. Look for:

- **Route → navigation coupling:** Does the project have a navigation/menu component that should list user-visible routes? If so, a "new route added without a nav entry" is a delivery defect. Record which directories hold routes and which holds the nav component.
- **Cross-module seams:** Does any spec/task doc format in the project describe dependencies between modules (e.g., a `Depends on:` field, `## Seams` sections)? If so, multi-module work should name its producer/consumer explicitly before closing.
- **Localization touchpoints:** If `all_locales_required` is true, adding UI copy in one locale without updating the others is a delivery defect.
- **API contract drift:** If the project has a response-shape convention (DTOs, resources, Pydantic models), are there checks that new endpoints follow it?

If NO delivery patterns apply to this project (e.g., pure library, CLI, internal service with no UI), note that `delivery.checks` should remain empty. Do not invent rules.

**Record each detected pattern as a candidate check** with: id (e.g., `DELIV-001`), name, severity, description, detection approach, and affected paths. These go into `manifest.delivery.checks` in Step 4a.

## Step 3.5: CONFIGURE — Permission Mode

Ask the user:

> "Do you want to auto-accept tool calls? The governance hooks (secret-filter, destructive-guard) will still block dangerous operations in real-time. This removes the manual permission prompt for every Bash/Write/Edit call."

- If **yes** → set `auto_accept = true` in the manifest (Step 4a). The scaffold already created `settings.json` with auto-accept permissions and hooks.
- If **no** → set `auto_accept = false` in the manifest (Step 4a). Note: The scaffold created `settings.json` with auto-accept by default. Tell the user they can remove the `permissions` block from `.claude/settings.json` after init completes.

Record the choice for Step 4a.

## Step 3.6: CONFIGURE — Task-Doc Enforcement Opt-Ins

The plugin ships three opt-in gates that enforce task-doc conventions. All default to **off** — the plugin does not impose a convention the project has not explicitly adopted. Ask the user about each:

1. **Acceptance-criteria checkbox convention (`governance.enforcement.criteria_format`)**
   > "Do you want the anti-rationalization hook to block dismissal language (e.g., 'deliberate tradeoff', 'out of scope') whenever the active task doc has any unchecked `[ ]` acceptance-criteria items? This assumes tasks use markdown checkboxes under an `## Acceptance Criteria` heading."

2. **Deferral format (`governance.enforcement.deferred_format`)**
   > "Do you want to enforce the `[deferred:TASK-ID]` checkbox form for acceptance-criteria items that are pushed to follow-up work? Free-text deferrals ('will do later', 'follow-up task') are rejected; TASK-ID must resolve to a real task file or entry in `tasks/INDEX.md`."

3. **Cross-task deferral ledger (`governance.enforcement.ledger`)**
   > "Do you want `close-task` to refuse closures when the project-wide count of open `[deferred:TASK-ID]` items (excluding the closing task's own) exceeds a threshold? Default threshold is 3, configurable via `governance.deferred_threshold`. Only meaningful if you also enabled the deferral format above."

4. **Thesis demo on close (`governance.enforcement.thesis_demo`)**
   > "Do you want `close-task` to refuse closures on user-visible tasks unless the task doc contains a `## Thesis Demo` section (Claim + Script + Observable + a timestamped demonstration within the last 24 hours)? Infrastructure/refactor tasks can opt out per-task with `no-user-observable-change: true`. The `/thesis` skill authors the section interactively."

   **Dependency:** `thesis_demo` only fires on tasks that are "ready to close" — i.e., tasks whose `## Acceptance Criteria` section contains at least one checkbox and all checkboxes are `[x]` or `[deferred:TASK-ID]`. Tasks written as prose without a structured criteria section never trigger the thesis gate. If you want thesis enforcement and your project uses prose task docs, enable `criteria_format` as well so the author is nudged toward the checkbox structure.

5. **Ambient rule context on edits (`governance.enforcement.rule_context`)**
   > "Do you want a PreToolUse hook to re-emphasize relevant rule sections as `additionalContext` before each Edit/Write? Rules in `.claude/rules/` are auto-loaded once at session start; in long sessions they drift out of recency. This hook matches the file being edited against rule path globs and injects up to two most-specific matching sections (~200-400 tokens per edit). Never blocks. Useful for projects where conversational fixes between formal tasks tend to introduce convention violations."

   **Cost:** every Edit/Write inside the project root pays a token tax. For a 50-edit session, expect ~10-20K extra tokens. When the flag is off, the hook still runs the matching and logs `decision: "skipped"` with which rules WOULD have been injected — so `/report` can show whether enabling it would surface useful content.

Decision defaults if the user declines to answer or is unsure:
- If the project has an existing `.claude/tasks/` directory with markdown checkboxes, suggest enabling `criteria_format`
- Only enable `deferred_format` / `ledger` if the user explicitly confirms — these require discipline around every deferral being a tracked task
- Only enable `thesis_demo` if the project ships user-visible features regularly. For internal/library projects, leave it off.
- `rule_context` is the lowest-stakes flag — never blocks, just re-emphasizes rules. Recommend enabling it on projects with extensive `.claude/rules/` content where conversational fixes are common. For projects where rules are sparse or already always-loaded by virtue of short sessions, leave it off — the token cost is real.

Record all five answers for Step 4a. Each becomes a boolean under `governance.enforcement.<name>` in `manifest.json`.

When all flags stay off, the hooks still run but log their findings as `decision: "skipped"` in `.claude/hook-log.jsonl`. Run `/report` to see what each disabled gate WOULD have caught — that's the validation signal for deciding whether to enable. Users can promote flags to true later by editing `manifest.json` directly or re-running `/init --update`.

## Step 3.7: DISCOVER — Rule Packs

Check if packs exist in `~/.claude/clauding-thought/packs/` (or `<plugin_root>/packs/` if the scaffold output included a `plugin_root`):
1. Read each `packs/*/pack.json`
2. Filter by `stack_filter`: A pack matches if `stack_filter` is absent/empty (universal pack), or ALL non-empty filter arrays match — `stack_filter.language` (if non-empty) must contain the detected `stack.language`, AND `stack_filter.framework` (if non-empty) must contain the detected `stack.framework`. An empty array means "no constraint" for that dimension.
3. Present matching packs to the user:

   > "These community rule packs match your stack:
   > - **owasp-top-10** v1.0.0 — OWASP Top 10 security rules for web applications
   > - (other matching packs)
   >
   > Apply all / select specific / skip?"

4. Record the user's selection for Steps 4a and 4e.

If no packs match or the `packs/` directory doesn't exist, skip silently.

## Step 3.8: LEARN — Read Cross-Project Insights

Check whether the plugin has accumulated cross-project intelligence that can improve this project's initial governance.

1. Read `~/.claude/clauding-thought/insights/patterns.md` and `~/.claude/clauding-thought/insights/hook-candidates.md`
   - If neither file exists or both are empty, skip this step silently. This is expected for first-time installations or fresh plugin installs.

2. If data exists, extract recommendations relevant to the detected stack from Step 1:
   - Filter for patterns matching `stack.language` and `stack.framework`
   - Identify universal patterns (flagged as "across all stacks")
   - Identify stack-specific patterns

3. **Adjust security posture recommendation:**
   - If cross-project data shows this stack commonly has security violations that led to BLOCK verdicts, bias toward `strict` posture even for existing codebases
   - If data shows mostly WARN-level findings, `advisory` may be appropriate

4. **Pre-populate security checks:**
   - If cross-project findings show specific rules are frequently violated for this stack, add corresponding entries to `security.checks` in the manifest (Step 4a)
   - Include `"source": "cross-project-insights"` in the check's description field so they are distinguishable from checks derived from codebase analysis

5. **Record pack recommendations for Step 4a:**
   - If cross-project patterns suggest a specific pack addresses common violations for this stack, note the pack name and reason. In Step 4a, if the user did not already select this pack in Step 3.7, add a comment in the generated manifest noting the recommendation for the next `/evolve` run.

6. **Note in CLAUDE.md:**
   If cross-project insights influenced the configuration, add a section to the generated CLAUDE.md (Step 4b):
   ```markdown
   ## Cross-Project Insights Applied

   This governance layer was informed by anonymized findings from other projects:
   - <insight 1>: <how it influenced this project's rules>
   - <insight 2>: <how it influenced this project's rules>

   These can be reviewed and customized via `/evolve`.
   ```

If `~/.claude/clauding-thought/insights/` does not exist, skip this step silently.

## Step 4: GENERATE — Build the Governance Layer

Using your analysis, generate the following files. Each must be specific to THIS project — no generic boilerplate.

### 4a. `.claude/manifest.json`
Fill in every field you can confidently determine. Use `null` for fields you cannot determine. Follow the schema at `.claude/skills/init/manifest.schema.json`.

Set `version` to `"1.1"` (the current schema version supporting path-scoped rules and severity levels).

Include the `governance` block:
```json
{
  "governance": {
    "version": "1.0.0",
    "initialized": "<today's date>",
    "last_evolved": null,
    "changelog": "CHANGELOG.md",
    "auto_accept": true | false,
    "plugin_version": "<version from scaffold output>",
    "deferred_threshold": 3,
    "enforcement": {
      "criteria_format": false,
      "deferred_format": false,
      "ledger": false,
      "thesis_demo": false,
      "rule_context": false
    },
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
    "checkpoint_interval": 30
  }
}
```

Set each `governance.enforcement.*` flag to the value the user chose in Step 3.6. Defaults are `false` — do not turn a flag on unless the user explicitly opted in.

Populate `governance.packs` with the packs selected in Step 3.7 (empty array `[]` if none selected).

When generating `security.checks`, include a `paths` array on each check based on what it targets:
- Auth bypass checks → controller and route directory globs from Step 2
- Tenant isolation checks → model and validation/form-request directory globs
- Data exposure checks → controller and resource/serializer directory globs
- Injection checks → all backend code paths (broad scope, or omit `paths` for all files)
- Secrets checks → omit `paths` (applies to all files)

Use the unified severity vocabulary: `error` for active vulnerability checks, `warning` for potential risk checks, `info` for informational/hygiene checks. Do NOT use the legacy `block`/`warn` values.

### 4b. `.claude/CLAUDE.md`
Generate the governance rules document at `.claude/CLAUDE.md`, structured as:
1. **Overview** — one paragraph describing what this project is
2. **Module System** — if modules exist, how they work
3. **Multi-Tenancy** — if tenancy exists, the critical rules (MUST use trait, scope column, etc.)
4. **Authorization** — the patterns with code examples from the actual codebase
5. **Data Exposure Prevention** — what to never expose, how to serialize
6. **Translation System** — how it works, locales required
7. **Service Layer** — where business logic goes
8. **Security Enforcement** — blocking rules that must never be violated
9. **Pre-Commit Checklist** — ordered list of checks before finishing
10. **Memory Management** — include the following section verbatim:

```markdown
## Memory Management

`.claude/memory/MEMORY.md` is auto-loaded into every session but **only the first 200 lines are read**. When MEMORY.md approaches 200 lines:

1. Move detailed content into topic files in `.claude/memory/`:
   - `security-lessons.md` — security-related findings and lessons
   - `architecture-decisions.md` — architectural patterns and decisions
   - `convention-notes.md` — coding convention insights
2. Replace the moved content in MEMORY.md with a one-line link: `- See [topic-file.md](memory/topic-file.md) for details`
3. Keep MEMORY.md under 200 lines with only the most critical facts and links

Do this proactively when adding new lessons — don't wait for it to break.
```

### 4c. Agent Skills

Generate the 5 project-customized skills in `.claude/skills/`. Each skill is a directory containing a `SKILL.md` with YAML frontmatter and full agent logic. After init, all skills are project-local and available in VS Code autocomplete.

**`.claude/skills/preflight/SKILL.md`** — generates a context brief before code generation. Must reference the manifest to load the right rules and patterns. Include frontmatter:
```yaml
---
name: preflight
description: "Gathers context before coding. Classifies the task, loads relevant rules and patterns, finds sibling files, identifies risks."
argument-hint: "<task description>"
user-invocable: true
allowed-tools: ["Read", "Glob", "Grep", "Bash"]
---
```

If `governance.enforcement.ledger` is true in the manifest, the generated preflight skill MUST count open `[deferred:TASK-ID]` items across `.claude/tasks/*.md` (excluding INDEX.md and closed task docs, and excluding the current task's own deferrals) before issuing its brief. If the count exceeds `manifest.governance.deferred_threshold` (default 3), prepend a warning to the brief:

> Deferred-item ledger at N items (threshold M). `/close-task` will refuse new closures until the ledger drops below the threshold. Consider resolving existing deferrals before starting new work.

If `ledger` is false, omit this check entirely — the project has not opted into ledger enforcement.

**`.claude/skills/qc/SKILL.md`** — post-generation review. Security checks derived from the manifest's tenancy, auth, and exposure rules. Architecture checks from module boundaries. Convention checks from conventions section. Delivery checks from `manifest.delivery.checks` and `rules/delivery.md` (may be empty for projects without user-visible surface). Include frontmatter:
```yaml
---
name: qc
description: "Quality control review. Evaluates uncommitted changes against manifest-driven security, architecture, and convention rules."
user-invocable: true
allowed-tools: ["Read", "Glob", "Grep", "Bash"]
---
```

The generated QC skill MUST include these behavioral rules in its body:

1. **Report, don't judge.** When a rule violation is found, report it with the correct severity. Do NOT downgrade findings by calling them "acceptable", "a deliberate tradeoff", "minor", or "justified". The developer decides what to suppress — QC reports facts.
2. **Rules are the source of truth.** If `.claude/rules/` says X and the code does Y, that is a violation. QC does not second-guess rules. If a rule is wrong, `/evolve` fixes it — QC enforces what exists.
3. **Check suppressions, not intent.** The only reason to skip a finding is if it appears in the active task document's Suppressions table. "The developer probably meant to do this" is not a valid reason to skip.
4. **Convention violations can be errors.** If a convention rule has `<!-- severity: error -->`, it BLOCKs. Do not assume conventions are always warnings — read the inline severity annotation.
5. **Load all four tiers.** Security, architecture, conventions, AND delivery. Each has its own rules file and its own section in the verdict. The delivery tier may be empty — report it as "delivery: no checks defined" in that case, not as absent.
6. **Respect posture fields.** `manifest.security.posture` and `manifest.delivery.posture` each take values `strict` or `advisory`. `strict` means violations in that tier emit BLOCK verdicts; `advisory` means WARN only. Convention severity is always per-rule (via inline annotations); architecture severity is per-rule too. Security defaults to strict for new projects, advisory for existing. Delivery defaults to advisory.

**`.claude/skills/evolve/SKILL.md`** — re-analyzes the codebase and updates the manifest and rules. Include frontmatter:
```yaml
---
name: evolve
description: "Re-analyzes the codebase and updates the governance layer. Detects drift, suggests rule changes, bumps version."
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---
```

**`.claude/skills/task-doc/SKILL.md`** — creates and maintains per-task documents through their lifecycle. Include frontmatter:
```yaml
---
name: task-doc
description: "Creates or updates a task document for the current work. Tracks decisions, files changed, QC verdicts."
argument-hint: "<task description or 'update'>"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---
```

If `governance.enforcement.criteria_format` OR `governance.enforcement.deferred_format` is true, the generated task-doc skill MUST use the following acceptance-criteria format in new task templates:

```markdown
## Acceptance Criteria

- [ ] Criterion one — unchecked, blocks close
- [x] Criterion two — done
- [deferred:TASK-YYYYMMDD-slug] Criterion three — tracked in a separate task
```

Rules the generated skill MUST embed when the corresponding flag is on:

1. **(`deferred_format`) Only three marker forms are valid:** `[ ]`, `[x]`, and `[deferred:TASK-ID]`. Free-text deferrals ("to be done later", "follow-up task", "deferred — tracked for next sprint") are rejected by the `deferral-check` hook.
2. **(`deferred_format`) Deferred TASK-IDs must resolve.** Before writing a `[deferred:TASK-ID]` line, create the follow-up task file or add the TASK-ID to `tasks/INDEX.md`. Dangling references are blocked at Stop.
3. **Suppressions table is separate from acceptance criteria.** Rule suppressions go in the `## Suppressions` table with rule_id + reason; acceptance criteria track functional deliverables. (Always — this is a structural separation, not an enforcement concern.)

When all three flags are off, the task-doc skill may still offer the checkbox format as a *convention* (because the hook logs a `decision: "skipped"` entry for any violations it would have flagged) but must not present it as mandatory.

**`.claude/skills/close-task/SKILL.md`** — finalizes task documents and promotes lessons to memory. Include frontmatter:
```yaml
---
name: close-task
description: "Finalizes the active task document. Records commit reference, captures lessons learned, promotes learnings to memory."
argument-hint: "[optional: lessons learned]"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---
```

The generated close-task skill MUST enforce these pre-close checks in order. Each check is conditional on its enforcement flag:

1. **(`criteria_format`) All acceptance criteria resolved.** Every item in `## Acceptance Criteria` must be `[x]` or `[deferred:TASK-ID]`. Unchecked `[ ]` items block the close.
2. **(`deferred_format`) Deferrals well-formed.** Every `[deferred:TASK-ID]` references a real task file or INDEX.md entry; no free-text deferrals in checkbox lines.
3. **(`ledger`) Deferred-item ledger under threshold.** Sum all open `[deferred:TASK-ID]` lines across non-closed task docs, *excluding* the current task's own deferrals. Refuse to close the current task if the sum exceeds `manifest.governance.deferred_threshold` (default 3). If the ledger is intentionally high, the developer raises the threshold in the manifest — the skill does not override.
4. **(`thesis_demo`) Thesis Demo present and fresh.** The task must have a `## Thesis Demo` section with Claim, Script, Observable subsections AND a `**Demonstrated:**` timestamp within the last 24 hours. Exception: tasks with `no-user-observable-change: true` in frontmatter or a `## No User-Observable Change` section skip this check. Direct the user to run `/thesis` if the section is missing.
5. **QC verdict must not be BLOCK.** Existing rule — always enforced regardless of flags.

The `deferral-check` and `thesis-check` hooks on Stop enforce checks 2, 3, and 4 independently of the skill when their flags are on (and log `decision: "skipped"` when off). The skill's role is to report what would block *before* requesting the close and give the developer a clear path to resolution.

**Boilerplate skills** — Already copied by the scaffold script. These are: export, report, insights, critique, thesis (SKILL.md files) and evolve/changelog-spec.md. Do NOT regenerate these — they are already in place.

### 4d. Pattern Files
For each archetype sampled in Step 2, generate a pattern file showing:
- The canonical structure (annotated)
- Required elements (must always be present)
- Variable elements (change per instance)
- Anti-patterns (what NOT to do, based on project conventions)

### 4e. Rule Files

The scaffold script copied rule templates to `.claude/rule-templates/` (NOT `.claude/rules/` — Claude Code auto-loads `rules/` and `{{}}` syntax crashes it). Hydrate them into `.claude/rules/` by replacing placeholders with project-specific content:

**`rules/security.md`** — derived from manifest.security + tenancy + auth analysis
**`rules/architecture.md`** — derived from manifest.boundaries + layers
**`rules/conventions.md`** — derived from manifest.conventions + sampled patterns
**`rules/delivery.md`** — derived from manifest.delivery + Step 3 delivery-pattern detection. If no delivery checks were detected, hydrate the template with an empty checks list — the file exists but contains only the structural scaffold, which is the correct state for projects without user-visible delivery concerns.

When hydrating templates, populate:
- `paths:` YAML frontmatter with the directory globs detected in Step 2 for each rule category
- `default_severity:` in frontmatter: `error` for security, `warning` for architecture, `warning` for conventions
- `<!-- scope: -->` inline annotations using the archetype-specific globs from Step 2 (e.g., `<!-- scope: app/Http/Controllers/** -->` on the Authentication section)
- `<!-- severity: -->` inline annotations on sections that deviate from the file-level default (e.g., Migration Safety gets `error` even though architecture defaults to `warning`)

**Pack rule merging:** For each pack selected in Step 3.7, read the pack's rule files and append them to the target rule file as clearly-delimited sections:
```markdown
<!-- pack:<pack-name>:<section-id>:start -->
## Section Title
[pack rule content]
<!-- pack:<pack-name>:<section-id>:end -->
```

Also append any `security_checks` from the pack's `pack.json` to the manifest's `security.checks` array.

### 4f. Changelog

Create `.claude/CHANGELOG.md` with the initial `[1.0.0]` entry:

```markdown
# Changelog

All notable changes to this project's governance layer are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [1.0.0] - <today's date>

### Added
- Initial governance layer generated by `/init`
- Manifest: <brief summary of what was detected>
- Security rules: <list key checks>
- Architecture rules: <list key boundaries>
- Convention rules: <list key conventions>
- Pattern files: <list generated patterns>
- Agent skills: preflight, qc, evolve, task-doc, close-task, export, report, insights, critique, thesis
- Hook scripts: secret-filter, destructive-guard, anti-rationalization, evidence-check, skill-reminder
- Governance hooks configured in settings.json
- Task document system with auto-creation and index
```

### 4g-4h. Task Index and Memory

Already created by the scaffold script. No action needed.

### 4i. Settings and Hooks

**DO NOT write `.claude/settings.json`** — it was already created by the scaffold script with hooks and permissions. Writing settings.json mid-session crashes Claude Code.

If you need to verify it exists, read it, but never write or edit it.

### 4k. Hook Scripts

Already copied by the scaffold script. Do NOT copy or regenerate.

### 4j. File Storage Detection

If the project has filesystem/storage configuration (e.g., `config/filesystems.php`, S3 config in environment, `MEDIA_ROOT` in Django settings), populate `architecture.file_storage` in the manifest:
- `disk`: the default storage disk (e.g., `"private"`, `"public"`, `"s3"`)
- `auth_required`: whether file downloads require authentication

If no filesystem configuration is detected, omit the `file_storage` field.

## Step 5: VERIFY — Calibrate

After generating all files:
1. Pick 3 existing files from the codebase
2. Run your generated QC rules against them mentally
3. They should PASS (since they're existing, presumably correct code)
4. If they would WARN or BLOCK, your rules are too strict — adjust

## Output

**Completion checklist — verify ALL of these exist before finishing:**

| # | File | Your job |
|---|------|----------|
| 1 | `.claude/manifest.json` | **GENERATE** from analysis |
| 2 | `.claude/CLAUDE.md` | **GENERATE** from analysis |
| 3 | `.claude/CHANGELOG.md` | **GENERATE** (Step 4f) |
| 4 | `.claude/settings.json` | scaffold (DO NOT write — verify exists) |
| 5 | `.claude/rules/security.md` | **GENERATE** by hydrating template |
| 6 | `.claude/rules/architecture.md` | **GENERATE** by hydrating template |
| 7 | `.claude/rules/conventions.md` | **GENERATE** by hydrating template |
| 7a | `.claude/rules/delivery.md` | **GENERATE** by hydrating template (empty checks OK) |
| 8 | `.claude/patterns/*.md` | **GENERATE** from code samples |
| 9 | `.claude/skills/preflight/SKILL.md` | **GENERATE** project-customized |
| 10 | `.claude/skills/qc/SKILL.md` | **GENERATE** project-customized |
| 11 | `.claude/skills/evolve/SKILL.md` | **GENERATE** project-customized |
| 12 | `.claude/skills/task-doc/SKILL.md` | **GENERATE** project-customized |
| 13 | `.claude/skills/close-task/SKILL.md` | **GENERATE** project-customized |
| 14 | `.claude/tasks/INDEX.md` | scaffold (verify exists) |
| 15 | `.claude/memory/MEMORY.md` | scaffold (verify exists) |
| 16 | `.claude/memory/decisions.md` | scaffold (verify exists) |
| 17-21 | `.claude/skills/{export,report,insights,critique,thesis}/SKILL.md` | scaffold (verify exists) |
| 21 | `.claude/skills/evolve/changelog-spec.md` | scaffold (verify exists) |
| 22-27 | `.claude/scripts/*.py` (6 files) | scaffold (verify exists) |

Items 1-3 and 5-13 are YOUR responsibility to create. Item 4 and items 14-27 were created by the scaffold script — verify they exist but do NOT recreate them. Report what you created and any manifest fields you couldn't determine (marked as `null`).

## Security Posture Detection

During Step 3 (ANALYZE), determine whether this is a new or existing project:

**New project** (few or no controllers, models, routes):
- Set `security.posture` to `"strict"`
- All security rules are BLOCKING from day one
- No baseline gaps — the project starts clean

**Existing project** (established controllers, models, routes, patterns):
- Set `security.posture` to `"advisory"`
- Scan the codebase for security gaps and record them in `security.baseline_gaps`
- Each gap gets an id, category, description, affected files, mitigation suggestion, and severity
- New code MUST still follow strict security rules — advisory only applies to existing patterns
- The gap list serves as a migration backlog toward full strict posture

**Critical distinction:** Advisory posture does NOT mean security is optional. It means:
- New code: always strict. Every new controller, model, route must meet security rules.
- Existing code: gaps are documented, not ignored. Mitigation tasks are suggested.
- The goal is always to reach strict. Advisory is the on-ramp, not the destination.

**Gap categories to scan for:**
- `auth` — controllers/routes without authorization
- `tenancy` — models with tenant column but no scoping trait
- `exposure` — raw models passed to views without field selection
- `injection` — raw SQL without bindings
- `secrets` — hardcoded credentials or direct `env()` usage outside config
- `file-access` — public disk for user uploads, downloads without auth checks
- `csrf` — forms without CSRF protection
- `session` — insecure cookie/session configuration

## Important Principles

- **Be specific, not generic.** Every rule should reference patterns actually found in THIS codebase.
- **Extract, don't invent.** Your rules should codify what the project already does, not impose external opinions.
- **Err on the side of fewer rules.** Ten precise rules beat fifty vague ones.
- **Use real code examples.** Pattern files should contain actual code from the project, not hypothetical examples.
- **Security is non-negotiable.** Even non-public apps must follow strict security practices — exposure status changes, internal threats exist, and compliance audits happen. The posture setting controls enforcement style (block vs advise), not whether security matters.
