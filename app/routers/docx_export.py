import io
import re
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.docx.builder import SECTION_ORDER, build_docx
from app.models import TestCase

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EXPORTS_DIR = Path("app/uploads/exports")

# Characters Windows (and the zip/Content-Disposition round trip) will not
# accept in a name. Spaces, hyphens and parentheses are kept so the exported
# name reads the way the user asked for it: "<code> - <title>".
_ILLEGAL_FILENAME_CHARS = r'[<>:"/\\|?*\x00-\x1f]'


def _safe_filename(text: str, fallback: str = "export") -> str:
    cleaned = re.sub(_ILLEGAL_FILENAME_CHARS, "", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned[:120] or fallback


def _testcase_basename(testcase: TestCase) -> str:
    """"<code> - <title>", the stem shared by both exports."""
    return _safe_filename(f"{testcase.display_code} - {testcase.title}")


def _content_disposition(filename: str) -> str:
    """Attachment header carrying the exact name, including non-ASCII."""
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "export"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/testcases/{testcase_id}/export-docx")
def export_docx(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    filename = f"{_testcase_basename(testcase)}.docx"

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORTS_DIR / filename
    build_docx(testcase, str(output_path))

    return FileResponse(
        path=str(output_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/testcases/{testcase_id}/export-images")
def export_images(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    """Every screenshot on the test case, zipped.

    Entries are named "<SECTION>.<step number>_<step name><ext>", ordered by
    section then step number. A step carrying several screenshots gets an
    index suffix so no entry is overwritten.
    """
    from app.routers.screenshots import UPLOADS_DIR

    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    steps_by_section: dict[str, list] = {name: [] for name in SECTION_ORDER}
    for step in testcase.steps:
        steps_by_section[step.section.value].append(step)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for section_name in SECTION_ORDER:
            for step in sorted(steps_by_section[section_name], key=lambda s: s.step_no):
                step_name = _safe_filename(step.step_text, fallback="step")
                stem = f"{section_name}.{step.step_no}_{step_name}"
                for index, screenshot in enumerate(step.screenshots):
                    source = UPLOADS_DIR / screenshot.file_path
                    if not source.exists():
                        continue
                    suffix = source.suffix or ".png"
                    entry = stem if index == 0 else f"{stem}_{index + 1}"
                    archive.write(source, f"{entry}{suffix}")

    buffer.seek(0)
    filename = f"{_testcase_basename(testcase)}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )
