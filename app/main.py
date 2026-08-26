from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import bugs, prebuilt, curls, dashboard, docx_export, execution, screenshots, stories, subtasks, testcases

Base.metadata.create_all(bind=engine)

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
app.include_router(curls.router)
app.include_router(docx_export.router)
