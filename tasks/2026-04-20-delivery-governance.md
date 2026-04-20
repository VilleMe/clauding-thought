# Delivery Governance — Catch Features That Pass Every Correctness Gate But Deliver No Value

- **Status:** open
- **Created:** 2026-04-20
- **Plugin version at start:** 2.1.2
- **Target version:** 2.2.0 (minor — new skill + schema-tier addition, backwards-compatible)
- **Effort:** ~2.5 days across 3 phases, each independently shippable

## Why this task exists

A consuming project (KI, Laravel/Inertia/Vue ISMS platform) ran four sequential multi-pillar specs through the full Clauding Thought pipeline — `/preflight` → `/task-doc` → `/qc` → `/critique` → `/close-task` — across a weekend. All four pillars closed in review/closed status. Every gate was green: 847 tests pass, QC PASS, critique found only nitpicks, architecture tests green, pint clean, close-task accepted the close-outs.

**Observable outcome for the user: zero user-visible improvement.** The stated thesis of the work (a pre-journey wizard captures organisational context → downstream AI capabilities produce richer, tailored output → users perceive tangible lift) was not delivered end-to-end despite every pillar being individually "done."

The forensic analysis — documented in [c:\dev\KI\.claude\tasks\2026-04-20-isms-deliver-weekend-value.md](../../KI/.claude/tasks/2026-04-20-isms-deliver-weekend-value.md) — confirms the failure was not in the code quality. The code is clean. The failure is in **what the pipeline measures**.

## Problem statement

Clauding Thought's pipeline is a semantic linter with a skills lifecycle. Every gate answers variants of *"is this code well-formed?"* No gate answers *"does this code deliver the stated thesis?"*

Specific evidence from the plugin source:

