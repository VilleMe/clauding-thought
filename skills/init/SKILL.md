---
name: init
description: "Bootstrap governance layer. Analyzes the codebase and generates manifest.json, CLAUDE.md, rules, patterns, skills, and changelog. Run this first on any new project."
argument-hint: "[--update | optional: specific focus area]"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---

You are the Clauding Thought bootstrap agent. Follow the numbered steps below IN ORDER. Do not skip ahead. Do not start reading project files until you have completed Steps 0 and 0.5.

**IMPORTANT:** An existing root-level `CLAUDE.md` does NOT mean governance is already initialized. You are generating a completely separate `.claude/` directory with 27+ files. The root `CLAUDE.md` is irrelevant — leave it alone.

## YOUR FIRST ACTION — Step 0: Resolve Plugin Root

**Do this RIGHT NOW before reading any project files.** Run this Bash command:

```bash
echo "PLUGIN_ROOT=$CLAUDE_PLUGIN_ROOT" && echo "SKILL_DIR=$CLAUDE_SKILL_DIR"
```

The output gives you the plugin installation directory. Store it as `PLUGIN_ROOT`. You need this path to copy boilerplate skills, scripts, and rule templates later.

If `CLAUDE_PLUGIN_ROOT` is empty, use `CLAUDE_SKILL_DIR` and go two directories up (the skill is at `skills/init/` relative to the plugin root).

**CRITICAL:** If neither resolves to a valid path, stop and tell the user: "Cannot resolve plugin root directory. Try running `/init` from the terminal (not VS Code chat panel) or reinstall the plugin."

## Step 0.5: Create Directory Skeleton

**Do this IMMEDIATELY after Step 0.** Run:

```bash
mkdir -p .claude/skills/preflight .claude/skills/qc .claude/skills/evolve .claude/skills/task-doc .claude/skills/close-task .claude/skills/export .claude/skills/report .claude/skills/insights .claude/skills/critique .claude/rules .claude/patterns .claude/tasks .claude/memory .claude/scripts
```

This creates the `.claude/` directory tree. ALL generated files go inside `.claude/`. Do NOT write files to the project root (except you may leave an existing root CLAUDE.md untouched).

## Update Mode (`--update`)

Only if called with `--update` argument. Otherwise skip to Step 1.

Refreshes boilerplate without re-analyzing. Requires `.claude/manifest.json` to already exist.

1. Complete Steps 0 and 0.5 above
2. Verify `.claude/manifest.json` exists (if not, tell user to run full `/init` first)
3. Copy boilerplate skills from `${PLUGIN_ROOT}/templates/skills/{export,report,insights,critique}/SKILL.md` to `.claude/skills/{export,report,insights,critique}/SKILL.md`
4. Copy `${PLUGIN_ROOT}/templates/evolve/changelog-spec.md` to `.claude/skills/evolve/changelog-spec.md`
5. Copy all scripts from `${PLUGIN_ROOT}/scripts/` to `.claude/scripts/`
6. Merge hooks into `.claude/settings.json` (preserve existing permissions)
7. Update `governance.plugin_version` in manifest.json
8. Add `[Unreleased]` changelog entry
9. Report what was updated, then STOP

Do NOT update in `--update` mode: preflight, qc, evolve, task-doc, close-task (project-customized). Do NOT re-analyze.

---

## Full Init — Steps 1 through 5

You will: (1) analyze the project, (2) ask two questions, (3) generate 27+ files inside `.claude/`. The files:

| Category | Files |
|----------|-------|
| Config | `.claude/manifest.json`, `.claude/settings.json` |
| Docs | `.claude/CLAUDE.md`, `.claude/CHANGELOG.md` |
| Rules | `.claude/rules/security.md`, `architecture.md`, `conventions.md` |
| Patterns | `.claude/patterns/*.md` (one per archetype) |
| Skills | `.claude/skills/{preflight,qc,evolve,task-doc,close-task}/SKILL.md` (generated), `.claude/skills/{export,report,insights,critique}/SKILL.md` + `evolve/changelog-spec.md` (copied) |
| Scripts | `.claude/scripts/{secret-filter,destructive-guard,anti-rationalization,evidence-check,skill-reminder,hook_telemetry}.py` (copied) |
| Tasks | `.claude/tasks/INDEX.md` |
| Memory | `.claude/memory/MEMORY.md`, `.claude/memory/decisions.md` |

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

## Step 3.5: CONFIGURE — Permission Mode

Ask the user:

> "Do you want to auto-accept tool calls? The governance hooks (secret-filter, destructive-guard) will still block dangerous operations in real-time. This removes the manual permission prompt for every Bash/Write/Edit call."

