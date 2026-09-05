import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import redirect_with_flash
from app.templating import templates
from app.models import Label, LabelAttachType, Note, NoteAttachType, Phase, PhaseType, Story, TaskStatus, User, UserType, generate_internal_key
from app.labels import clear_labels, get_labels, set_labels
from app.testcase_io import dict_to_task

router = APIRouter()


def _user_dropdowns(db: Session) -> dict:
    return {
        "testers": db.query(User).filter(User.type == UserType.TESTER).order_by(User.name).all(),
        "developers": db.query(User).filter(User.type == UserType.DEVELOPER).order_by(User.name).all(),
        "assignees": db.query(User).order_by(User.name).all(),
        "all_labels": db.query(Label).order_by(Label.name).all(),
    }


def _parse_id(raw: str) -> int | None:
    return int(raw) if raw.strip().isdecimal() else None


@router.get("/stories")
def list_stories(request: Request, db: Session = Depends(get_db)):
    stories = db.query(Story).order_by(Story.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "stories/list.html", {"stories": stories, **_user_dropdowns(db)}
    )


@router.get("/stories/new")
def new_story_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "stories/form.html",
        {
            "story": None, "error": None,
            "values": {"display_code": "", "title": "", "assignee_id": "", "tester_id": "", "developer_id": ""},
            "current_label_ids": [],
            **_user_dropdowns(db),
        },
    )


@router.post("/stories")
def create_story(
    request: Request,
    display_code: str = Form(...),
    title: str = Form(...),
    assignee_id: str = Form(""),
    tester_id: str = Form(""),
    developer_id: str = Form(""),
    label_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    display_code = display_code.strip()
    title = title.strip()
    if db.query(Story).filter(Story.display_code == display_code).first():
        return templates.TemplateResponse(
            request,
            "stories/form.html",
            {
                "story": None,
                "error": f'Code "{display_code}" is already used by another story.',
                "values": {
                    "display_code": display_code, "title": title,
                    "assignee_id": assignee_id, "tester_id": tester_id, "developer_id": developer_id,
                },
                "current_label_ids": label_ids,
                **_user_dropdowns(db),
            },
            status_code=422,
        )
    story = Story(
        display_code=display_code, title=title, internal_key=generate_internal_key(),
        assignee_id=_parse_id(assignee_id), tester_id=_parse_id(tester_id), developer_id=_parse_id(developer_id),
    )
    db.add(story)
    db.flush()
    set_labels(db, LabelAttachType.STORY, story.id, label_ids)
    db.commit()
    db.refresh(story)
    return redirect_with_flash(f"/stories/{story.id}", f"Story {story.display_code} created.")


@router.post("/stories/import")
async def import_story(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        data = json.loads(await file.read())
    except json.JSONDecodeError:
        return redirect_with_flash("/stories", "That file isn't valid JSON.", category="danger")
    try:
        story = dict_to_task(db, data)
    except ValueError as exc:
        db.rollback()
        return redirect_with_flash("/stories", str(exc), category="danger")
    db.commit()
    return redirect_with_flash(f"/stories/{story.id}", f"Task {story.display_code} imported.")


def _available_phase_types(story: Story) -> list[PhaseType]:
    used = {p.type for p in story.phases}
    return [t for t in PhaseType if t not in used]


@router.get("/stories/{story_id}")
def story_detail(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    notes = db.query(Note).filter(
        Note.attach_type == NoteAttachType.STORY, Note.attach_id == story_id
    ).all()
    return templates.TemplateResponse(
        request,
        "stories/detail.html",
        {
            "story": story, "available_phase_types": _available_phase_types(story), "error": None, "notes": notes,
            "statuses": list(TaskStatus),
            "story_labels": get_labels(db, LabelAttachType.STORY, story_id),
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.STORY, story_id)],
            **_user_dropdowns(db),
        },
    )


@router.get("/stories/{story_id}/edit")
def edit_story_form(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "stories/form.html",
        {
            "story": story,
            "error": None,
            "statuses": list(TaskStatus),
            "values": {
                "display_code": story.display_code, "title": story.title, "status": story.status.value,
                "assignee_id": str(story.assignee_id or ""), "tester_id": str(story.tester_id or ""),
                "developer_id": str(story.developer_id or ""),
            },
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.STORY, story_id)],
            **_user_dropdowns(db),
        },
    )


