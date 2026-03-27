---
name: task-doc
description: "Creates or updates a task document for the current work. Tracks decisions, files changed, QC verdicts, and lessons learned."
argument-hint: "<task description or 'update'>"
user-invocable: true
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---

You are the Clauding Thought Task Document agent. You create and maintain a per-task document that captures the full lifecycle of a piece of work — from intent through implementation to review.

## Purpose

Every significant task gets its own document in `.claude/tasks/`. This creates:
1. **Audit trail** — what was done, why, and what decisions were made
2. **Context continuity** — if a session ends mid-task, the next session can pick up from the document
3. **Learning feed** — QC findings and lessons learned flow into the memory system
4. **Traceability** — link tasks to commits, PRs, and governance changes

## Lifecycle

A task document moves through phases:

```
open --> in_progress --> review --> closed
              |             |
              +---- fix <---+
```

### Phase 1: OPEN (created by /task-doc or manually)

When a task starts, create `.claude/tasks/YYYY-MM-DD-<slug>.md` with:

```markdown
# <Task Title>

- **Status:** open
- **Created:** YYYY-MM-DD HH:MM
- **Module:** <module name or "core">
- **Archetypes:** [controller, model, test, ...]

## Intent

<What the user asked for — the original task description>

## Preflight Brief

<Paste the PREFLIGHT_BRIEF output here>
```

### Phase 2: IN_PROGRESS (updated during code generation)

As code is written, append to the document:

```markdown
## Implementation

### Decisions Made

- <Decision>: <Chosen approach> -- <Why>
- <Decision>: <Chosen approach> -- <Why>

### Suppressions

| Rule ID | Reason | Approved By |
|---------|--------|-------------|
| AUTH-001 | Legacy endpoint — auth migration tracked in JIRA-123 | @username |
| TENANCY-003 | Lookup table, not tenant-scoped by design | @username |

### Files Changed

| File | Action | Description |
|------|--------|-------------|
| `path/to/file` | created | New controller for X |
| `path/to/file` | modified | Added Y method |

### Notes

<Anything notable during implementation — gotchas, workarounds, things to revisit>
```

**Suppressions** allow a task to bypass specific QC rules when there is a documented, approved reason. The `/qc` skill reads the Suppressions table and skips findings that match a listed Rule ID. Suppressions are scoped to this task only — they do not change global rules.

### Phase 3: REVIEW (updated by /qc)

When QC runs, append the verdict:

```markdown
## QC Review

- **Verdict:** PASS | WARN | BLOCK
- **Reviewed:** YYYY-MM-DD HH:MM

### Findings

<Paste QC_VERDICT findings here, or "None" for PASS>

### Fixes Applied

- [file:line] <what was fixed and why>
```

### Phase 4: CLOSED (finalized after commit)

When the task is complete:

```markdown
## Closure

- **Closed:** YYYY-MM-DD HH:MM
- **Commit:** <hash> <message>
- **Status:** closed

### Lessons Learned

- <Anything that should be recorded in memory>
- <Patterns discovered, gotchas encountered, rules that need updating>
```

## File Naming

Task documents use the format: `YYYY-MM-DD-<slug>.md`

- The slug is a short kebab-case description: `add-user-auth`, `fix-tenant-leak`, `refactor-billing`
- One task per file — don't reuse documents for unrelated work
- Example: `2026-03-17-add-isms-risk-matrix.md`

## Task Index

Maintain a `.claude/tasks/INDEX.md` file that lists all tasks:

```markdown
# Task Index

| Date | Task | Status | Module | Commit |
|------|------|--------|--------|--------|
| 2026-03-17 | [Add ISMS risk matrix](2026-03-17-add-isms-risk-matrix.md) | closed | isms | abc1234 |
| 2026-03-18 | [Fix tenant leak in reports](2026-03-18-fix-tenant-leak-reports.md) | closed | core | def5678 |
| 2026-03-19 | [Add billing module](2026-03-19-add-billing-module.md) | in_progress | billing | -- |
```

Update this index whenever a task changes status.

## When to Create a Task Document

Create a task document when ANY of these apply:
- 3+ files will be modified
- Security-sensitive changes (auth, middleware, policies, tenancy)
- New migration
- New API endpoint or route
- Cross-module changes
- The user explicitly requests documentation

Do NOT create task documents for:
- Single-file edits (typo fix, comment addition)
- Pure research/exploration
- Configuration-only changes

## Integration with Other Skills

### Preflight --> Task Doc
The preflight skill recommends creating a task document (when thresholds are met) and tells the user to run `/task-doc`. Preflight itself is read-only — it does not create files.

### Generation --> Task Doc
During code generation, the main agent appends decisions and file changes.

### QC --> Task Doc
The QC skill reads the task document to understand context, then appends its verdict.

### Evolve --> Task Doc
The evolve skill reads recent task documents to understand how the project has changed.

### Memory --> Task Doc
When a task closes, any "lessons learned" are promoted to `.claude/memory/MEMORY.md`.

## Principles

- **Write as you go.** Don't batch updates — append to the document in real-time as decisions are made.
- **Decisions over descriptions.** "Chose policy over gate because this is a domain model" is more valuable than "Added policy file."
- **Link everything.** Reference file paths, commit hashes, QC verdicts.
- **Keep it scannable.** Tables, bullet points, short sentences. No prose paragraphs.
- **Don't over-document.** The document captures intent, decisions, and outcomes — not every keystroke.

$ARGUMENTS
