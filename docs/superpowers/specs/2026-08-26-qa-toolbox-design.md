# QA Toolbox — Design Spec

Date: 2026-08-26
Status: Approved for implementation planning

## Goal

Local-only web app supporting software tester work on the API &
microservices division. Tools: documentation generator (docx test
report export), test reporting, misc utilities. No server hosting —
runs on the user's machine, single user, no authentication.

## Stack

- Backend: Python, FastAPI
- DB: SQLite (single file, local-first, no Postgres/multi-user need)
- Frontend: Jinja2 server-rendered templates, vanilla JS where needed
  (clipboard screenshot capture)
- Files (screenshots, docx exports): stored on disk under `uploads/`,
  path saved in DB (not BLOB)
- Testing: pytest + FastAPI `TestClient`, each test run against a
  fresh temp SQLite file

## Project structure

```
qa-toolbox/
  app/
    main.py
    database.py             # SQLite engine, session
    models.py                # SQLAlchemy models
    schemas.py                 # Pydantic
    routers/
      stories.py
      subtasks.py
      testcases.py
      bugs.py
      curls.py
      docx_export.py
      dashboard.py
    templates/                 # Jinja2
      base.html
      dashboard.html
      stories/ ...
      subtasks/ ...
      testcase_execute.html      # Section 1-4 layout
    static/
      js/
      css/
    docx/
      Template_Artifact_V1.docx
      builder.py                 # fills template from DB data
    uploads/
      screenshots/{testcase_id}/{step_id}/...
      exports/
  tests/
  qa_toolbox.db                # sqlite file, gitignored
  requirements.txt
  README.md
```

## Core hierarchy (mirrors Jira)

Story → Phase (SIT / STAGING / STAGING_AFTER_ROLLBACK / SANITY,
testing starts from SIT) → Subtask.

Each Story has **at most one Phase per type** — no repeated phase
instances (e.g. a SIT retest round happens by adding more
subtasks/testcases to the existing SIT phase, not by creating a
second SIT phase). Enforced via `unique(story_id, type)`.

5 subtask types per phase: Test Planning, Test Data Preparation,
`<Phase> <Title>` (execution), Test Automation, Test Reporting.

- The **execution** subtask type holds TestCases and Bug tickets
  (bug title convention: `[ISSUE] <description>`). TestCase and Bug
  are **mandatory linked to a subtask** — no orphans.
- The other 4 subtask types (Test Planning, Test Data Preparation,
  Test Automation, Test Reporting) are lightweight containers: a
  title plus a free-text `notes` field. No specialized child records,
  no special page layout.

**STAGING_AFTER_ROLLBACK phase skips the 5-subtask breakdown** — only
1 execution-type subtask, no separate planning/data-prep/automation/
reporting subtasks. Enforced both in the UI (the subtask-create form
only offers the execution type for this phase type) and server-side
(reject other subtask types for this phase type).

## Code/ID convention

Applies to Story, Subtask, TestCase, Bug.

- User types 2 fields only: `display_code` (e.g. `EX-049`, matches
  real Jira code) + `title`
- `internal_key` (random string, e.g. uuid4 hex) auto-generated
  silently, DB uniqueness only — never shown/typed by user
- No auto-incrementing counter, codes 100% manual entry (Jira
  integration deferred)
- `display_code` uniqueness is enforced **per parent scope**, checked
  server-side at save time:
  - Story: globally unique
  - Subtask: unique within its Phase
  - TestCase: unique within its Subtask
  - Bug: unique within its Subtask
  - A collision re-renders the form with an inline "code already used
    in this [scope]" error (see Error handling below)

## DB schema (core tables)

- `story`: id, display_code (unique), title, internal_key, created_at
- `phase`: id, story_id FK, type (SIT/STAGING/STAGING_AFTER_ROLLBACK/
  SANITY) — unique(story_id, type)
