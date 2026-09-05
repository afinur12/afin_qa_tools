"""Two routes for the Jira Sync feature: export a Subtask's test cases as
Jira/Zephyr-shaped JSON, and import that same shape back in. See
app/jira_io.py for the actual field mapping — these routes are thin
wrappers, following the same shape as every other import/export route in
this app (app/routers/docx_export.py's JSON routes, app/routers/subtasks.py's
import_subtask)."""

import json

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import redirect_with_flash
from app.jira_io import apply_jira_json_to_subtask, subtask_to_jira_json
from app.models import Subtask
from app.routers.docx_export import _content_disposition, _safe_filename
from app.templating import templates

router = APIRouter()


@router.get("/subtasks/{subtask_id}/export-jira-json")
def export_jira_json(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    data = subtask_to_jira_json(subtask, db)
    filename = f"{_safe_filename(subtask.display_code)} - jira export.json"
    return Response(
        json.dumps(data, indent=2), media_type="application/json",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.post("/subtasks/{subtask_id}/import-jira-json")
async def import_jira_json(request: Request, subtask_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    try:
        data = json.loads(await file.read())
    except json.JSONDecodeError:
        return redirect_with_flash(f"/subtasks/{subtask_id}", "That file isn't valid JSON.", category="danger")
    try:
        apply_jira_json_to_subtask(db, subtask, data)
    except ValueError as exc:
        db.rollback()
        return redirect_with_flash(f"/subtasks/{subtask_id}", str(exc), category="danger")
    db.commit()
    return redirect_with_flash(f"/subtasks/{subtask_id}", f"Jira data imported into {subtask.display_code}.")
