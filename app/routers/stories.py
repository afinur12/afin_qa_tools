from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CurlAttachType, CurlCollection, Phase, PhaseType, Story, generate_internal_key

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/stories")
def list_stories(request: Request, db: Session = Depends(get_db)):
    stories = db.query(Story).order_by(Story.created_at.desc()).all()
    return templates.TemplateResponse(request, "stories/list.html", {"stories": stories})


@router.get("/stories/new")
def new_story_form(request: Request):
    return templates.TemplateResponse(
        request, "stories/form.html", {"story": None, "error": None, "values": {"display_code": "", "title": ""}}
    )


@router.post("/stories")
def create_story(
    request: Request,
    display_code: str = Form(...),
    title: str = Form(...),
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
                "values": {"display_code": display_code, "title": title},
            },
            status_code=422,
        )
    story = Story(display_code=display_code, title=title, internal_key=generate_internal_key())
    db.add(story)
    db.commit()
    db.refresh(story)
    return RedirectResponse(url=f"/stories/{story.id}", status_code=303)


def _available_phase_types(story: Story) -> list[PhaseType]:
    used = {p.type for p in story.phases}
    return [t for t in PhaseType if t not in used]


@router.get("/stories/{story_id}")
def story_detail(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    curls = db.query(CurlCollection).filter(
        CurlCollection.attach_type == CurlAttachType.STORY, CurlCollection.attach_id == story_id
    ).all()
    return templates.TemplateResponse(
        request,
        "stories/detail.html",
        {"story": story, "available_phase_types": _available_phase_types(story), "error": None, "curls": curls},
    )


@router.get("/stories/{story_id}/edit")
def edit_story_form(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "stories/form.html",
        {"story": story, "error": None, "values": {"display_code": story.display_code, "title": story.title}},
    )


@router.post("/stories/{story_id}/edit")
def update_story(
    request: Request,
    story_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = db.query(Story).filter(Story.display_code == display_code, Story.id != story_id).first()
    if conflict:
        return templates.TemplateResponse(
            request,
            "stories/form.html",
            {
                "story": story,
                "error": f'Code "{display_code}" is already used by another story.',
                "values": {"display_code": display_code, "title": title},
            },
            status_code=422,
        )
    story.display_code = display_code
    story.title = title
    db.commit()
    return RedirectResponse(url=f"/stories/{story.id}", status_code=303)


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
            },
            status_code=422,
        )
    db.delete(story)
    db.commit()
    return RedirectResponse(url="/stories", status_code=303)


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
            {"story": story, "available_phase_types": available, "error": "Invalid or already-used phase type."},
            status_code=422,
        )
    db.add(Phase(story_id=story.id, type=phase_type))
    db.commit()
    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)


@router.post("/phases/{phase_id}/delete")
def delete_phase(request: Request, phase_id: int, db: Session = Depends(get_db)):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    if len(phase.subtasks) > 0:
        story = phase.story
        curls = db.query(CurlCollection).filter(
            CurlCollection.attach_type == CurlAttachType.STORY, CurlCollection.attach_id == story.id
        ).all()
        return templates.TemplateResponse(
            request,
            "stories/detail.html",
            {
                "story": story,
                "available_phase_types": _available_phase_types(story),
                "error": f"Delete {len(phase.subtasks)} subtask(s) first.",
                "curls": curls,
            },
            status_code=422,
        )
    story_id = phase.story_id
    db.delete(phase)
    db.commit()
    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)
