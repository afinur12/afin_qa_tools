from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import StepSection, TestCase, TestCaseStatus, TestCaseStep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _steps_by_section(testcase: TestCase, db: Session | None = None) -> dict[str, list[TestCaseStep]]:
    grouped: dict[str, list[TestCaseStep]] = {"PRECONDITION": [], "MAIN": [], "POSTCONDITION": []}

    # Get steps, ordered by section then step_no, fallback to id if step_no values are unreliable
    if db is not None:
        steps_list = db.execute(
            select(TestCaseStep)
            .where(TestCaseStep.testcase_id == testcase.id)
            .order_by(TestCaseStep.section, TestCaseStep.step_no, TestCaseStep.id)
        ).scalars().all()
    else:
        steps_list = sorted(testcase.steps, key=lambda s: (s.section.value, s.step_no, s.id))

    for step in steps_list:
        grouped[step.section.value].append(step)

    return grouped


def _render_execute(request: Request, testcase: TestCase, error: str | None = None, status_code: int = 200, db: Session | None = None):
    return templates.TemplateResponse(
        request,
        "testcases/execute.html",
        {
            "testcase": testcase,
            "steps": _steps_by_section(testcase, db),
            "statuses": list(TestCaseStatus),
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/testcases/{testcase_id}/execute")
def execute_page(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    # Reload steps with explicit ordering
    db.refresh(testcase)
    return _render_execute(request, testcase, db=db)


@router.post("/testcases/{testcase_id}/section1")
def update_section1(
    request: Request,
    testcase_id: int,
    tester: str = Form(""),
    test_date: str = Form(""),
    test_priority: str = Form(""),
    test_type: str = Form(""),
    channel: str = Form(""),
    iteration: str = Form("1"),
    balance_before: str = Form("Rp. -"),
    balance_after: str = Form("Rp. -"),
    usage: str = Form("Rp. -"),
    remark: str = Form(""),
    data_test: str = Form(""),
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    try:
        status_enum = TestCaseStatus(status)
    except ValueError:
        return _render_execute(request, testcase, error="Invalid status.", status_code=422, db=db)

    testcase.tester = tester
    testcase.test_date = test_date
    testcase.test_priority = test_priority
    testcase.test_type = test_type
    testcase.channel = channel
    testcase.iteration = iteration
    testcase.balance_before = balance_before
    testcase.balance_after = balance_after
    testcase.usage = usage
    testcase.remark = remark
    testcase.data_test = data_test
    testcase.status = status_enum
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/steps")
def create_step(
    request: Request,
    testcase_id: int,
    section: str = Form(...),
    step_text: str = Form(""),
    expected_result: str = Form(""),
    actual_result: str = Form(""),
    db: Session = Depends(get_db),
):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    try:
        section_enum = StepSection(section)
    except ValueError:
        return _render_execute(request, testcase, error="Invalid section.", status_code=422, db=db)
    max_no = db.execute(
        select(func.max(TestCaseStep.step_no)).where(
            (TestCaseStep.testcase_id == testcase_id) &
            (TestCaseStep.section == section_enum)
        )
    ).scalar()
    next_no = (max_no or 0) + 1
    db.add(
        TestCaseStep(
            testcase_id=testcase_id, section=section_enum, step_no=next_no,
            step_text=step_text, expected_result=expected_result, actual_result=actual_result,
        )
    )
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/steps/{step_id}/edit")
def edit_step(
    request: Request,
    testcase_id: int,
    step_id: int,
    step_text: str = Form(""),
    expected_result: str = Form(""),
    actual_result: str = Form(""),
    db: Session = Depends(get_db),
):
    step = db.get(TestCaseStep, step_id)
    if step is None or step.testcase_id != testcase_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    step.step_text = step_text
    step.expected_result = expected_result
    step.actual_result = actual_result
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/steps/{step_id}/delete")
def delete_step(request: Request, testcase_id: int, step_id: int, db: Session = Depends(get_db)):
    step = db.get(TestCaseStep, step_id)
    if step is None or step.testcase_id != testcase_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    for screenshot in step.screenshots:
        db.delete(screenshot)
    db.delete(step)
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)