- If **yes** → set `auto_accept = true`, will generate `.claude/settings.json` with permissions and hooks in Step 4i
- If **no** → set `auto_accept = false`, will generate `.claude/settings.json` with hooks only (no permission overrides)

Record the choice for use in Steps 4a and 4i. Note: `.claude/settings.json` is always generated because it contains the hook definitions.

## Step 3.7: DISCOVER — Rule Packs

Scan the plugin's `packs/` directory (at `${CLAUDE_PLUGIN_ROOT}/packs/`):
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

### 4a. `manifest.json`
Fill in every field you can confidently determine. Use `null` for fields you cannot determine. Follow the schema at `${CLAUDE_SKILL_DIR}/manifest.schema.json`.

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
    "plugin_version": "<version from plugin.json>",
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

Generate ALL 10 skills in the target project's `.claude/skills/` directory. Each skill is a directory containing a `SKILL.md` with YAML frontmatter and full agent logic. After init, all skills are project-local and available in VS Code autocomplete — no plugin dependency for daily use.

**Project-customized skills** — These are generated with project-specific content based on the codebase analysis. They should NOT be overwritten by `--update`:

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

**`.claude/skills/qc/SKILL.md`** — post-generation review. Security checks derived from the manifest's tenancy, auth, and exposure rules. Architecture checks from module boundaries. Convention checks from conventions section. Include frontmatter:
```yaml
---
name: qc
description: "Quality control review. Evaluates uncommitted changes against manifest-driven security, architecture, and convention rules."
user-invocable: true
allowed-tools: ["Read", "Glob", "Grep", "Bash"]
---
```

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

**Boilerplate skills** — These are copied verbatim from the plugin's `templates/skills/` directory. They are NOT project-customized and CAN be overwritten by `--update`. Use the resolved `PLUGIN_ROOT` from Step 0:

**`.claude/skills/export/SKILL.md`** — Copy from `${CLAUDE_PLUGIN_ROOT}/templates/skills/export/SKILL.md`. Exports governance rules to other AI coding tools (Cursor, Copilot, Windsurf).

**`.claude/skills/report/SKILL.md`** — Copy from `${CLAUDE_PLUGIN_ROOT}/templates/skills/report/SKILL.md`. Governance health report analyzing task history, QC verdicts, and evolution.

**`.claude/skills/insights/SKILL.md`** — Copy from `${CLAUDE_PLUGIN_ROOT}/templates/skills/insights/SKILL.md`. Cross-project intelligence — analyzes anonymized findings to identify patterns.

**`.claude/skills/critique/SKILL.md`** — Copy from `${CLAUDE_PLUGIN_ROOT}/templates/skills/critique/SKILL.md`. Adversarial code review that finds what QC misses.

**`.claude/skills/evolve/changelog-spec.md`** — Copy from `${CLAUDE_PLUGIN_ROOT}/templates/evolve/changelog-spec.md`. Referenced by the evolve skill for changelog formatting rules.

**How to copy:** For each boilerplate skill, Read the source file from `PLUGIN_ROOT` and then Write it to the `.claude/skills/` path. Example:
1. Read `<PLUGIN_ROOT>/templates/skills/export/SKILL.md`
2. Write the content to `.claude/skills/export/SKILL.md`

### 4d. Pattern Files
For each archetype sampled in Step 2, generate a pattern file showing:
- The canonical structure (annotated)
- Required elements (must always be present)
- Variable elements (change per instance)
- Anti-patterns (what NOT to do, based on project conventions)

### 4e. Rule Files

Generate rule files by hydrating the templates from `${CLAUDE_PLUGIN_ROOT}/rules/`:

**`rules/security.md`** — derived from manifest.security + tenancy + auth analysis
**`rules/architecture.md`** — derived from manifest.boundaries + layers
**`rules/conventions.md`** — derived from manifest.conventions + sampled patterns

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
- Agent skills: preflight, qc, evolve, task-doc, close-task, export, report, insights, critique
- Hook scripts: secret-filter, destructive-guard, anti-rationalization, evidence-check, skill-reminder
- Governance hooks configured in settings.json
- Task document system with auto-creation and index
```

### 4g. Task Index

Create `.claude/tasks/INDEX.md`:

```markdown
# Task Index

| Date | Task | Status | Module | Commit |
|------|------|--------|--------|--------|
```

### 4h. Memory Directory

Create `.claude/memory/MEMORY.md`:

```markdown
# Project Memory

Lessons learned and decisions from tasks are recorded here.
Lines after 200 will be truncated from auto-loading, so keep this file concise.
Use topic files (e.g., `security-lessons.md`, `architecture-decisions.md`) for detailed notes.
```

Create `.claude/memory/decisions.md`:

```markdown
# Governance Decisions

