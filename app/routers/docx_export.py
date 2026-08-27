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
from app.models import Story, Subtask, TestCase

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


def _write_testcase_docx(archive: zipfile.ZipFile, testcase: TestCase, prefix: str = "") -> None:
    """Builds one test case's docx and writes it into the zip under `prefix`."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = EXPORTS_DIR / f"_bulk_{testcase.id}.docx"
    build_docx(testcase, str(tmp_path))
    archive.write(tmp_path, f"{prefix}{_testcase_basename(testcase)}.docx")
    tmp_path.unlink(missing_ok=True)


def _write_testcase_images(archive: zipfile.ZipFile, testcase: TestCase, uploads_dir: Path, prefix: str = "") -> None:
    """Writes one test case's screenshots into the zip under `prefix`.

    Entries are named "<letter>.<SECTION>_<step number>.<step name><ext>",
    same scheme as the single-test-case export — see export_images below.
    """
    for section_index, section in enumerate(testcase.sections):
        section_name = f"{_section_letter(section_index)}.{SECTION_FILE_LABELS[section.kind]}"
        for step in section.steps:
            step_name = _safe_filename(step.step_text, fallback="step")
            stem = f"{section_name}_{step.step_no}.{step_name}"
            for shot_index, screenshot in enumerate(step.screenshots):
                source = uploads_dir / screenshot.file_path
                if not source.exists():
                    continue
                suffix = source.suffix or ".png"
                entry = stem if shot_index == 0 else f"{stem}_{shot_index + 1}"
                archive.write(source, f"{prefix}{entry}{suffix}")


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
        _write_testcase_images(archive, testcase, UPLOADS_DIR)

    buffer.seek(0)
    filename = f"{_testcase_basename(testcase)}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/subtasks/{subtask_id}/export-docx")
def export_subtask_docx(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    """Every test case in the subtask, one .docx each, flat in the zip."""
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for testcase in subtask.testcases:
            _write_testcase_docx(archive, testcase)

    buffer.seek(0)
    filename = f"{_safe_filename(subtask.display_code)} - all docx.zip"
    return StreamingResponse(
        buffer, media_type="application/zip", headers={"Content-Disposition": _content_disposition(filename)}
    )


@router.get("/subtasks/{subtask_id}/export-images")
def export_subtask_images(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    """Every screenshot in the subtask, grouped into one folder per test case."""
    from app.routers.screenshots import UPLOADS_DIR

    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for testcase in subtask.testcases:
            _write_testcase_images(archive, testcase, UPLOADS_DIR, prefix=f"{_testcase_basename(testcase)}/")

    buffer.seek(0)
    filename = f"{_safe_filename(subtask.display_code)} - all images.zip"
    return StreamingResponse(
        buffer, media_type="application/zip", headers={"Content-Disposition": _content_disposition(filename)}
    )


@router.get("/stories/{story_id}/export-docx")
def export_story_docx(request: Request, story_id: int, db: Session = Depends(get_db)):
    """Every test case across the whole task, one .docx each, in a folder per subtask."""
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for phase in story.phases:
            for subtask in phase.subtasks:
                if not subtask.testcases:
                    continue
                prefix = f"{_safe_filename(subtask.display_code)}/"
                for testcase in subtask.testcases:
                    _write_testcase_docx(archive, testcase, prefix=prefix)

    buffer.seek(0)
    filename = f"{_safe_filename(story.display_code)} - all docx.zip"
    return StreamingResponse(
        buffer, media_type="application/zip", headers={"Content-Disposition": _content_disposition(filename)}
    )


@router.get("/stories/{story_id}/export-images")
def export_story_images(request: Request, story_id: int, db: Session = Depends(get_db)):
    """Every screenshot across the whole task, in <subtask>/<test case>/ folders."""
    from app.routers.screenshots import UPLOADS_DIR

    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for phase in story.phases:
            for subtask in phase.subtasks:
                if not subtask.testcases:
                    continue
                subtask_prefix = f"{_safe_filename(subtask.display_code)}/"
                for testcase in subtask.testcases:
                    prefix = f"{subtask_prefix}{_testcase_basename(testcase)}/"
                    _write_testcase_images(archive, testcase, UPLOADS_DIR, prefix=prefix)

    buffer.seek(0)
    filename = f"{_safe_filename(story.display_code)} - all images.zip"
    return StreamingResponse(
        buffer, media_type="application/zip", headers={"Content-Disposition": _content_disposition(filename)}
    )