- [`scripts/anti-rationalization.py:49`](../scripts/anti-rationalization.py#L49) — the negation pattern `documented?\s+(this|it|the issue)\s+(as|in)\s+(tech debt|a ticket|the task)` waves through "deferred. Tracked for follow-up task" — the exact phrasing used to close out acceptance criteria that would have caught the gap.
- [`scripts/evidence-check.py:20-25`](../scripts/evidence-check.py#L20-L25) — verifies test commands were executed but has no concept of *what the tests covered*. "847 tests passed" satisfies it regardless of thesis coverage.
- [`schema/manifest.schema.json`](../schema/manifest.schema.json) — tiers hardcoded to `security` / `architecture` / `conventions`. No tier exists that could express "new user-visible route must have nav reachability" or "cross-pillar spec must name its integration seams."
- [`patterns/`](../patterns) — five archetypes: controller, model, migration, test, component. No `feature.md`, `journey.md`, `integration.md`, `navigation.md`. The object "feature with an entry point" is not a first-class pattern in the framework.
- The close-task skill accepts unchecked `[ ]` acceptance criteria marked as deferred via free-text. A pillar close-out citing deferrals for the exact test that would have caught the gap closed successfully.

## Thesis Demo (this task's own)

**Claim:** After these changes ship, a consuming project running a pillar-style spec through the full Clauding Thought pipeline cannot close a pillar whose stated user-visible thesis is not demonstrated end-to-end. The KI weekend failure is mechanically impossible to repeat.

**Demo script:**
1. Apply the three phases to `c:\dev\clauding-thought`.
2. In a fresh test project, create a task doc claiming a user-visible thesis but writing only slice-level acceptance criteria.
3. Attempt `/close-task`. Expected: close-task refuses until a `## Thesis Demo` section exists AND has been executed within 24h AND the observable output matches.
4. Amend the task to defer the thesis test with free-text "deferred to follow-up". Expected: close-task refuses. Only `[deferred:TASK-ID]` where TASK-ID exists in INDEX.md is accepted.
5. Add a new route to the project without a nav entry, run `/qc`. Expected: DELIV-001 warning.

**Observable:** three distinct refusal messages from `close-task` + one DELIV-001 warning from `qc` in the demo log.

## Phases

Ordered by impact-per-effort. Each phase is independently shippable — no cross-phase dependency.

### Phase 1 — Deferrals become mechanically expensive (~1 day, highest leverage)

The single smallest change that would have caught the weekend failure. No schema bump, no new skill, reversible in one commit.

**Changes:**

1. **Amend [`scripts/anti-rationalization.py`](../scripts/anti-rationalization.py):** when the response contains a dismissal match AND the current active task doc has any unchecked `[ ]` acceptance-criterion boxes in its `## Acceptance Criteria` section, disable the negation patterns. Hook fires regardless of "tracked for follow-up" phrasing. Active task resolved via the same logic `/qc` uses.

2. **Amend `close-task` skill (lives in the plugin distribution, path varies):**
   - Acceptance criteria format enforced: each item is `[x]`, `[ ]` (cannot close), or `[deferred:TASK-ID]`.
   - `TASK-ID` must resolve to an entry in the project's task `INDEX.md`.
   - Free-text "deferred" / "to be done later" / similar prose fails the close.

3. **Amend `preflight` skill:** injects the current count of open `[deferred:...]` items from all prior task docs in the project. At count > 3, preflight prepends a warning: *"Deferred-item ledger at N items. `/close-task` will refuse new closures until the ledger drops below 3."*

4. **Amend `close-task` skill:** refuse to close any new task while the deferred-item ledger is > 3.

**Acceptance:**
- [ ] Modified `anti-rationalization.py` — unit tests cover: (a) dismissal with all-`[x]` criteria = allow, (b) dismissal with unchecked `[ ]` = feedback (exit 2), (c) dismissal with `[deferred:TASK-ID]` = allow when TASK-ID exists, feedback when it doesn't.
- [ ] `close-task` refuses close-outs with free-text deferrals. Tested against a sample task doc.
- [ ] `preflight` prepends ledger count when non-empty.
- [ ] `close-task` refuses new closures when ledger > 3. Manual test.
- [ ] CHANGELOG entry: "2.2.0-alpha.1 — Deferrals gated."

**Files:**
- `scripts/anti-rationalization.py`
- Plugin-distribution close-task `SKILL.md` (find exact path during implementation — the skill SKILL.md is referenced by the consuming project's `.claude/skills/close-task/SKILL.md` in KI)
- Plugin-distribution preflight `SKILL.md`
- `CHANGELOG.md`

### Phase 2 — `/thesis` skill + `close-task` demo gate (~1 day, medium leverage)

New skill that forces the author to state the user-visible thesis as a first-class artifact in the task doc. `close-task` blocks unless the thesis was demonstrated within 24h.

**Changes:**

1. **New skill `/thesis` at `skills/thesis/SKILL.md`** (in plugin distribution). Invoked during task-doc creation or amendment. Prompts the agent to write exactly one `## Thesis Demo` section with three subsections:
   - `**Claim:**` — one sentence, user-perspective
   - `**Script:**` — numbered steps, at least one must be an executable command
   - `**Observable:**` — the exact string, DB row, prop value, or UI state that proves the claim

2. **Amend `task-doc` skill:** default new task template includes an empty `## Thesis Demo` section with the three subsection headers. Tagged `<!-- required -->` HTML comment.

3. **Amend `close-task` skill:** before accepting close, parse the task doc for `## Thesis Demo`. If missing or empty, refuse. If present, check for evidence (a tool output block, screenshot reference, or log excerpt) with a timestamp within 24h of the close. If no evidence, refuse.

4. **Opt-out flag:** `--no-user-observable-change` on `/close-task` writes a one-line justification to the task doc (replacing the thesis requirement) AND logs it to the insights ledger as a `CRITIQUE-delivery-opt-out` entry.

**Acceptance:**
- [ ] `skills/thesis/SKILL.md` authored with YAML frontmatter matching existing convention (see [`templates/skills/critique/SKILL.md`](../templates/skills/critique/SKILL.md)).
- [ ] Task-doc template carries the three-subsection thesis block.
- [ ] close-task refuses close without thesis section. Tested against sample task doc missing the section.
- [ ] close-task refuses close with thesis section but no recent evidence. Tested.
- [ ] close-task accepts `--no-user-observable-change` with justification. Logged to insights.
- [ ] CHANGELOG entry: "2.2.0-alpha.2 — Thesis demo gate."

**Files:**
- New: `skills/thesis/SKILL.md` (or `templates/skills/thesis/SKILL.md` if this repo holds templates only — verify during implementation)
- Amend: plugin-distribution `task-doc` and `close-task` skills
- `CHANGELOG.md`

### Phase 3 — `delivery` manifest tier + 3 rules (~0.5 day, institutionalising the lesson)

New tier so future projects get delivery-level checks from `/init`.

**Changes:**

1. **Amend [`schema/manifest.schema.json`](../schema/manifest.schema.json):** add `delivery` alongside `security`, `architecture`, `conventions`. Schema:
   ```jsonc
   "delivery": {
     "posture": "strict" | "advisory",
     "rules": [
       { "id": "string", "name": "string", "severity": "error"|"warning"|"info", "paths": [...] }
     ]
   }
   ```
   Schema change is additive — existing manifests remain valid (no `delivery` tier = empty, all checks pass trivially).

2. **New rule file `rules/delivery.md`** with three rules:
   - **DELIV-001** — *New top-level route requires nav reachability.* `/qc` scans route files for additions; flags routes not referenced in any file under the nav component archetype. Severity: warning.
   - **DELIV-002** — *Cross-pillar spec requires seams manifest.* Any task doc listing > 1 pillar in its `Depends on:` or `Parent:` field must include a `## Seams` section mapping each producer→consumer→owner. Severity: error.
   - **DELIV-003** — *User-observable task requires thesis demo.* Any task doc tagged `user-observable: true` in its frontmatter must have a `## Thesis Demo` section (depends on Phase 2; degrades gracefully if Phase 2 not applied). Severity: error.

3. **Amend `init` skill:** when generating `manifest.json` for a new project, include the `delivery` tier with the 3 default rules. Posture defaults to `advisory` for existing projects, `strict` for new.

4. **Amend `qc` skill:** load `rules/delivery.md` in the same tiered loop as `security.md` / `architecture.md` / `conventions.md`. Add `delivery:` section to the verdict block.

**Acceptance:**
- [ ] Schema updated. `ajv` (or equivalent) validates both old and new manifests.
- [ ] `rules/delivery.md` authored with 3 rules + examples.
- [ ] `init` skill generates the tier in new projects. Manual test against an empty directory.
- [ ] `qc` emits `delivery:` section. Tested against a project with a route but no nav entry — expects DELIV-001 warning.
- [ ] `/evolve` on a 1.x manifest migrates to 2.x tier shape without data loss.
- [ ] CHANGELOG entry: "2.2.0 — Delivery tier added."

**Files:**
- `schema/manifest.schema.json`
- New: `rules/delivery.md`
- Amend: plugin-distribution `init`, `qc`, `evolve` skills
- `CHANGELOG.md`

## Sequence

1. **Phase 1 first** — ships as `2.2.0-alpha.1`. Smallest blast radius. Shipped independently, it catches the bulk of future weekend-style failures because the deferred-ledger constraint alone would have blocked 3 of the 4 weekend pillar closures.
2. **Phase 2 second** — `2.2.0-alpha.2`. Adds the positive gate (thesis present + executed) on top of the negative gate from Phase 1. Opt-out flag provides escape for genuine infrastructure work.
3. **Phase 3 third** — `2.2.0`. Institutionalises the new contract in manifest + init so future projects inherit delivery governance by default.

Each phase can ship and be observed in a consuming project before the next begins. Ideal dogfooding: apply Phase 1 to KI first, watch the ISMS delivery task — the one documented in [2026-04-20-isms-deliver-weekend-value.md](../../KI/.claude/tasks/2026-04-20-isms-deliver-weekend-value.md) — flow through it. If the new gate catches real issues there, the change is validated before Phase 2.

## Out of scope

- **Spec-authoring quality.** If the thesis claim itself is trivially weak ("thesis: wizard exists"), no amount of gate will catch it. That's a human-review problem; Clauding Thought is not the right tool to solve it.
- **Infrastructure / refactor tasks.** The `--no-user-observable-change` flag deliberately preserves developer autonomy for work with no user-facing delta. Trust + audit rather than block.
- **Subtle integration failures under load.** Needs telemetry, not governance. Orthogonal.
- **Retroactive application.** Phases do NOT auto-reopen previously-closed tasks. The ISMS weekend pillars stay closed; the delivery task at KI is the forward-fix.

## Risks

- **False positives on DELIV-001** — many projects have routes that should NOT appear in nav (API endpoints, background jobs). Mitigation: `paths:` scope in the rule excludes `api/`, `webhooks/`, `jobs/`. Manual allowlist supported via per-project `.claude/rules/delivery.md` override.
- **Thesis-demo fatigue** — developers opting out routinely. Mitigation: `/insights` surfaces opt-out rate per project. High rate signals either genuine infrastructure-heavy work or gate gaming. Neither is mechanically preventable, but both are visible.
- **Deferred-ledger starvation** — projects with legitimate multi-sprint work could hit the > 3 ledger threshold in normal operation. Mitigation: threshold is per-initiative (inferred from task doc parent links), not per-project. Explicit override in `manifest.governance.deferred_threshold` for projects that need it.
- **Phase 1 regex brittleness** — detecting "unchecked `[ ]` in Acceptance Criteria section" relies on markdown structure staying consistent. Mitigation: use a real markdown parser (commonmark-py, shipped in hook deps), not regex.

## Success definition

After all three phases ship and are applied to KI:
- The deferred-test at the root of the weekend failure (`Risk suggestion test fixture: org with 5 registered assets produces risk suggestions referencing those asset names`) cannot be deferred without a tracked TASK-ID.
- The ISMS delivery task ([2026-04-20-isms-deliver-weekend-value.md](../../KI/.claude/tasks/2026-04-20-isms-deliver-weekend-value.md)) cannot be closed without demonstrating its thesis end-to-end.
- Any future project's wizard-style feature (one that captures data intended to flow into another subsystem) must declare the seam and own it before its parent pillar can close.
- `/insights` gains a new aggregate dimension: delivery-tier findings over time. Baseline = 0 pre-change, expected rise then fall as the ecosystem adapts.

## Open questions (to resolve during implementation)

1. **Where exactly do the core skills (close-task, preflight, task-doc, qc, init, evolve) live?** This repo contains only `templates/skills/{critique,export,insights,report}/`. The core six must ship somewhere the plugin loader consumes. Verify path during Phase 1 implementation before amending.
2. **Insights schema extension** — add `CRITIQUE-delivery`, `DELIV-001`, `DELIV-002`, `DELIV-003` as allowed rule IDs in the insights log. Already supported per the skill's rule-ID flexibility, but worth documenting.
3. **Backwards compatibility with manifest v1.0 and v1.1** — `/evolve` has to migrate without breaking in-flight projects. Test against the KI manifest at a known v1.1 state.
4. **Hook ordering** — if both `anti-rationalization` (Stop hook) and a future thesis-verification hook exist on the same event, define precedence. Likely: `anti-rationalization` first (blocks rationalized closures), then thesis-verification (blocks unjustified closures). First failure wins.

## Notes

The task doc itself demonstrates the pattern. It carries a `## Thesis Demo` section and uses the deferred-format convention that Phase 1 will enforce. Eat-the-dog-food.
