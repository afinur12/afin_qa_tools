from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import redirect_with_flash
from app.templating import templates
from app.models import Bug, BugSeverity, BugStatus, LabelAttachType, Subtask, generate_internal_key
from app.labels import clear_labels, get_labels, set_labels
from app.routers.stories import _parse_id, _user_dropdowns

router = APIRouter()


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
            "values": {
                "display_code": "", "title": "", "description": "", "severity": "MEDIUM", "status": "OPEN",
                "assignee_id": "", "tester_id": "", "developer_id": "",
            },
            "current_label_ids": [],
            **_user_dropdowns(db),
        },
    )


@router.post("/subtasks/{subtask_id}/bugs")
def create_bug(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
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
                "values": {
                    "display_code": display_code, "title": title, "description": description,
                    "severity": "MEDIUM", "status": "OPEN",
                    "assignee_id": assignee_id, "tester_id": tester_id, "developer_id": developer_id,
                },
                "current_label_ids": label_ids,
                **_user_dropdowns(db),
            },
            status_code=422,
        )
    bug = Bug(
        subtask_id=subtask_id, display_code=display_code, title=title, description=description,
        internal_key=generate_internal_key(),
        assignee_id=_parse_id(assignee_id), tester_id=_parse_id(tester_id), developer_id=_parse_id(developer_id),
    )
    db.add(bug)
    db.flush()
    set_labels(db, LabelAttachType.BUG, bug.id, label_ids)
    db.commit()
    db.refresh(bug)
    return redirect_with_flash(f"/bugs/{bug.id}", f"Bug {bug.display_code} logged.")


@router.get("/bugs/{bug_id}")
def bug_detail(request: Request, bug_id: int, db: Session = Depends(get_db)):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "bugs/detail.html",
        {
            "bug": bug, "severities": list(BugSeverity), "statuses": list(BugStatus),
            "bug_labels": get_labels(db, LabelAttachType.BUG, bug_id),
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.BUG, bug_id)],
            **_user_dropdowns(db),
        },
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
                "assignee_id": str(bug.assignee_id or ""), "tester_id": str(bug.tester_id or ""),
                "developer_id": str(bug.developer_id or ""),
            },
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.BUG, bug_id)],
            **_user_dropdowns(db),
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
    assignee_id: str = Form(""),
    tester_id: str = Form(""),
    developer_id: str = Form(""),
    label_ids: list[int] = Form([]),
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
                "values": {
                    "display_code": display_code, "title": title, "description": description,
                    "severity": severity, "status": status,
                    "assignee_id": assignee_id, "tester_id": tester_id, "developer_id": developer_id,
                },
                "current_label_ids": label_ids,
                **_user_dropdowns(db),
            },
            status_code=422,
        )

    bug.display_code = display_code
    bug.title = title
    bug.description = description
    bug.severity = severity_enum
    bug.status = status_enum
    bug.assignee_id = _parse_id(assignee_id)
    bug.tester_id = _parse_id(tester_id)
    bug.developer_id = _parse_id(developer_id)
    set_labels(db, LabelAttachType.BUG, bug.id, label_ids)
    db.commit()
    return redirect_with_flash(f"/bugs/{bug.id}", f"Bug {bug.display_code} updated.")


@router.post("/bugs/{bug_id}/delete")
def delete_bug(request: Request, bug_id: int, db: Session = Depends(get_db)):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    subtask_id = bug.subtask_id
    code = bug.display_code
    clear_labels(db, LabelAttachType.BUG, bug.id)
    db.delete(bug)
    db.commit()
    return redirect_with_flash(f"/subtasks/{subtask_id}", f"Bug {code} deleted.", category="danger")
