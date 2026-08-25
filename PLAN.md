# QA Toolbox — Build Plan

## Goal
Local-only web app supporting software tester work, API & microservices
division. Tools: documentation generator, test reporting, misc utilities.
No server hosting — runs on user's machine.

## Stack
- Backend: Python, FastAPI
- DB: SQLite (single file, local-first, no Postgres/multi-user need)
- Frontend: Jinja2 server-rendered templates, vanilla JS where needed
- Files (screenshots, docs, artifacts): stored on disk, path saved in DB
  (not BLOB)

## Project structure
```
qa-toolbox/
  app/
    main.py
    database.py          # SQLite engine, session
    models.py             # SQLAlchemy models
    schemas.py             # Pydantic
    routers/
      stories.py
      subtasks.py
      testcases.py
      bugs.py
      curls.py
      docx_export.py
    templates/             # Jinja2
      base.html
      stories/ ...
      subtasks/ ...
      testcase_execute.html   # Section 1-4 layout
    static/
      js/
      css/
    docx/
      Template_Artifact_V1.docx
      builder.py            # fills template from DB data
    uploads/
      screenshots/{testcase_id}/...
      exports/
  qa_toolbox.db            # sqlite file, gitignored
  requirements.txt
  README.md
```

## Core hierarchy (mirrors Jira)
Story → Phase (SIT / STAGING / STAGING_AFTER_ROLLBACK / SANITY, testing
starts from SIT) → Subtask

5 subtask types per phase: Test Planning, Test Data Preparation,
`<Phase> <Title>` (execution), Test Automation, Test Reporting.

**STAGING_AFTER_ROLLBACK phase skips the 5-subtask breakdown** — only 1
execution-type subtask, no separate planning/data-prep/automation/
reporting subtasks.

Under execution subtask: TestCases and Bug tickets
(bug title convention: `[ISSUE] <description>`). TestCase and Bug are
**mandatory linked to a subtask** — no orphans.

## Code/ID convention
Applies to Story, Subtask, TestCase, Bug.
- User types 2 fields only: `display_code` (e.g. `EX-049`, matches real
  Jira code) + `title`
- `internal_key` (random string, e.g. uuid4 hex) auto-generated silently,
  DB uniqueness only — never shown/typed by user
- No auto-incrementing counter, codes 100% manual entry (Jira integration
  deferred)

## DB schema (core tables)
- `story`: id, display_code, title, internal_key, created_at
- `phase`: id, story_id FK, type (SIT/STAGING/STAGING_AFTER_ROLLBACK/SANITY)
- `subtask`: id, phase_id FK, display_code, title, internal_key,
  subtask_type
- `testcase`: id, subtask_id FK (mandatory), display_code, title,
  internal_key
- `bug`: id, subtask_id FK (mandatory), display_code, title, internal_key
- `curl_collection`: id, attach_type (story/subtask), attach_id, raw_text,
  method, url, headers (json), body
- `testcase_step`: id, testcase_id FK, section
  (precondition/main/postcondition), step_no, step_text, expected_result,
  actual_result
- `screenshot`: id, step_id FK, file_path, uploaded_at

Constraints enforced in code (not just DB):
- STAGING_AFTER_ROLLBACK phase blocks creation of other 4 subtask types
- testcase/bug forms require subtask_id, no orphan save
- internal_key generated server-side, never exposed in forms

## Curl collection feature
Attaches to either Story or Subtask level. Stores raw curl text (verbatim)
+ parsed fields (method/url/headers/body) for display + future re-run.

## Execution Test Case page
Every testcase links to a subtask. Layout:
- Section 1: Description/header info
- Section 2: Pre Condition
- Section 3: Main Test
- Section 4: Post Condition

Each step (section 2-4): No, Step, Expected Result, Actual Result,
Screenshot. Screenshot capture via clipboard paste (click zone, Ctrl+V,
direct upload). Multiple screenshots per step allowed. Multiple steps =
Option A, each step its own full stacked block (matches docx template
structure — see below).

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

**Builder logic** (`docx/builder.py`):
1. Load template fresh per export, never mutate source file
2. Fill table 0 cell(row, 3) per field from testcase/subtask/story data
3. Per section, step 1 uses existing table; step 2+ clones table XML,
   inserts after; fill No/Step/Actual/Expected; insert screenshot(s) into
   row3 merged cell (`add_run().add_picture(path, width=...)`)
4. Multiple screenshots per step: multiple `add_picture` calls in same
   row3 cell
5. Save as `{project}_{scenario}_{date}.docx` under `uploads/exports/`

## Routes (high level)
- `/stories` CRUD, `/stories/{id}/phases`
- `/subtasks` CRUD (scoped under phase)
- `/testcases/{id}/execute` — Section 1-4 page,
  `POST /testcases/{id}/steps/{step_id}/screenshot` for paste-upload
- `/curls` attach/list per story or subtask
- `/testcases/{id}/export-docx` — runs builder.py, filename
  `{project}_{scenario}_{date}.docx`

## requirements.txt
fastapi, uvicorn, sqlalchemy, jinja2, python-multipart, python-docx.
No pandas/openpyxl (Windows build error previously, add unpinned later
only if Excel import gets built).

## Tooling/environment notes
User runs Windows (PowerShell) — avoid heavy/no-wheel pip deps.
