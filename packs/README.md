# Rule Packs

Rule packs are pre-built rule sets that can be merged into a project's `.claude/` governance layer during `/init` or applied later via `/evolve`.

## Pack Structure

```
packs/
  <pack-name>/
    pack.json          — Pack manifest (required)
    rules/             — Rule content files
      rule-a.md
      rule-b.md
```

## pack.json Format

```json
{
  "name": "my-pack",
  "version": "1.0.0",
  "description": "What this pack enforces",
  "tags": ["security", "best-practices"],
  "stack_filter": {
    "language": ["php", "python", "typescript"],
    "framework": ["laravel", "django"]
  },
  "rules": [
    {
      "file": "rules/my-rule.md",
      "target": "rules/security.md",
      "merge_strategy": "append_section",
      "section_id": "my-rule"
    }
  ],
  "security_checks": [
    {
      "id": "MYPACK-001",
      "name": "Check name",
      "severity": "error",
      "description": "What this check detects",
      "detect": "Pattern or heuristic description"
    }
  ]
}
```

## Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique pack identifier (kebab-case) |
| `version` | Yes | Semver version string |
| `description` | Yes | Human-readable description |
| `tags` | No | Categorization tags |
| `stack_filter` | No | When present, ALL non-empty filter arrays must match the project's stack. Empty arrays or missing field means "no constraint" for that dimension. |
| `rules` | Yes | Array of rule files to merge |
| `security_checks` | No | Additional manifest security checks to register |

## Rule Files

Rule content files are plain Markdown. They are **not** templates — they do not use `{{placeholder}}` syntax because packs are merged after template hydration.

Keep rule content specific and actionable. Reference OWASP, CWE, or other standards where applicable.

## Merge Strategy

During `/init` or `/evolve`, pack rules are inserted into the target rule file between section markers:

```markdown
<!-- pack:my-pack:my-rule:start -->
## Rule Title

Rule content here.

<!-- pack:my-pack:my-rule:end -->
```

This allows `/evolve` to detect whether pack sections have been customized (content between markers differs from the original) and handle updates accordingly:

- **Not customized:** Replace content between markers with new pack version
- **Customized:** Show diff and ask user to choose: accept update, keep current, or merge manually

## Stack Filtering

The `stack_filter` object controls when a pack is offered during `/init`:

- If `stack_filter` is omitted or empty, the pack applies to all projects
- If `language` is non-empty, the project must use at least one listed language
- If `framework` is non-empty, the project must use at least one listed framework
- An empty array (e.g., `"framework": []`) means "no constraint" for that dimension
- All non-empty conditions must be satisfied (AND logic). Example: if both `language` and `framework` are non-empty, the project must match at least one entry in each.

## Authoring Tips

1. **Be specific.** Reference CWE IDs, OWASP categories, or framework docs.
2. **Keep rules actionable.** Each rule should describe what to check and what "good" looks like.
3. **Use severity wisely.** `error` = must fix before merge. `warning` = should fix. `info` = nice to know.
4. **Test with a real project.** Run `/init` with your pack on a sample codebase.
5. **Version bumps:** MAJOR for removed/restructured rules, MINOR for new rules, PATCH for wording tweaks.