Timestamped log of changes to the governance layer, maintained by `/evolve`.

| Date | Decision | Reason | Source |
|------|----------|--------|--------|
```

### 4i. Settings and Hooks

**Always** generate `.claude/settings.json` with hook definitions. If the user chose auto-accept in Step 3.5, also include permissions. Read-only tools (Read, Glob, Grep) are already auto-approved by Claude Code and do not need to be listed.

**If auto-accept was chosen:**
```json
{
  "permissions": {
    "defaultMode": "auto",
    "allow": [
      "Bash",
      "Edit",
      "Write",
      "WebFetch",
      "WebSearch",
      "NotebookEdit"
    ]
  },
  "hooks": { ... }
}
```

**If auto-accept was declined:**
```json
{
  "hooks": { ... }
}
```

**Hook definitions** (always included):
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/scripts/secret-filter.py\""
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/scripts/destructive-guard.py\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/scripts/anti-rationalization.py\""
          },
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/scripts/evidence-check.py\""
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/.claude/scripts/skill-reminder.py\""
          }
        ]
      }
    ]
  }
}
```

The governance hooks fire **before** permission rules are evaluated and block dangerous operations regardless of the allow list. This is the safety layer that makes auto-accept viable.

### 4k. Hook Scripts

Copy all hook scripts from `${CLAUDE_PLUGIN_ROOT}/scripts/` to `.claude/scripts/`:

- `secret-filter.py` — blocks hardcoded API keys, private keys, credentials in Write/Edit
- `destructive-guard.py` — blocks risky Bash commands (rm -rf, git push --force, etc.)
- `anti-rationalization.py` — prevents refusal patterns on Stop
- `evidence-check.py` — verifies claims with file reads before Stop
- `skill-reminder.py` — tracks prompt count, reminds about QC checkpoints
- `hook_telemetry.py` — shared logging utility used by all hooks

These scripts are self-contained Python 3 files with no external dependencies. They use relative imports (`hook_telemetry.py` in the same directory) and read from stdin for tool input. No path modifications needed — copy verbatim.

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

Write all generated files to the project's `.claude/` directory.

**Completion checklist — verify ALL of these exist before finishing:**

| # | File | Source |
|---|------|--------|
| 1 | `.claude/manifest.json` | Generated from analysis |
| 2 | `.claude/CLAUDE.md` | Generated from analysis |
| 3 | `.claude/CHANGELOG.md` | Generated (Step 4f) |
| 4 | `.claude/tasks/INDEX.md` | Generated (Step 4g) |
| 5 | `.claude/memory/MEMORY.md` | Generated (Step 4h) |
| 6 | `.claude/memory/decisions.md` | Generated (Step 4h) |
| 7 | `.claude/settings.json` | Generated (Step 4i) |
| 8 | `.claude/rules/security.md` | Hydrated from template |
| 9 | `.claude/rules/architecture.md` | Hydrated from template |
| 10 | `.claude/rules/conventions.md` | Hydrated from template |
| 11 | `.claude/patterns/*.md` | Generated from samples |
| 12 | `.claude/skills/preflight/SKILL.md` | Generated (project-customized) |
| 13 | `.claude/skills/qc/SKILL.md` | Generated (project-customized) |
| 14 | `.claude/skills/evolve/SKILL.md` | Generated (project-customized) |
| 15 | `.claude/skills/task-doc/SKILL.md` | Generated (project-customized) |
| 16 | `.claude/skills/close-task/SKILL.md` | Generated (project-customized) |
| 17 | `.claude/skills/export/SKILL.md` | Copied from plugin |
| 18 | `.claude/skills/report/SKILL.md` | Copied from plugin |
| 19 | `.claude/skills/insights/SKILL.md` | Copied from plugin |
| 20 | `.claude/skills/critique/SKILL.md` | Copied from plugin |
| 21 | `.claude/skills/evolve/changelog-spec.md` | Copied from plugin |
| 22 | `.claude/scripts/secret-filter.py` | Copied from plugin |
| 23 | `.claude/scripts/destructive-guard.py` | Copied from plugin |
| 24 | `.claude/scripts/anti-rationalization.py` | Copied from plugin |
| 25 | `.claude/scripts/evidence-check.py` | Copied from plugin |
| 26 | `.claude/scripts/skill-reminder.py` | Copied from plugin |
| 27 | `.claude/scripts/hook_telemetry.py` | Copied from plugin |

If any file is missing, go back and create it. Report what you created and any fields in the manifest you couldn't determine (marked as `null`).

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

$ARGUMENTS
