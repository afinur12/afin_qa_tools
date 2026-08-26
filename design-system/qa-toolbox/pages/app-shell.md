# Page Override: App Shell & Navigation

Overrides MASTER.md's auto-matched "Enterprise Gateway" pattern, which is a
marketing/conversion pattern (mega menu, hero video, "Contact Sales") and
does not apply to this internal, single-user, local-only tool. Style,
color, and typography tokens from MASTER.md still apply. Motion: ignore
MASTER's scroll-reveal/GSAP recommendation — this is a form/table-heavy
CRUD app; motion budget is limited to hover/focus transitions (150-250ms)
and a fade-in on route content swap if any.

## Information Architecture

Hierarchy mirrors Jira: **Story → Phase → Subtask → (TestCase | Bug)**.
Curl collections attach to Story or Subtask directly (side-branch, not a
depth level).

```
Top nav (persistent, from existing style.css: white bar, brand + links)
  Stories | (Bugs — cross-story list) | (Curl Collections — cross-story list)

Story list  (/stories)
  -> Story detail (/stories/{id})            [tabs: Phases | Curl Collections]
       -> Phase panel (SIT / STAGING / STAGING_AFTER_ROLLBACK / SANITY)
            -> Subtask list (scoped to phase)
                 -> Subtask detail (/subtasks/{id})   [tabs: Test Cases | Bugs | Notes]
                      -> TestCase execute (/testcases/{id}/execute)
                      -> Bug detail (/bugs/{id})
```

Use **breadcrumbs** on every page below the top level (3+ depth levels
present, per ux-guidelines "Breadcrumbs" rule):
`Stories / EX-049 Login flow / SIT / EX-049-3 Execution / TC-001`
Each breadcrumb segment is a real link back up the hierarchy — this is
the primary "back" navigation, not the browser back button, since deep
links are shared/bookmarked by testers mid-execution.

## Layout pattern per level

- **List pages** (Stories, Subtasks-within-phase, Bugs, Curl Collections):
  dense table (existing `table`/`th`/`td` styles), one primary action
  button top-right ("+ New Story"), row click -> detail, status/severity
  as colored badge column, no pagination needed at expected local-use
  scale (tens–low hundreds of rows) but add a client-side text filter
  input above the table once a list exceeds ~20 rows.
- **Detail pages** (Story, Subtask): header card with code/title/
  internal_key (internal_key shown greyed/mono, read-only, never
  editable — per PLAN.md it's never user-typed), tabbed sub-sections
  below using existing `.card` styling per tab panel.
- **Phase view**: not a separate route so much as a segmented control /
  tab strip inside Story detail (4 fixed tabs: SIT, STAGING,
  STAGING_AFTER_ROLLBACK, SANITY). STAGING_AFTER_ROLLBACK tab renders a
  reduced UI (single execution subtask, no 5-way subtask-type picker) —
  make this visually obvious (e.g. no "+ Add subtask type" grid, just one
  card) rather than a disabled/greyed 5-way picker, so the constraint
  reads as "this phase works differently," not "this is broken."

## Status & severity color coding

Semantic, not decorative — reuse across TestCase status, Bug status/
severity, badge component from existing `.badge` CSS class. Colors below
extend MASTER.md's palette with semantic roles it doesn't define:

| Meaning | Background | Text | Used for |
|---|---|---|---|
| Neutral/pending | `#EEF0F3` | `#5B6472` | NOT_RUN, OPEN |
| In progress | `#DBEAFE` | `#1E40AF` | IN_PROGRESS |
| Success | `#DCFCE7` | `#15803D` | PASS, RESOLVED, CLOSED |
| Failure | `#FEE2E2` | `#B91C1C` | FAIL, CRITICAL severity |
| Warning/blocked | `#FEF3C7` | `#92400E` | BLOCKED, POSTPONED, HIGH severity |
| Cancelled/muted | `#F1F5F9` | `#94A3B8` | CANCELLED, LOW severity |

Never rely on color alone: pair every badge with its text label (already
implied by `.badge` usage) — satisfies "don't convey meaning by color
alone" from the chart/ux guidance.

## Forms

Story/Subtask/TestCase/Bug creation forms: exactly two user-typed
identity fields (`display_code`, `title`) per PLAN.md's code/ID
convention — do not add an internal_key field to any form, and do not
autogenerate/suggest display_code (100% manual entry, matches real Jira
code). Label display_code field clearly as "Jira code (e.g. EX-049)" so
the manual-entry constraint is understood, not mistaken for a bug.

Subtask/TestCase/Bug creation must hard-require selecting a parent
subtask before save is enabled (no orphans, enforced in code per
PLAN.md) — disable the Save button until a subtask is selected, with
inline helper text explaining why, rather than a post-submit error.
