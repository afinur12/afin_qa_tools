from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, backfill_column, engine, ensure_columns, migrate_table
from app.master_data import migrate_free_text_to_master, migrate_testcase_tester_to_user, seed_defaults
from app.routers import api_client, bugs, labels, prebuilt, notes, dashboard, docx_export, execution, screenshots, settings, stories, subtasks, testcases, users, utility
from app.variables import seed_builtin_variables

Base.metadata.create_all(bind=engine)
ensure_columns("prebuilt_testcases", {
    "service_name": "VARCHAR(64)", "test_type": "VARCHAR(64)", "simulate": "VARCHAR(32)", "remark": "TEXT",
})
ensure_columns("api_requests", {"position": "INTEGER NOT NULL DEFAULT 0"})
ensure_columns("stories", {"status": "VARCHAR(32) NOT NULL DEFAULT 'TO_DO'"})
ensure_columns("subtasks", {"status": "VARCHAR(32) NOT NULL DEFAULT 'TO_DO'"})
ensure_columns("prebuilt_testcases", {
    "service_id": "INTEGER", "simulate_id": "INTEGER", "test_type_id": "INTEGER",
})
ensure_columns("testcases", {"test_type_id": "INTEGER"})
ensure_columns("stories", {"assignee_id": "INTEGER", "tester_id": "INTEGER", "developer_id": "INTEGER"})
ensure_columns("subtasks", {"assignee_id": "INTEGER", "tester_id": "INTEGER", "developer_id": "INTEGER"})
ensure_columns("testcases", {"assignee_id": "INTEGER", "tester_id": "INTEGER", "developer_id": "INTEGER"})
ensure_columns("bugs", {"assignee_id": "INTEGER", "tester_id": "INTEGER", "developer_id": "INTEGER"})
ensure_columns("testcases", {"tester_migrated": "BOOLEAN"})
ensure_columns("testcases", {
    "category": "VARCHAR(32)", "msisdn": "TEXT", "planned_cost": "VARCHAR(64)",
    "actual_cost": "VARCHAR(64)", "number_of_iteration": "INTEGER", "jira_execution_id": "VARCHAR(32)",
})
ensure_columns("users", {"jira_username": "VARCHAR(64)"})
# service_name was briefly named "category"; carry over any values already saved under that name.
backfill_column("prebuilt_testcases", dest="service_name", src="category")
# Note replaces the curl-only CurlCollection; carry over anything already saved there.
migrate_table("notes", "curl_collections", {
    "id": "id", "attach_type": "attach_type", "attach_id": "attach_id",
    "language": "'CURL'", "content": "raw_text", "remark": "NULL", "created_at": "created_at",
})
with SessionLocal() as _seed_db:
    seed_builtin_variables(_seed_db)
    seed_defaults(_seed_db)
    migrate_free_text_to_master(_seed_db)
    migrate_testcase_tester_to_user(_seed_db)

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
app.include_router(api_client.router)
app.include_router(prebuilt.router)
app.include_router(users.router)
app.include_router(labels.router)
app.include_router(settings.router)
app.include_router(notes.router)
app.include_router(utility.router)
app.include_router(docx_export.router)
