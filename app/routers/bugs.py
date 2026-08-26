from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bug, BugSeverity, BugStatus, Subtask, generate_internal_key

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/bugs")
def list_bugs(request: Request, db: Session = Depends(get_db)):
    bugs = db.query(Bug).order_by(Bug.id.desc()).all()
    return templates.TemplateResponse(request, "bugs/list.html", {"bugs": bugs})


@router.get("/subtasks/{subtask_id}/bugs/new")
def new_bug_form(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "bugs/form.html",
        {
            "bug": None,
            "subtask": subtask,
            "severities": list(BugSeverity),
            "statuses": list(BugStatus),
            "error": None,
            "values": {"display_code": "", "title": "", "description": "", "severity": "MEDIUM", "status": "OPEN"},
        },
    )


@router.post("/subtasks/{subtask_id}/bugs")
def create_bug(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    if db.query(Bug).filter(Bug.subtask_id == subtask_id, Bug.display_code == display_code).first():
        return templates.TemplateResponse(
            request,
            "bugs/form.html",
            {
                "bug": None,
                "subtask": subtask,
                "severities": list(BugSeverity),
                "statuses": list(BugStatus),
                "error": f'Code "{display_code}" is already used in this subtask.',
                "values": {"display_code": display_code, "title": title, "description": description, "severity": "MEDIUM", "status": "OPEN"},
            },
            status_code=422,
        )
    bug = Bug(
        subtask_id=subtask_id, display_code=display_code, title=title, description=description,
        internal_key=generate_internal_key(),
    )
    db.add(bug)
    db.commit()
    db.refresh(bug)
    return RedirectResponse(url=f"/bugs/{bug.id}", status_code=303)


@router.get("/bugs/{bug_id}")
def bug_detail(request: Request, bug_id: int, db: Session = Depends(get_db)):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "bugs/detail.html",
        {"bug": bug, "severities": list(BugSeverity), "statuses": list(BugStatus)},
    )


@router.get("/bugs/{bug_id}/edit")
def edit_bug_form(request: Request, bug_id: int, db: Session = Depends(get_db)):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "bugs/form.html",
        {
            "bug": bug,
            "subtask": bug.subtask,
            "severities": list(BugSeverity),
            "statuses": list(BugStatus),
            "error": None,
            "values": {
                "display_code": bug.display_code, "title": bug.title, "description": bug.description,
                "severity": bug.severity.value, "status": bug.status.value,
            },
        },
    )


@router.post("/bugs/{bug_id}/edit")
def update_bug(
    request: Request,
    bug_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    severity: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = (
        db.query(Bug)
        .filter(Bug.subtask_id == bug.subtask_id, Bug.display_code == display_code, Bug.id != bug_id)
        .first()
    )
    try:
        severity_enum = BugSeverity(severity)
        status_enum = BugStatus(status)
    except ValueError:
        conflict = True  # reuse the same error branch below for any invalid enum value

    if conflict:
        return templates.TemplateResponse(
            request,
            "bugs/form.html",
            {
                "bug": bug,
                "subtask": bug.subtask,
                "severities": list(BugSeverity),
                "statuses": list(BugStatus),
                "error": f'Code "{display_code}" is already used in this subtask, or the severity/status was invalid.',
                "values": {"display_code": display_code, "title": title, "description": description, "severity": severity, "status": status},
            },
            status_code=422,
        )

    bug.display_code = display_code
    bug.title = title
    bug.description = description
    bug.severity = severity_enum
    bug.status = status_enum
    db.commit()
    return RedirectResponse(url=f"/bugs/{bug.id}", status_code=303)


@router.post("/bugs/{bug_id}/delete")
def delete_bug(request: Request, bug_id: int, db: Session = Depends(get_db)):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    subtask_id = bug.subtask_id
    db.delete(bug)
    db.commit()
    return RedirectResponse(url=f"/subtasks/{subtask_id}", status_code=303)
