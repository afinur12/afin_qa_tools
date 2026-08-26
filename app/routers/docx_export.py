import io
import re
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.docx.builder import SECTION_FILE_LABELS, build_docx
from app.models import TestCase

router = APIRouter()

EXPORTS_DIR = Path("app/uploads/exports")

# Characters Windows (and the zip/Content-Disposition round trip) will not
# accept in a name. Spaces, hyphens and parentheses are kept so the exported
# name reads the way the user asked for it: "<code> - <title>".
_ILLEGAL_FILENAME_CHARS = r'[<>:"/\\|?*\x00-\x1f]'


def _section_letter(index: int) -> str:
    """A, B, ... Z, AA, AB — matching Word's Heading1 numbering."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


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

    Entries are named "<letter>.<SECTION>_<step number>.<step name><ext>" --
    e.g. "A.PRE-CONDITION_1.check.png" -- ordered by section then step. The
    leading letter is the section's heading letter in the exported document.
    A step carrying several screenshots gets an index suffix so no entry is
    overwritten.
    """
    from app.routers.screenshots import UPLOADS_DIR

    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for section_index, section in enumerate(testcase.sections):
            # Entries lead with the section's heading letter, matching the
            # A/B/C/D Word gives the headings in the exported document. That
            # also keeps repeated kinds apart without a separate counter.
            section_name = f"{_section_letter(section_index)}.{SECTION_FILE_LABELS[section.kind]}"
            for step in section.steps:
                step_name = _safe_filename(step.step_text, fallback="step")
                stem = f"{section_name}_{step.step_no}.{step_name}"
                for shot_index, screenshot in enumerate(step.screenshots):
                    source = UPLOADS_DIR / screenshot.file_path
                    if not source.exists():
                        continue
                    suffix = source.suffix or ".png"
                    entry = stem if shot_index == 0 else f"{stem}_{shot_index + 1}"
                    archive.write(source, f"{entry}{suffix}")

    buffer.seek(0)
    filename = f"{_testcase_basename(testcase)}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )
