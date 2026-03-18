# Clauding Thought

**Self-generating AI code governance for any project.**

Clauding Thought analyzes your codebase and builds a complete `.claude/` governance layer -- rules, patterns, security checks, and agent skills -- tailored to your project's actual architecture and conventions.

Distributed as a **Claude Agent SDK plugin**.

## Prerequisites

Clauding Thought skills are token-intensive -- `/init` reads dozens of files to analyze your codebase, and `/preflight` + `/qc` add overhead to every task. A **Claude Max subscription** (or equivalent high-throughput plan) is strongly recommended.

## The Problem

Every project's AI coding rules are hand-crafted over weeks of trial and error. When you start a new project, you start from zero. Clauding Thought fixes this by reading your codebase and generating the rules automatically.

## How It Works

```
Your Codebase --> /init --> .claude/ governance layer
                             ├── manifest.json      (project DNA + governance version)
                             ├── CLAUDE.md           (master rules)
                             ├── CHANGELOG.md        (governance version history)
                             ├── skills/
                             │   ├── preflight/      (pre-generation context)
                             │   ├── qc/             (post-generation review)
                             │   ├── evolve/         (update rules over time)
                             │   ├── task-doc/       (create/update task documents)
                             │   └── close-task/     (finalize task + capture lessons)
                             ├── rules/
                             │   ├── security.md     (auth, tenancy, exposure)
                             │   ├── architecture.md (modules, layers, boundaries)
                             │   └── conventions.md  (naming, style, patterns)
                             ├── patterns/
                             │   ├── controller.md   (how controllers look here)
                             │   ├── model.md        (how models look here)
                             │   ├── test.md         (how tests look here)
                             │   ├── migration.md    (how migrations look here)
                             │   └── component.md    (how frontend components look)
                             └── tasks/
                                 ├── INDEX.md        (task registry)
                                 └── *.md            (per-task documents)
```

## Quick Start

```bash
# 1. Clone clauding-thought
git clone <repo-url> clauding-thought

# 2. Add as a plugin to your target project
# (reference it in your project's plugin configuration)

# 3. Bootstrap -- analyze your codebase
/init

# 4. Work on a task
/preflight "Add user authentication"   # gather context, create task doc
# ... write code ...
/qc                                     # review changes, update task doc
/close-task                             # finalize, capture lessons

# 5. Periodically update the governance layer
/evolve                                 # re-analyze, bump version, update CHANGELOG
```

## Four Phases

### 1. Bootstrap -- `/init`

Drop Clauding Thought into a project and run `/init`. It:

- **Detects** your stack (language, framework, database, frontend, testing)
- **Samples** existing code to extract patterns (3-5 files per archetype)
- **Analyzes** architecture (tenancy, auth, modules, layers, boundaries)
- **Generates** the entire `.claude/` directory with project-specific rules
- **Versions** the governance layer as `1.0.0` with a CHANGELOG entry

### 2. Runtime -- `/preflight` + `/qc` + `/task-doc`

During development, skills work before, during, and after code generation:

**Preflight** runs before you write code:
- Classifies the task (model? controller? frontend?)
- Loads only the relevant rules and patterns
- Finds sibling files as references
- Creates a task document if the change is significant
- Returns a focused context brief

**Task Doc** tracks the work as it happens:
- Records decisions made during implementation
- Tracks files changed and why
- Maintains a per-task audit trail
- Captures lessons learned on close

**QC** runs after code is written:
- Reviews changes against manifest-driven rules
- Three tiers: Security (BLOCK) -> Architecture (WARN/BLOCK) -> Conventions (WARN)
- Appends verdict to the active task document
- Returns a structured verdict

### 3. Closure -- `/close-task`

When a task is complete:
- Finalizes the task document with commit reference
- Captures lessons learned
- Promotes learnings to the memory system
- Updates the task index

### 4. Evolution -- `/evolve`

Projects change. The governance layer should too:
- Re-analyzes the codebase
- Diffs against the stored manifest
- Suggests rule updates where conventions have shifted
- Reviews recent task documents for patterns
- Bumps the governance version and updates CHANGELOG
- Preserves intentional/aspirational rules

## Hooks -- Real-Time Enforcement

Clauding Thought includes 5 hooks that enforce governance in real-time, borrowed from best practices across the Claude Code ecosystem:

