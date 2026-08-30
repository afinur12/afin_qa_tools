import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app import deletion
from app.database import get_db
from app.flash import redirect_with_flash
from app.templating import templates
from app.models import Note, NoteAttachType, Phase, PhaseType, PrebuiltTestCase, Subtask, SubtaskType, generate_internal_key
from app.testcase_io import dict_to_subtask

router = APIRouter()


def _allowed_subtask_types(phase: Phase) -> list[SubtaskType]:
    return phase.allowed_subtask_types


@router.get("/phases/{phase_id}/subtasks/new")
def new_subtask_form(request: Request, phase_id: int, db: Session = Depends(get_db)):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "subtasks/form.html",
        {
            "subtask": None,
            "phase": phase,
            "allowed_types": _allowed_subtask_types(phase),
            "error": None,
            "values": {"display_code": "", "title": "", "subtask_type": ""},
        },
    )


@router.post("/phases/{phase_id}/subtasks")
def create_subtask(
    request: Request,
    phase_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    subtask_type: str = Form(...),
    db: Session = Depends(get_db),
):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    allowed = _allowed_subtask_types(phase)
    try:
        st_type = SubtaskType(subtask_type)
    except ValueError:
        st_type = None

    error = None
    if st_type is None or st_type not in allowed:
        error = "That subtask type isn't allowed for this phase."
    elif db.query(Subtask).filter(Subtask.phase_id == phase.id, Subtask.display_code == display_code).first():
        error = f'Code "{display_code}" is already used in this phase.'

    if error:
        return templates.TemplateResponse(
            request,
            "subtasks/form.html",
            {
                "subtask": None,
                "phase": phase,
                "allowed_types": allowed,
                "error": error,
                "values": {"display_code": display_code, "title": title, "subtask_type": subtask_type},
            },
            status_code=422,
        )

    subtask = Subtask(
        phase_id=phase.id,
        display_code=display_code,
        title=title,
        internal_key=generate_internal_key(),
        subtask_type=st_type,
    )
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return redirect_with_flash(f"/subtasks/{subtask.id}", f"Subtask {subtask.display_code} created.")


@router.post("/phases/{phase_id}/subtasks/import")
async def import_subtask(request: Request, phase_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    try:
        data = json.loads(await file.read())
    except json.JSONDecodeError:
        return redirect_with_flash(f"/stories/{phase.story_id}", "That file isn't valid JSON.", category="danger")
    try:
        subtask = dict_to_subtask(db, phase_id, data)
    except ValueError as exc:
        db.rollback()
        return redirect_with_flash(f"/stories/{phase.story_id}", str(exc), category="danger")
    db.commit()
    return redirect_with_flash(f"/subtasks/{subtask.id}", f"Subtask {subtask.display_code} imported.")


@router.get("/subtasks/{subtask_id}")
def subtask_detail(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    notes = db.query(Note).filter(
        Note.attach_type == NoteAttachType.SUBTASK, Note.attach_id == subtask_id
    ).all()
    return templates.TemplateResponse(
        request,
        "subtasks/detail.html",
        {
            "subtask": subtask, "error": None, "notes": notes,
            "prebuilts": db.query(PrebuiltTestCase).order_by(PrebuiltTestCase.name).all(),
        },
    )


@router.get("/subtasks/{subtask_id}/edit")
def edit_subtask_form(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "subtasks/form.html",
        {
            "subtask": subtask,
            "phase": subtask.phase,
            "allowed_types": _allowed_subtask_types(subtask.phase) or [subtask.subtask_type],
            "error": None,
            "values": {
                "display_code": subtask.display_code,
                "title": subtask.title,
                "subtask_type": subtask.subtask_type.value,
                "notes": subtask.notes or "",
            },
        },
    )


@router.post("/subtasks/{subtask_id}/edit")
def update_subtask(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = (
        db.query(Subtask)
        .filter(Subtask.phase_id == subtask.phase_id, Subtask.display_code == display_code, Subtask.id != subtask_id)
        .first()
    )
    if conflict:
        return templates.TemplateResponse(
            request,
            "subtasks/form.html",
            {
                "subtask": subtask,
                "phase": subtask.phase,
                "allowed_types": [subtask.subtask_type],
                "error": f'Code "{display_code}" is already used in this phase.',
                "values": {"display_code": display_code, "title": title, "subtask_type": subtask.subtask_type.value, "notes": notes},
            },
            status_code=422,
        )
    subtask.display_code = display_code
    subtask.title = title
    subtask.notes = notes
    db.commit()
    return redirect_with_flash(f"/subtasks/{subtask.id}", f"Subtask {subtask.display_code} updated.")


@router.post("/subtasks/{subtask_id}/delete")
def delete_subtask(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    story_id = subtask.phase.story_id
    code = subtask.display_code
    # Cascades to its test cases (and their steps/screenshots) and bugs, so
    # the subtask can be removed without emptying it first.
    deletion.delete_subtask(db, subtask)
    db.commit()
    return redirect_with_flash(f"/stories/{story_id}", f"Subtask {code} deleted.", category="danger")
