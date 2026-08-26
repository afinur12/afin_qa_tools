# Page Override: Test Case Execution (`/testcases/{id}/execute`)

The highest-effort page in the app — testers live here for the duration
of a test run. Layout must mirror the docx export structure 1:1 (per
PLAN.md docx template mapping) so what testers see on screen is exactly
what lands in the exported artifact. Inherits color/type tokens from
MASTER.md and status colors from `app-shell.md`; overrides layout only.

## Structure (top to bottom, single scrolling column, max-width ~900px
per existing `main` container — do not go full-bleed, long line lengths
hurt scanability of step text)

1. **Breadcrumb** (Stories / Story / Phase / Subtask / TC code)
2. **Section 1 — Header card**: 2-column label/value grid (matches docx
   Table 0) — Project, Scenario, Tester, Test Date, Environment,
   Priority, Type, Channel, Iteration, Balance Before/After, Usage,
   Final Status (as the same badge component from app-shell.md, editable
   via dropdown inline), Remark, Data Test (multiline, collapsed by
   default behind "Show data test" disclosure — it's often long/JSON-ish
   and pushes the real content below the fold).
3. **Section 2 — Pre Condition**, **Section 3 — Main Test**, **Section 4
   — Post Condition**: identical step-block component, repeated per
   step, stacked (matches docx "Option A: each step its own full
   stacked block").

## Step block component (repeats N times per section)

```
┌ Step 1 ─────────────────────────────────────── [⋮ menu: delete step] ┐
│ Step description                                                     │
│ ┌───────────────────────────────────────────────────────────────┐   │
│ │ (textarea, autosize, placeholder "What does this step do?")     │   │
│ └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│ Expected Result              │ Actual Result                        │
│ ┌─────────────────────────┐  │ ┌─────────────────────────────────┐ │
│ │ (textarea)               │  │ │ (textarea)                       │ │
│ └─────────────────────────┘  │ └─────────────────────────────────┘ │
│                                                                       │
│ Screenshot                                                           │
│ ┌───────────────────────────────────────────────────────────────┐   │
│ │  [thumbnail] [thumbnail] [thumbnail]        ⌘/Ctrl+V to paste   │   │
│ │  dropzone: dashed border (existing .dropzone class), click to    │   │
│ │  focus + paste, or drag-drop a file                              │   │
│ └───────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
[+ Add step]
```

Notes:
- Expected/Actual side-by-side on desktop (≥768px), stacked full-width
  on narrower viewports — this is still a desktop-first internal tool
  (per PLAN.md, local Windows use) but don't hard-code fixed pixel
  widths for the two columns; use a responsive grid (`1fr 1fr` above
  768px, `1fr` below) so the window can still be resized/split-screened
  next to a browser being tested.
- Screenshot dropzone: reuse existing `.dropzone` CSS. Multiple
  screenshots per step (per PLAN.md) render as a thumbnail row above the
  paste target, each with a small delete (×) affordance on hover —
  44×44px hit target per touch guidance even though primary input is
  mouse/keyboard, since it costs nothing and helps precision.
- Give the dropzone an explicit focus state (visible outline) and a
  keyboard path (a real "Upload file" button/`<input type=file>` inside
  it) — clipboard-paste alone is not keyboard/screen-reader operable on
  its own.
- Actual Result field should visually flag as "empty" (subtle amber left
  border, not a hard error) when Expected Result is filled but Actual
  isn't yet — this is the live-execution state, not a validation error,
  so don't use destructive/red styling for it.
- "+ Add step" appends a new numbered block at the end of that section
  only (steps are per-section per PLAN.md `testcase_steps.section`).

## Footer actions (sticky bar, bottom of viewport)

`[ Save ]` (primary) · `[ Export to Word ]` (secondary, triggers
`/testcases/{id}/export-docx`) — keep this bar visible while scrolling
through a long multi-step test case rather than only at the page bottom,
since Save should be reachable without scrolling back up.
