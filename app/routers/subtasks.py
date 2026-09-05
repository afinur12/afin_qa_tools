import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, selectinload

from app import deletion
from app.database import get_db
from app.flash import redirect_with_flash
from app.templating import templates
from app.models import LabelAttachType, Note, NoteAttachType, Phase, PhaseType, PrebuiltTestCase, Subtask, SubtaskType, TaskStatus, TestCase, generate_internal_key
from app.labels import get_labels, set_labels
from app.routers.stories import _parse_id, _user_dropdowns
from app.testcase_io import dict_to_subtask

router = APIRouter()


def _allowed_subtask_types(phase: Phase) -> list[SubtaskType]:
    return phase.allowed_subtask_types


def _next_subtask_position(phase: Phase) -> int:
    return max((subtask.position for subtask in phase.subtasks), default=-1) + 1


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
            "values": {
                "display_code": "", "title": "", "subtask_type": "",
                "assignee_id": "", "tester_id": "", "developer_id": "",
            },
            "current_label_ids": [],
            **_user_dropdowns(db),
        },
    )


@router.post("/phases/{phase_id}/subtasks")
def create_subtask(
    request: Request,
    phase_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    subtask_type: str = Form(...),
    assignee_id: str = Form(""),
    tester_id: str = Form(""),
    developer_id: str = Form(""),
    label_ids: list[int] = Form([]),
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
                "values": {
                    "display_code": display_code, "title": title, "subtask_type": subtask_type,
                    "assignee_id": assignee_id, "tester_id": tester_id, "developer_id": developer_id,
                },
                "current_label_ids": label_ids,
                **_user_dropdowns(db),
            },
            status_code=422,
        )

    subtask = Subtask(
        phase_id=phase.id,
        display_code=display_code,
        title=title,
        internal_key=generate_internal_key(),
        subtask_type=st_type,
        position=_next_subtask_position(phase),
        assignee_id=_parse_id(assignee_id), tester_id=_parse_id(tester_id), developer_id=_parse_id(developer_id),
    )
    db.add(subtask)
    db.flush()
    set_labels(db, LabelAttachType.SUBTASK, subtask.id, label_ids)
    db.commit()
    db.refresh(subtask)
    return redirect_with_flash(f"/subtasks/{subtask.id}", f"Subtask {subtask.display_code} created.")


@router.post("/phases/{phase_id}/subtasks/reorder")
def reorder_subtasks(request: Request, phase_id: int, order: str = Form(...), db: Session = Depends(get_db)):
    """Persist a new subtask order within a phase.

    ``order`` is a comma-separated list of subtask ids in their new order.
    Ids that don't belong to this phase are rejected outright rather than
    partially applied.
    """
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    by_id = {subtask.id: subtask for subtask in phase.subtasks}
    try:
        requested = [int(value) for value in order.split(",") if value.strip()]
    except ValueError:
        return Response("Invalid subtask order.", status_code=422)

    if sorted(requested) != sorted(by_id):
        return Response("Subtask order does not match this phase.", status_code=422)

    for position, subtask_id in enumerate(requested):
        by_id[subtask_id].position = position
    db.commit()
    return RedirectResponse(url=f"/stories/{phase.story_id}", status_code=303)


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
    subtask = db.get(
        Subtask, subtask_id,
        options=[selectinload(Subtask.testcases).selectinload(TestCase.test_priority_ref)],
    )
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
            "statuses": list(TaskStatus),
            "subtask_labels": get_labels(db, LabelAttachType.SUBTASK, subtask_id),
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.SUBTASK, subtask_id)],
            **_user_dropdowns(db),
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
            "statuses": list(TaskStatus),
            "values": {
                "display_code": subtask.display_code,
                "title": subtask.title,
                "subtask_type": subtask.subtask_type.value,
                "notes": subtask.notes or "",
                "status": subtask.status.value,
                "assignee_id": str(subtask.assignee_id or ""), "tester_id": str(subtask.tester_id or ""),
                "developer_id": str(subtask.developer_id or ""),
            },
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.SUBTASK, subtask_id)],
            **_user_dropdowns(db),
        },
    )


@router.post("/subtasks/{subtask_id}/edit")
def update_subtask(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    notes: str = Form(""),
    status: str = Form(...),
    assignee_id: str = Form(""),
    tester_id: str = Form(""),
    developer_id: str = Form(""),
    label_ids: list[int] = Form([]),
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
    try:
        status_enum = TaskStatus(status)
    except ValueError:
        conflict = True  # reuse the same error branch below for any invalid enum value

    if conflict:
        return templates.TemplateResponse(
            request,
            "subtasks/form.html",
            {
                "subtask": subtask,
                "phase": subtask.phase,
                "allowed_types": [subtask.subtask_type],
                "error": f'Code "{display_code}" is already used in this phase, or the status was invalid.',
                "values": {
                    "display_code": display_code, "title": title, "subtask_type": subtask.subtask_type.value,
                    "notes": notes, "status": status,
                    "assignee_id": assignee_id, "tester_id": tester_id, "developer_id": developer_id,
                },
                "current_label_ids": label_ids,
                **_user_dropdowns(db),
            },
            status_code=422,
        )
    subtask.display_code = display_code
    subtask.title = title
    subtask.notes = notes
    subtask.status = status_enum
    subtask.assignee_id = _parse_id(assignee_id)
    subtask.tester_id = _parse_id(tester_id)
    subtask.developer_id = _parse_id(developer_id)
    set_labels(db, LabelAttachType.SUBTASK, subtask.id, label_ids)
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
