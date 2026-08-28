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

## API Client tool (Postman/Insomnia-style, under Workspace nav)

Sidebar placement: `Workspace` group, ordered Dashboard, Tasks, Bugs,
**API Client**, Prebuilt (not under the `Utility` group — it has its own
top-level nav item, positioned directly below Bugs). Route `/api-client`.

Runs as a backend proxy (FastAPI + `httpx`, added to requirements.txt):
frontend never calls the target API directly, so requests ride whatever
network the local machine is on (e.g. Trend VPN tunnel) and never hit
browser CORS.

UI takes cues from Postman/Insomnia's interaction pattern (tree of
collections/folders, open-request tabs, section tabs with fill/count
indicators, stacked-vs-split layout toggle) — not their branding: stays
in QA Toolbox's own warm-neutral/dark-sidebar/lime-indigo system, no
Postman colors, icons, or illustrations copied.

### DB schema
- `api_collection`: id, name, created_at
- `api_folder`: id, collection_id FK, parent_folder_id FK (nullable,
  self-referencing — arbitrary nesting depth), name, position
- `api_request`: id, collection_id FK, folder_id FK (nullable — sits at
  collection root if unset), name, method, url, headers_json,
  params_json, body_type (none/json/form/raw), body, created_at,
  updated_at
- `api_variable`: id, scope (builtin/global/collection), collection_id
  FK (nullable), key, kind (value/script), value (nullable — used when
  kind=value), script (nullable — Python source, used when kind=script),
  description, is_sensitive (bool, default false — see redaction below)
- `api_history`: id, request_id FK (nullable), method, url,
  request_headers_json, request_body, response_status,
  response_headers_json, response_body, duration_ms,
  response_size_bytes, sent_at

`builtin` is not hardcoded in Python — it's a scope value like the
other two, seeded with 5 default rows on first run (`guid`,
`timestamp`, `timestamp_ms`, `iso_date`, `random_int`, all kind=script)
and fully user-editable/deletable/addable from there on. Resolution
precedence at send time: collection > global > builtin.

### 1. Collections — nested folders, many collections, import/export
- Sidebar is a recursive tree: many collections, each with many
  folders (arbitrary nesting) and requests; matches the mental model of
  a real Postman workspace but rendered in-app
- `POST /api-client/collections`, `POST /api-client/collections/{id}/folders`,
  `POST /api-client/requests` (save current builder state into a
  collection/folder)
- `GET /api-client/collections/{id}/export` → downloads collection
  (with its folder tree) as JSON (native QA-Toolbox schema v1; Postman
  v2.1 compatibility is a possible later stretch, not v1 scope)
- `POST /api-client/collections/import` → upload JSON, parse, create
  collection + folders + requests; name collisions get a numeric suffix
  rather than silently overwriting

### Open request tabs + layout toggle
- Multiple requests can be open at once in a browser-tab-style strip
  above the builder (client-side state, not persisted server-side —
  reopening the app starts fresh, same as Postman's unsaved-tab
  behavior for this v1)
- Stacked (request above response) vs. split (side-by-side) layout,
  toggled per-session; preference remembered in `localStorage` the same
  way the sidebar-collapsed state already is
  (`qa-toolbox:sidebar-collapsed` pattern → `qa-toolbox:api-client-layout`)

