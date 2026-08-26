# QA Toolbox

Local-only web app for API/microservices software testing work: documentation
generator (docx test report export), test tracking, and reusable prebuilt
test case templates. Runs entirely on `localhost` — no auth, no external
services, SQLite for storage.

**Version:** 1.0.0-alpha.1

## Quick start (GUI launcher, recommended)

The easiest way to run this on Windows: build `QA Toolbox Launcher.exe`
(see [Building the launcher](#building-the-launcher-exe) below), then just
double-click it. It's a small always-on-top-free window with:

- **Start / Stop** — runs the web app in the background, no terminal needed
- **Open in browser** — opens http://127.0.0.1:8000 once running
- **Setup / Install Dependencies** — creates a `.venv` next to the exe and
  installs `requirements.txt` into it; run this once before the first Start
- **Backup Data (db + images)** — zips `qa_toolbox.db` plus
  `app/uploads/screenshots` and `app/uploads/exports` into `backups/`
- **Import Backup...** — restores db + uploads from a previously saved
  backup zip (overwrites current data — confirms first)
- **Reset / Clear All Data** — wipes the database and all uploads; requires
  typing `DELETE ALL` to confirm

The exe expects to sit next to `app/`, `requirements.txt`, and
`qa_toolbox.db` — i.e. at the repo root, not inside `dist/`.

## Manual setup (any OS)

    python -m venv .venv
    .venv\Scripts\activate          # Windows
    source .venv/bin/activate       # macOS/Linux
    pip install -r requirements.txt

## Run

    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000

## Test

    pytest

## Building the launcher exe

Requires `pyinstaller` (`pip install pyinstaller`, not in
`requirements.txt` since it's a build-time tool, not a runtime dependency).
From the repo root:

    pyinstaller --onefile --noconsole --name "QA Toolbox Launcher" --distpath . --workpath build --specpath build launcher.py

This drops `QA Toolbox Launcher.exe` at the repo root (`--distpath .`) so
its own directory matches where `app/` and `requirements.txt` live. `build/`
and the generated `.spec` file are gitignored — safe to delete and
regenerate any time.

## Syntax highlighting in the Note Section

Snippets saved in the Note Section (curl, SQL, JSON, etc.) are
syntax-highlighted client-side using a locally vendored copy of
highlight.js — no CDN, nothing fetched at runtime. See
`app/static/js/vendor/highlightjs/README.md` if you need to add a language
or update the version.
