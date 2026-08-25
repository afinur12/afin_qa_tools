from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bug, BugStatus, Story, TestCase, TestCaseStatus

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    stories = db.query(Story).order_by(Story.created_at.desc()).all()

    status_counts = {status: 0 for status in TestCaseStatus}
    for status, count in db.query(TestCase.status, func.count(TestCase.id)).group_by(TestCase.status).all():
        status_counts[status] = count

    open_bugs = (
        db.query(func.count(Bug.id))
        .filter(Bug.status.in_([BugStatus.OPEN, BugStatus.IN_PROGRESS]))
        .scalar()
    )

    return templates.TemplateResponse(
        request, "dashboard.html", {"stories": stories, "status_counts": status_counts, "open_bugs": open_bugs}
    )
