from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SECTION_LABELS, StepSection, TestCase, TestCaseSection, TestCaseStatus, TestCaseStep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _render_execute(request: Request, testcase: TestCase, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "testcases/execute.html",
        {
            "testcase": testcase,
            "statuses": list(TestCaseStatus),
            "section_kinds": list(StepSection),
            "section_labels": SECTION_LABELS,
            "error": error,
        },
        status_code=status_code,
    )


def _next_position(testcase: TestCase) -> int:
    return max((section.position for section in testcase.sections), default=-1) + 1


@router.get("/testcases/{testcase_id}/execute")
def execute_page(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return _render_execute(request, testcase)


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

    # Assign all submitted values to testcase object (in memory only, not yet committed)
    # This ensures validation error re-renders show submitted values, not stale DB values
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

    try:
        status_enum = TestCaseStatus(status)
    except ValueError:
        # Re-render with error, showing submitted values via testcase object
        return _render_execute(request, testcase, error="Invalid status.", status_code=422)

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
        # Invalid section (forged POST). Show clear error; submitted step data cannot be preserved
        # in the template since there's no "new step" form slot until the step is created.
        return _render_execute(request, testcase, error=f'Invalid section "{section}". Valid sections: PRECONDITION, MAIN, POSTCONDITION.', status_code=422)

    # Addressed by kind rather than section id: appends to the LAST section of
    # that kind, creating one if the test case has none. Keeps a plain
    # "add a MAIN step" request working now that a kind can appear repeatedly.
    matching = [s for s in testcase.sections if s.kind == section_enum]
    if matching:
        target = matching[-1]
    else:
        target = TestCaseSection(testcase_id=testcase_id, kind=section_enum, position=_next_position(testcase))
        db.add(target)
        db.flush()

    _add_step(db, target, step_text, expected_result, actual_result)
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


def _add_step(db: Session, section: TestCaseSection, step_text: str, expected: str, actual: str) -> None:
    next_no = max((step.step_no for step in section.steps), default=0) + 1
    db.add(
        TestCaseStep(
            section_id=section.id, step_no=next_no,
            step_text=step_text, expected_result=expected, actual_result=actual,
        )
    )


@router.post("/testcases/{testcase_id}/sections")
def create_section(
    request: Request,
    testcase_id: int,
    kind: str = Form(...),
    db: Session = Depends(get_db),
):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    try:
        kind_enum = StepSection(kind)
    except ValueError:
        return _render_execute(request, testcase, error=f'Invalid section "{kind}".', status_code=422)

    db.add(TestCaseSection(testcase_id=testcase_id, kind=kind_enum, position=_next_position(testcase)))
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/sections/{section_id}/delete")
def delete_section(request: Request, testcase_id: int, section_id: int, db: Session = Depends(get_db)):
    from app import deletion

    section = db.get(TestCaseSection, section_id)
    if section is None or section.testcase_id != testcase_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    deletion.delete_section(db, section)
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/sections/{section_id}/steps")
def create_step_in_section(
    request: Request,
    testcase_id: int,
    section_id: int,
    step_text: str = Form(""),
    expected_result: str = Form(""),
    actual_result: str = Form(""),
    db: Session = Depends(get_db),
):
    section = db.get(TestCaseSection, section_id)
    if section is None or section.testcase_id != testcase_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    _add_step(db, section, step_text, expected_result, actual_result)
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
    from app import deletion

    step = db.get(TestCaseStep, step_id)
    if step is None or step.testcase_id != testcase_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    deletion.delete_step(db, step)
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)
