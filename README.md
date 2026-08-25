# QA Toolbox

Local-only web app for API/microservices software testing work: documentation
generator (docx test report export) and test tracking. Runs entirely on
`localhost` — no auth, no external services, SQLite for storage.

## Setup

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

## Run

    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000

## Test

    pytest
