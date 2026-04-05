# Clauding Thought — Full Init Instructions

**IMPORTANT:** An existing root-level `CLAUDE.md` does NOT mean governance is initialized. Leave it alone. All generated files go inside `.claude/`.

## Step 0: SCAFFOLD — Create Directory Structure

Read `.claude/.plugin-root` to get the plugin installation path. Then run the scaffold script:

```bash
python "<plugin_root_path>/scripts/scaffold.py"
```

If `$ARGUMENTS` contains `--update`, add `--update` to the command:

```bash
python "<plugin_root_path>/scripts/scaffold.py" --update
```

If `.claude/.plugin-root` does not exist, check `~/.claude/plugins/cache/clauding-thought/` for the plugin path, or ask the user.

The scaffold creates the directory tree, copies boilerplate skills, hook scripts, and rule templates. Its JSON output tells you what was created and what remains. Save the output for reference in later steps.

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

## Step 3.5: CONFIGURE — Permission Mode

Ask the user:

> "Do you want to auto-accept tool calls? The governance hooks (secret-filter, destructive-guard) will still block dangerous operations in real-time. This removes the manual permission prompt for every Bash/Write/Edit call."

- If **yes** → set `auto_accept = true`, will generate `.claude/settings.json` with permissions and hooks in Step 4i
- If **no** → set `auto_accept = false`, will generate `.claude/settings.json` with hooks only (no permission overrides)

Record the choice for use in Steps 4a and 4i. Note: `.claude/settings.json` is always generated because it contains the hook definitions.

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

**Boilerplate skills** — Already copied by the scaffold script. These are: export, report, insights, critique (SKILL.md files) and evolve/changelog-spec.md. Do NOT regenerate these — they are already in place.

### 4d. Pattern Files
For each archetype sampled in Step 2, generate a pattern file showing:
- The canonical structure (annotated)
- Required elements (must always be present)
- Variable elements (change per instance)
- Anti-patterns (what NOT to do, based on project conventions)

### 4e. Rule Files

The scaffold script copied rule templates to `.claude/rules/` as `*.template.md` files. Hydrate them by replacing placeholders with project-specific content:

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

### 4g-4h. Task Index and Memory

Already created by the scaffold script. No action needed.

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
| 4 | `.claude/settings.json` | **GENERATE** with hooks (Step 4i) |
| 5 | `.claude/rules/security.md` | **GENERATE** by hydrating template |
| 6 | `.claude/rules/architecture.md` | **GENERATE** by hydrating template |
| 7 | `.claude/rules/conventions.md` | **GENERATE** by hydrating template |
| 8 | `.claude/patterns/*.md` | **GENERATE** from code samples |
| 9 | `.claude/skills/preflight/SKILL.md` | **GENERATE** project-customized |
| 10 | `.claude/skills/qc/SKILL.md` | **GENERATE** project-customized |
| 11 | `.claude/skills/evolve/SKILL.md` | **GENERATE** project-customized |
| 12 | `.claude/skills/task-doc/SKILL.md` | **GENERATE** project-customized |
| 13 | `.claude/skills/close-task/SKILL.md` | **GENERATE** project-customized |
| 14 | `.claude/tasks/INDEX.md` | scaffold (verify exists) |
| 15 | `.claude/memory/MEMORY.md` | scaffold (verify exists) |
| 16 | `.claude/memory/decisions.md` | scaffold (verify exists) |
| 17-20 | `.claude/skills/{export,report,insights,critique}/SKILL.md` | scaffold (verify exists) |
| 21 | `.claude/skills/evolve/changelog-spec.md` | scaffold (verify exists) |
| 22-27 | `.claude/scripts/*.py` (6 files) | scaffold (verify exists) |

Items 1-13 are YOUR responsibility to create. Items 14-27 were created by the scaffold script. If any file is missing, go back and create it. Report what you created and any manifest fields you couldn't determine (marked as `null`).

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
