# Cross-Project Insights

This directory stores anonymized, aggregated findings from all projects governed by this Clauding Thought plugin instance.

## Files

- `findings.jsonl` — Append-only log of anonymized findings (created at runtime by /close-task and /critique)
- `patterns.md` — Synthesized patterns from findings (created/updated by /insights)
- `hook-candidates.md` — Violations that could become hooks (created/updated by /insights)

## Privacy

Data stored here is deliberately anonymized:
- NO project paths or file names
- NO code snippets
- Only: rule_id, tier, stack fingerprint (language+framework), verdict, timestamp, outcome

## Location

This directory lives at `${CLAUDE_PLUGIN_ROOT}/insights/` — it is plugin-scoped, not project-scoped.