- `subtask`: id, phase_id FK, display_code (unique within phase),
  title, internal_key, subtask_type, notes (text, nullable)
- `testcase`: id, subtask_id FK (mandatory), display_code (unique
  within subtask), title, internal_key, status (enum: Not Run / Pass
  / Fail / Blocked / Cancelled / Postponed, default Not Run)
- `bug`: id, subtask_id FK (mandatory), display_code (unique within
  subtask), title, internal_key, description (text), severity (Low/
  Medium/High/Critical), status (Open/In Progress/Resolved/Closed)
- `curl_collection`: id, attach_type (story/subtask), attach_id,
  raw_text, method, url, headers (json), body
- `testcase_step`: id, testcase_id FK, section
  (precondition/main/postcondition), step_no, step_text,
  expected_result, actual_result
- `screenshot`: id, step_id FK, file_path, uploaded_at

Constraints enforced in code (not just DB):

- STAGING_AFTER_ROLLBACK phase blocks creation of other 4 subtask
  types
- testcase/bug forms require subtask_id, no orphan save
- internal_key generated server-side, never exposed in forms
- display_code uniqueness per parent scope (see above)
- Delete is **blocked if children exist**: deleting a Story/Phase/
  Subtask/TestCase fails with an inline error naming what still
  exists underneath (e.g. "Delete 3 testcases and 1 bug first") — no
  cascade delete. Screenshots and steps have no children of their own,
  so those delete outright behind a UI confirm click; a screenshot
  delete also removes its file from disk.

## CRUD scope

Every entity (Story, Phase, Subtask, TestCase, Bug, TestCaseStep,
Screenshot) gets full CRUD: list, create (GET form + POST), edit (GET
form + POST), delete (POST, subject to the block-if-children rule
above).

Phase creation is scoped under its Story (`POST /stories/{id}/phases`):
the create form offers only phase types the story doesn't already have
(enforced by `unique(story_id, type)`) — a story is not required to
have all 4 phase types, they're added as testing progresses.

## Error handling

All form validation failures (uniqueness collisions, missing required
fields like subtask_id, delete-blocked-by-children) re-render the same
template with submitted values preserved and an inline error message
near the top or the specific field. The route returns HTTP 422 with an
`error` context var passed to the template. No flash/session
messaging layer.

## Dashboard (`/`)

Landing page shows:

- Story list: display_code, title, created_at, link into the story's
  phase/subtask drill-down
- TestCase status breakdown: counts per status (Not Run/Pass/Fail/
  Blocked/Cancelled/Postponed), computed live via a SQL `GROUP BY`
  query — no caching table needed at this scale
- Open Bug count: count of bugs with status in (Open, In Progress)

Both summary blocks are global totals for v1 (no per-story breakdown
table on the dashboard itself — drill into a story to see its own
testcases/bugs).

## Curl collection feature

Attaches to either Story or Subtask level. Stores raw curl text
(verbatim) + parsed fields (method/url/headers/body) for **display
only**. Actually re-running the stored curl (sending the HTTP request
from the app) is explicitly out of scope for this spec — deferred to
a future iteration.

## Execution Test Case page

Every testcase links to a subtask. Layout:

- Section 1: Description/header info
- Section 2: Pre Condition
- Section 3: Main Test
- Section 4: Post Condition

Each step (section 2-4): No, Step, Expected Result, Actual Result,
Screenshot. Screenshot capture via clipboard paste (click zone,
Ctrl+V, direct upload via JS reading the clipboard image and POSTing
it). Multiple screenshots per step allowed. Multiple steps = each step
its own full stacked block (matches docx template structure — see
below).

No format or size validation is applied to pasted screenshots —
whatever the clipboard provides is stored as-is at
`uploads/screenshots/{testcase_id}/{step_id}/{filename}`.

TestCase status (Not Run/Pass/Fail/Blocked/Cancelled/Postponed) is set
from this execution page.

## Bug tracking

