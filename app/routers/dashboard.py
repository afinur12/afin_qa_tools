from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.models import Bug, BugStatus, Story, TaskStatus, TestCase, TestCaseStatus
from app.routers.stories import _user_dropdowns

router = APIRouter()


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

    total_tasks = len(stories)
    done_tasks = db.query(func.count(Story.id)).filter(Story.status == TaskStatus.DONE).scalar()
    task_done_pct = round(done_tasks / total_tasks * 100) if total_tasks else 0

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stories": stories, "status_counts": status_counts, "open_bugs": open_bugs,
            "total_tasks": total_tasks, "done_tasks": done_tasks, "task_done_pct": task_done_pct,
            **_user_dropdowns(db),
        },
    )
