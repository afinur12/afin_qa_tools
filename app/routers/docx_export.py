import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.docx.builder import build_docx
from app.models import TestCase

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EXPORTS_DIR = Path("app/uploads/exports")


def _safe_filename_part(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "export"


@router.get("/testcases/{testcase_id}/export-docx")
def export_docx(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    project = _safe_filename_part(testcase.subtask.phase.story.title)
    scenario = _safe_filename_part(testcase.subtask.title)
    today = date.today().isoformat()
    filename = f"{project}_{scenario}_{today}.docx"

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORTS_DIR / filename
    build_docx(testcase, str(output_path))

    return FileResponse(
        path=str(output_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