### 2. Paste-a-curl auto-conversion
Same paste-and-detect pattern already used for Note Section
(`ab514fa Auto-detect Note Section snippet type from what you paste`).
On paste into the URL bar: if the pasted text (trimmed) starts with
`curl `, run it through a small custom curl tokenizer (no external lib —
consistent with the rest of the app's zero-CDN utility tools):
- `-X`/`--request` → method (defaults to POST if `-d`/`--data*` present
  and no explicit method, else GET)
- first bare arg or `--url` → URL
- `-H`/`--header` (repeatable) → header rows
- `-d`/`--data`/`--data-raw`/`--data-binary` → Body tab, sets
  `Content-Type: application/x-www-form-urlencoded` if not already set
- `-u`/`--user` → `Authorization: Basic ...` header
- strips backslash line-continuations (handles curl copied multi-line
  from browser devtools "Copy as cURL")

Populates method dropdown, URL field, Headers rows, Body tab in one
shot; switches to whichever tab has content; toast confirms "Parsed
from curl". Non-curl paste behaves as a normal URL paste.

### 3. Template variables — `{{guid}}`, `{{timestamp}}`, etc.
Usable inside URL, header values, and body. Resolved server-side in the
`/api-client/send` route right before the `httpx` call (so time-based
values are fresh per send, and resolution logic lives in one place).

Built-ins ship as 5 seeded rows: `{{guid}}` (uuid4), `{{timestamp}}`
(unix seconds), `{{timestamp_ms}}`, `{{iso_date}}` (now, ISO 8601),
`{{random_int}}` — but are a full CRUD resource, not a fixed list. Own
page: `Workspace / API Client / Built-in Variables`, reachable via a
`Builder | Built-in Variables` sub-nav tab strip at the top of the API
Client page. Table layout matches Prebuilt Test Cases' list page
exactly (`card.flush` + table + row edit/delete icon buttons opening a
per-row modal) — Name, Kind, Preview, Description, actions columns.

User-defined variables (`api_variable` table, global or per-collection)
override/extend built-ins — e.g. `{{base_url}}`, `{{token}}`. Editable
via a small Variables panel (gear icon near Send). An unresolved
`{{name}}` at send time is left literal and flagged in the response
panel rather than silently sent broken.

Each user-defined variable is one of two kinds:
- **Value** — a plain static string (e.g. `{{base_url}}` →
  `https://api.workplace.internal/v1`)
- **Script** — a short Python snippet, re-executed fresh on *every*
  send (never cached), so e.g. `{{uuid}}` can return a new UUID each
  time the request runs. Runs server-side in a restricted namespace —
  a limited builtins set plus `uuid`, `time`, `datetime`, `random`,
  `hashlib`, `base64` — under a short timeout (~1s); a script error is
  caught and surfaced inline (in the Variables panel and the response
  panel), never a 500 or a silently-broken request.

Modal UI: each variable row picks Value or Script via a small toggle.
Script rows show the source in the same dark, line-numbered,
syntax-highlighted code-block style as Note Section snippets, with a
"Run" icon below it that re-executes once and shows the result as a
comment line (e.g. `# → 3f29ac1e-9b7d-...`) — a preview for authoring
only; actual resolution always re-runs the script at send time.

### 4. Sensitive-value redaction
A variable can be flagged `is_sensitive` (checkbox on its row in either
Variables modal). Auto-flagged by default the moment a header's *key*
matches a common pattern (case-insensitive: `authorization`, `cookie`,
`api-key`, `x-api-key`, `token`, `secret`, `password`) — user can
un-flag if a match is a false positive. A small lock icon sits next to
any header row using a sensitive-flagged value.

### 5. Export request/response as an image
Icon button (next to the layout toggle) renders the current
request+response cards to a PNG, client-side (a vendored DOM-to-image
lib, same local-vendoring pattern as `pdf-lib`/`pdfjs`/`qrcode` —
no CDN). Before rendering: clone the DOM subtree, find every element
whose value traces back to a sensitive-flagged variable (request
headers/body) and swap its text for a masked placeholder (`••••••••`);
also scan the response body for exact substring matches of any
currently-resolved sensitive value and mask those too (covers an API
echoing a token back). Only the masked clone is ever rasterized — the
real values never touch the canvas. Preview shown in a modal before
download, so nothing is masked "by surprise." Two ways to get the
result: **Download PNG** (saves a file) and **Copy Image** (writes the
rendered PNG straight to the clipboard via the Clipboard API —
`navigator.clipboard.write` with a `ClipboardItem`, works here since
the app is served from localhost — so it can be pasted directly into
Slack/Jira/a chat without a save-then-attach round trip).

### 6. Copy as cURL
Icon button next to Export Image. Unlike the exported image, this
copies a **fully runnable** curl command — real resolved values,
including a fresh run of any script variables (`{{uuid}}` etc.) —
since the whole point is pasting it into a terminal and having it work.
Needs a resolve-only round trip: `POST /api-client/resolve` runs the
same variable-resolution + curl-string-building logic as
`/api-client/send` but skips the `httpx` call. Toast confirms "curl
copied".

### 7. Request/response history
Every `/api-client/send` call logs one `api_history` row: id,
request_id FK (nullable — ad-hoc unsaved requests still get logged),
method, url, request_headers_json, request_body, response_status,
response_headers_json, response_body, duration_ms, response_size_bytes,
sent_at. New `History` sub-nav tab (alongside `Builder` and `Built-in
Variables`) lists past hits — method badge, URL, status badge, time,
relative "sent" timestamp — newest first. Row actions: open (loads the
saved request+response into the same read-only response-card view used
in the builder), Restore to Builder (loads it back into an editable
open tab), Copy as cURL, Export Image, Delete. History is local-only
data, never synced anywhere; a size cap (e.g. keep last 500 entries,
oldest pruned) avoids unbounded SQLite growth.

### Routes (API Client)
- `/api-client` — builder page
- `POST /api-client/send` — proxy: method/url/headers/body →
  `httpx` request → status/headers/body/time/size (structured error on
  timeout/connection failure, never a 500); logs an `api_history` row
- `POST /api-client/resolve` — same resolution logic as `/send` minus
  the actual `httpx` call, used to build the "Copy as cURL" string
- `/api-client/collections` CRUD, `/api-client/collections/{id}/folders`
  CRUD, `/api-client/collections/{id}/export`,
  `/api-client/collections/import`
- `/api-client/requests` CRUD (save/load builder state)
- `/api-client/variables/builtin` — Built-in Variables page (list +
  add/edit/delete), `/api-client/variables` CRUD (global/collection,
  used by the quick Variables panel)
- `/api-client/history` — History page (list), `/api-client/history/{id}`
  (detail, delete)

## requirements.txt
fastapi, uvicorn, sqlalchemy, jinja2, python-multipart, python-docx,
httpx (API Client proxy).
No pandas/openpyxl (Windows build error previously, add unpinned later
only if Excel import gets built).

## Tooling/environment notes
User runs Windows (PowerShell) — avoid heavy/no-wheel pip deps.
