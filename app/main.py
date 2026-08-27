from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.database import Base, backfill_column, engine, ensure_columns, migrate_table
from app.routers import bugs, prebuilt, notes, dashboard, docx_export, execution, screenshots, stories, subtasks, testcases, utility

Base.metadata.create_all(bind=engine)
ensure_columns("prebuilt_testcases", {
    "service_name": "VARCHAR(64)", "test_type": "VARCHAR(64)", "simulate": "VARCHAR(32)", "remark": "TEXT",
})
# service_name was briefly named "category"; carry over any values already saved under that name.
backfill_column("prebuilt_testcases", dest="service_name", src="category")
# Note replaces the curl-only CurlCollection; carry over anything already saved there.
migrate_table("notes", "curl_collections", {
    "id": "id", "attach_type": "attach_type", "attach_id": "attach_id",
    "language": "'CURL'", "content": "raw_text", "remark": "NULL", "created_at": "created_at",
})

app = FastAPI(title="QA Toolbox")

Path("app/static").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

Path("app/uploads/screenshots").mkdir(parents=True, exist_ok=True)
Path("app/uploads/exports").mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="app/uploads"), name="uploads")

from app.templating import templates  # noqa: F401  (shared Jinja env)

app.include_router(dashboard.router)
app.include_router(stories.router)
app.include_router(subtasks.router)
app.include_router(testcases.router)
app.include_router(execution.router)
app.include_router(screenshots.router)
app.include_router(bugs.router)
app.include_router(prebuilt.router)
app.include_router(notes.router)
app.include_router(utility.router)
app.include_router(docx_export.router)
