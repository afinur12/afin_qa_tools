"""Users: managed as Tester/Developer options for the assignee/tester/
developer fields on Story/Subtask/TestCase/Bug.

Not folded into settings.py's generic TABLES-dict router: User has a
second required column (type) that router's create/rename routes don't
collect, and its delete-block check spans 12 (model, column) pairs
across 4 different models rather than settings.py's one-model-per-slug
shape.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bug, Story, Subtask, TestCase, User, UserType
from app.templating import templates

router = APIRouter()

_REFS = [
    (Story, "assignee_id"), (Story, "tester_id"), (Story, "developer_id"),
    (Subtask, "assignee_id"), (Subtask, "tester_id"), (Subtask, "developer_id"),
    (TestCase, "assignee_id"), (TestCase, "tester_id"), (TestCase, "developer_id"),
    (Bug, "assignee_id"), (Bug, "tester_id"), (Bug, "developer_id"),
]


def _render(request: Request, db: Session, error: str | None = None, status_code: int = 200):
    users = db.query(User).order_by(User.name).all()
    return templates.TemplateResponse(
        request, "settings/users.html", {"slug": "users", "users": users, "error": error}, status_code=status_code,
    )


@router.get("/settings/users")
def list_users(request: Request, db: Session = Depends(get_db)):
    return _render(request, db)


@router.post("/settings/users")
def create_user(
    request: Request, name: str = Form(...), type: str = Form(...),
    jira_username: str = Form(""), db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return _render(request, db, error="Name is required.", status_code=422)
    try:
        type_enum = UserType(type)
    except ValueError:
        return _render(request, db, error="Invalid type.", status_code=422)
    if db.query(User).filter(User.name == name).first():
        return _render(request, db, error=f'"{name}" already exists.', status_code=422)
    db.add(User(name=name, type=type_enum, jira_username=jira_username.strip() or None))
    db.commit()
    return RedirectResponse(url="/settings/users", status_code=303)


@router.post("/settings/users/{user_id}/edit")
def rename_user(
    request: Request, user_id: int, name: str = Form(...),
    jira_username: str = Form(""), db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    name = name.strip()
    if not name:
        return _render(request, db, error="Name is required.", status_code=422)
    conflict = db.query(User).filter(User.name == name, User.id != user_id).first()
    if conflict:
        return _render(request, db, error=f'"{name}" already exists.', status_code=422)
    user.name = name
    user.jira_username = jira_username.strip() or None
    db.commit()
    return RedirectResponse(url="/settings/users", status_code=303)


@router.post("/settings/users/{user_id}/delete")
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    for model, fk_column in _REFS:
        count = db.query(func.count(model.id)).filter(getattr(model, fk_column) == user_id).scalar()
        if count:
            return _render(request, db, error=f'"{user.name}" is still used by {count} record(s).', status_code=422)
    db.delete(user)
    db.commit()
    return RedirectResponse(url="/settings/users", status_code=303)