| Hook | Event | What It Does |
|------|-------|-------------|
| **secret-filter** | PreToolUse (Write/Edit) | Blocks AWS keys, private keys, API tokens, hardcoded passwords |
| **destructive-guard** | PreToolUse (Bash) | Blocks `rm -rf .`, `git push --force main`, `DROP TABLE`, `git reset --hard` |
| **anti-rationalization** | Stop | Catches "out of scope" / "pre-existing issue" dismissals |
| **evidence-check** | Stop | Blocks "tests pass" claims without actual test output |
| **skill-reminder** | UserPromptSubmit | Reminds Claude about available governance skills |

## The Manifest

`manifest.json` is the project's DNA. Everything else is derived from it.

```jsonc
{
  "version": "1.0",
  "stack": {
    "language": "php",
    "framework": "laravel",
    "framework_version": "12",
    "frontend": "vue3",
    "bridge": "inertia-v2",
    "testing": "pest-v4",
    "db": "postgresql"
  },
  "architecture": {
    "tenancy": {
      "strategy": "column-scoped",
      "scope_column": "organization_id",
      "trait": "HasOrganization"
    },
    "auth": {
      "authorization": {
        "strategy": "mixed",
        "patterns": [
          { "pattern": "policy", "scope": "domain models" },
          { "pattern": "gate", "scope": "config entities" }
        ]
      }
    },
    "modules": [
      { "name": "itsm", "path": "app/Models/Itsm" },
      { "name": "isms", "path": "app/Models/Isms" }
    ]
  },
  "conventions": {
    "validation_style": "form-request-array",
    "translation": {
      "system": "nested-json",
      "locales": ["en", "fi", "sv", "de"],
      "all_locales_required": true
    }
  },
  "boundaries": {
    "modules_may_import": {
      "itsm": ["core"],
      "isms": ["core"]
    }
  }
}
```

## Security Philosophy

Security is non-negotiable -- even for non-public applications.

### Two Postures

**Strict** (default for new projects):
- All security rules are blocking -- violations fail QC
- No exceptions, no grace period

**Advisory** (auto-detected for existing projects):
- **New code must still be strict.** Every new controller, model, and route must meet security rules.
- **Existing patterns are respected.** Gaps are documented, not overridden.
- **Gaps become tracked debt.** Each gap gets an ID, severity, scope, and mitigation suggestion.
- **The goal is migration to strict.** As gaps are resolved, advisory posture narrows.

### Real-Time + Post-Hoc

Clauding Thought enforces security at two levels:
1. **PreToolUse hooks** catch secrets and destructive commands before they happen
2. **QC skill** reviews semantic violations (auth bypass, tenant leak, data exposure) after code is written

## What Makes This Different

| Static Linter | Clauding Thought |
|---|---|
| "Missing type hint" | "This model has org_id but no tenancy trait" |
| "Unused import" | "ISMS controller imports from ITSM -- boundary violation" |
| Same rules for all projects | Rules derived from YOUR codebase |
| Syntax-level checks | Architecture-level understanding |
| Manual configuration | Self-generating from code analysis |

## Project Structure

```
clauding-thought/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── skills/
│   ├── init/                # Bootstrap: analyze codebase, generate governance
│   ├── preflight/           # Pre-coding: gather context, load rules
│   ├── qc/                  # Post-coding: review against rules
│   ├── evolve/              # Periodic: update governance for drift
│   ├── task-doc/            # Track: create/update task documents
│   └── close-task/          # Finalize: close task, promote lessons
├── hooks/
│   └── hooks.json           # Hook definitions
├── scripts/                 # Hook implementation scripts
├── rules/                   # Rule file templates
├── patterns/                # Pattern file templates
├── schema/                  # Manifest JSON Schema
├── CLAUDE.md                # Project rules for clauding-thought itself
└── README.md
```

## Supported Stacks

Clauding Thought is stack-agnostic. The manifest schema is universal; the generated rules are project-specific. Tested with:

- **PHP/Laravel** -- Eloquent, Inertia, Vue, Pest
- **Go** -- Chi, pgx, SvelteKit frontend
- **Python** -- FastAPI, Vue frontend
- More stacks work out of the box via stack detection

## License

MIT