@router.post("/stories/{story_id}/edit")
def update_story(
    request: Request,
    story_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    status: str = Form(...),
    assignee_id: str = Form(""),
    tester_id: str = Form(""),
    developer_id: str = Form(""),
    label_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = db.query(Story).filter(Story.display_code == display_code, Story.id != story_id).first()
    try:
        status_enum = TaskStatus(status)
    except ValueError:
        conflict = True  # reuse the same error branch below for any invalid enum value

    if conflict:
        return templates.TemplateResponse(
            request,
            "stories/form.html",
            {
                "story": story,
                "error": f'Code "{display_code}" is already used by another story, or the status was invalid.',
                "statuses": list(TaskStatus),
                "values": {
                    "display_code": display_code, "title": title, "status": status,
                    "assignee_id": assignee_id, "tester_id": tester_id, "developer_id": developer_id,
                },
                "current_label_ids": label_ids,
                **_user_dropdowns(db),
            },
            status_code=422,
        )
    story.display_code = display_code
    story.title = title
    story.status = status_enum
    story.assignee_id = _parse_id(assignee_id)
    story.tester_id = _parse_id(tester_id)
    story.developer_id = _parse_id(developer_id)
    set_labels(db, LabelAttachType.STORY, story.id, label_ids)
    db.commit()
    return redirect_with_flash(f"/stories/{story.id}", f"Story {story.display_code} updated.")


@router.post("/stories/{story_id}/delete")
def delete_story(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    if len(story.phases) > 0:
        return templates.TemplateResponse(
            request,
            "stories/detail.html",
            {
                "story": story,
                "available_phase_types": _available_phase_types(story),
                "error": f"Delete {len(story.phases)} phase(s) first.",
                "statuses": list(TaskStatus),
                "story_labels": get_labels(db, LabelAttachType.STORY, story.id),
                "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.STORY, story.id)],
                **_user_dropdowns(db),
            },
            status_code=422,
        )
    code = story.display_code
    clear_labels(db, LabelAttachType.STORY, story.id)
    db.delete(story)
    db.commit()
    return redirect_with_flash("/stories", f"Story {code} deleted.", category="danger")


@router.post("/stories/{story_id}/phases")
def create_phase(request: Request, story_id: int, type: str = Form(...), db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    available = _available_phase_types(story)
    try:
        phase_type = PhaseType(type)
    except ValueError:
        phase_type = None
    if phase_type is None or phase_type not in available:
        return templates.TemplateResponse(
            request,
            "stories/detail.html",
            {
                "story": story, "available_phase_types": available, "error": "Invalid or already-used phase type.",
                "statuses": list(TaskStatus),
                "story_labels": get_labels(db, LabelAttachType.STORY, story.id),
                "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.STORY, story.id)],
                **_user_dropdowns(db),
            },
            status_code=422,
        )
    db.add(Phase(story_id=story.id, type=phase_type))
    db.commit()
    return redirect_with_flash(f"/stories/{story_id}", f"{phase_type.value} phase added.")


@router.post("/phases/{phase_id}/delete")
def delete_phase(request: Request, phase_id: int, db: Session = Depends(get_db)):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    if len(phase.subtasks) > 0:
        story = phase.story
        notes = db.query(Note).filter(
            Note.attach_type == NoteAttachType.STORY, Note.attach_id == story.id
        ).all()
        return templates.TemplateResponse(
            request,
            "stories/detail.html",
            {
                "story": story,
                "available_phase_types": _available_phase_types(story),
                "error": f"Delete {len(phase.subtasks)} subtask(s) first.",
                "notes": notes,
                "statuses": list(TaskStatus),
                "story_labels": get_labels(db, LabelAttachType.STORY, story.id),
                "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.STORY, story.id)],
                **_user_dropdowns(db),
            },
            status_code=422,
        )
    story_id = phase.story_id
    phase_label = phase.type.value
    db.delete(phase)
    db.commit()
    return redirect_with_flash(f"/stories/{story_id}", f"{phase_label} phase deleted.", category="danger")
