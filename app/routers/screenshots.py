import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Screenshot, TestCaseStep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

UPLOADS_DIR = Path("app/uploads")


@router.post("/testcases/{testcase_id}/steps/{step_id}/screenshot")
async def upload_screenshot(
    request: Request,
    testcase_id: int,
    step_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    step = db.get(TestCaseStep, step_id)
    if step is None or step.testcase_id != testcase_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    extension = mimetypes.guess_extension(file.content_type or "") or ".bin"
    filename = f"{uuid.uuid4().hex}{extension}"
    relative_path = f"screenshots/{testcase_id}/{step_id}/{filename}"
    disk_path = UPLOADS_DIR / relative_path
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(await file.read())

    screenshot = Screenshot(step_id=step_id, file_path=relative_path)
    db.add(screenshot)
    db.commit()
    db.refresh(screenshot)

    # The paste handler asks for JSON so it can drop the thumbnail straight
    # into the page; without a reload the caret and scroll position never
    # move. A plain form post still gets the redirect.
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            {"id": screenshot.id, "url": f"/uploads/{screenshot.file_path}", "step_id": step_id}
        )
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/screenshots/{screenshot_id}/delete")
def delete_screenshot(request: Request, screenshot_id: int, db: Session = Depends(get_db)):
    screenshot = db.get(Screenshot, screenshot_id)
    if screenshot is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    testcase_id = screenshot.step.testcase_id
    disk_path = UPLOADS_DIR / screenshot.file_path
    if disk_path.exists():
        disk_path.unlink()
    db.delete(screenshot)
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)