Bug tickets, linked mandatorily to a subtask, carry: display_code,
title, internal_key, description (free text), severity (Low/Medium/
High/Critical), status (Open/In Progress/Resolved/Closed). Full detail
lives here rather than only in Jira, since the dashboard's open-bug
count and per-story drill-down depend on status being tracked
in-app.

## Docx template mapping (Template_Artifact_V1.docx)

**Table 0 — header, 15 rows x 4 cols (col0 spacer, col1 label, col2
spacer, col3 value)**
Project, Scenario, Tester (PIC) [default `Andri Firman Nurvianto`],
Test Date, Environment, Test Priority, Test Type, Channel,
Iteration [default `1`], Balance Before [default `Rp. -`],
Balance After [default `Rp. -`], Usage [default `Rp. -`], Final Status,
Remark, Data Test [multiline]

**Tables 1-3 = PRE CONDITION / MAIN TEST / POST CONDITION**, one
step-block table each (confirms Option A):

- row0: `No` | `1` | `Step` | `<step text>`
- row1: `Actual Result` | `<actual>` | `Expected Result` | `<expected>`
- row2: merged cell (gridSpan=6), text `Screenshot` (label)
- row3: merged cell (gridSpan=6), empty — image inserted here

**Builder logic** (`docx/builder.py`), implemented with `python-docx`
and direct XML manipulation (no templating library — `docxtpl` was
considered and rejected: it doesn't cleanly handle "clone a table N
times based on step count" without dropping into the same raw XML
work anyway, and adds a dependency on a Windows box where wheel-build
issues are already a known risk):

1. Load template fresh per export, never mutate source file
2. Fill table 0 cell(row, 3) per field from testcase/subtask/story data
3. Per section, step 1 uses existing table; step 2+ clones table XML,
   inserts after; fill No/Step/Actual/Expected; insert screenshot(s)
   into row3 merged cell (`add_run().add_picture(path, width=...)`)
4. Multiple screenshots per step: multiple `add_picture` calls in same
   row3 cell
5. Save as `{project}_{scenario}_{date}.docx` under `uploads/exports/`

## Routes (high level)

- `/` — dashboard (story list + testcase status breakdown + open bug
  count)
- `/stories` CRUD, `/stories/{id}/phases`
- `/subtasks` CRUD (scoped under phase)
- `/testcases` CRUD, `/testcases/{id}/execute` — Section 1-4 page,
  `POST /testcases/{id}/steps/{step_id}/screenshot` for paste-upload
- `/bugs` CRUD (scoped under subtask), including status/severity edit
- `/curls` attach/list per story or subtask
- `/testcases/{id}/export-docx` — runs builder.py, filename
  `{project}_{scenario}_{date}.docx`

## Testing approach

pytest + FastAPI `TestClient`, each test run against a fresh temp
SQLite file (not the real `qa_toolbox.db`). Cover:

- CRUD happy paths for every entity
- display_code uniqueness-collision errors at each scope
- delete-blocked-by-children behavior
- STAGING_AFTER_ROLLBACK subtask-type restriction
- docx export produces a valid file with the right number of
  step-block tables for a multi-step testcase

Screenshot paste flow and dashboard counts get manual/browser
verification — JS clipboard capture isn't practically unit-testable.

## Success criteria (MVP)

A tester can create a Story → Phase → Subtask → TestCase, execute it
(fill steps, paste screenshots), mark status, log a linked Bug, and
export a docx matching Template_Artifact_V1.docx's structure — all
without touching the DB directly, running entirely on `localhost` with
no network dependency.

## requirements.txt

fastapi, uvicorn, sqlalchemy, jinja2, python-multipart, python-docx,
pytest.
No pandas/openpyxl (Windows build error previously, add unpinned later
only if Excel import gets built).

## Tooling/environment notes

User runs Windows (PowerShell) — avoid heavy/no-wheel pip deps.
