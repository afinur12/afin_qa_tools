from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import deletion
from app.database import get_db
from app.flash import redirect_with_flash
from app.templating import templates
from app.models import SECTION_LABELS, DEFAULT_SECTION_KINDS, LabelAttachType, PrebuiltTestCase, StepSection, TestCase, TestCaseSection, TestCaseStatus, TestCaseStep, TestPriority, TestType
from app.labels import get_labels, set_labels
from app.routers.stories import _parse_id, _user_dropdowns

router = APIRouter()


def _render_execute(request: Request, testcase: TestCase, db: Session, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "testcases/execute.html",
        {
            "testcase": testcase,
            "statuses": list(TestCaseStatus),
            "section_kinds": list(StepSection),
            "section_labels": SECTION_LABELS,
            "test_types": db.query(TestType).order_by(TestType.name).all(),
            "test_priorities": db.query(TestPriority).order_by(TestPriority.name).all(),
            "prebuilts": db.query(PrebuiltTestCase).order_by(PrebuiltTestCase.name).all(),
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.TESTCASE, testcase.id)],
            "testcase_labels": get_labels(db, LabelAttachType.TESTCASE, testcase.id),
            "error": error,
            **_user_dropdowns(db),
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
    return _render_execute(request, testcase, db)


@router.post("/testcases/{testcase_id}/section1")
def update_section1(
    request: Request,
    testcase_id: int,
    test_date: str = Form(""),
    test_priority_id: str = Form(""),
    test_type_id: str = Form(""),
    channel: str = Form(""),
    iteration: str = Form("1"),
    balance_before: str = Form("Rp. -"),
    balance_after: str = Form("Rp. -"),
    usage: str = Form("Rp. -"),
    remark: str = Form(""),
    data_test: str = Form(""),
    status: str = Form(...),
    assignee_id: str = Form(""),
    tester_id: str = Form(""),
    developer_id: str = Form(""),
    label_ids: list[int] = Form([]),
    msisdn: str = Form(""),
    planned_cost: str = Form(""),
    actual_cost: str = Form(""),
    db: Session = Depends(get_db),
):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    # Assign all submitted values to testcase object (in memory only, not yet committed)
    # This ensures validation error re-renders show submitted values, not stale DB values
    testcase.test_date = test_date
    testcase.test_priority_id = int(test_priority_id) if test_priority_id.strip().isdecimal() else None
    testcase.test_type_id = int(test_type_id) if test_type_id.strip().isdecimal() else None
    testcase.channel = channel
    # One "Iteration" field in the UI feeds both the docx header's free-text
    # iteration column and Jira Sync's numeric number_of_iteration — kept as
    # two DB columns since each downstream export expects its own shape.
    testcase.iteration = iteration or "1"
    testcase.number_of_iteration = int(iteration) if iteration.strip().isdecimal() else None
    testcase.balance_before = balance_before
    testcase.balance_after = balance_after
    testcase.usage = usage
    testcase.remark = remark
    testcase.data_test = data_test
    testcase.assignee_id = _parse_id(assignee_id)
    testcase.tester_id = _parse_id(tester_id)
    testcase.developer_id = _parse_id(developer_id)
    set_labels(db, LabelAttachType.TESTCASE, testcase.id, label_ids)
    testcase.msisdn = msisdn or None
    testcase.planned_cost = planned_cost or None
    testcase.actual_cost = actual_cost or None

    try:
        status_enum = TestCaseStatus(status)
    except ValueError:
        # Re-render with error, showing submitted values via testcase object
        return _render_execute(request, testcase, db, error="Invalid status.", status_code=422)

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
        return _render_execute(request, testcase, db, error=f'Invalid section "{section}". Valid sections: PRECONDITION, MAIN, POSTCONDITION.', status_code=422)

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
        return _render_execute(request, testcase, db, error=f'Invalid section "{kind}".', status_code=422)

    db.add(TestCaseSection(testcase_id=testcase_id, kind=kind_enum, position=_next_position(testcase)))
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/sections/reorder")
def reorder_sections(
    request: Request,
    testcase_id: int,
    order: str = Form(...),
    db: Session = Depends(get_db),
):
    """Persist a new section order.

    ``order`` is a comma-separated list of section ids in their new order.
    Ids that don't belong to this test case are rejected outright rather than
    partially applied.
    """
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    by_id = {section.id: section for section in testcase.sections}
    try:
        requested = [int(value) for value in order.split(",") if value.strip()]
    except ValueError:
        return _render_execute(request, testcase, db, error="Invalid section order.", status_code=422)

    if sorted(requested) != sorted(by_id):
        return _render_execute(request, testcase, db, error="Section order does not match this test case.", status_code=422)

    for position, section_id in enumerate(requested):
        by_id[section_id].position = position
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/sections/{section_id}/delete")
def delete_section(request: Request, testcase_id: int, section_id: int, db: Session = Depends(get_db)):
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


@router.post("/testcases/{testcase_id}/sections/{section_id}/steps/reorder")
def reorder_steps(
    request: Request,
    testcase_id: int,
    section_id: int,
    order: str = Form(...),
    db: Session = Depends(get_db),
):
    """Persist a new step order within a section.

    ``order`` is a comma-separated list of step ids in their new order.
    Ids that don't belong to this section are rejected outright rather than
    partially applied.
    """
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    section = db.get(TestCaseSection, section_id)
    if section is None or section.testcase_id != testcase_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    by_id = {step.id: step for step in section.steps}
    try:
        requested = [int(value) for value in order.split(",") if value.strip()]
    except ValueError:
        return _render_execute(request, testcase, db, error="Invalid step order.", status_code=422)

    if sorted(requested) != sorted(by_id):
        return _render_execute(request, testcase, db, error="Step order does not match this section.", status_code=422)

    for step_no, step_id in enumerate(requested, start=1):
        by_id[step_id].step_no = step_no
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
    deletion.delete_step(db, step)
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/copy-from-prebuilt")
def copy_from_prebuilt(request: Request, testcase_id: int, prebuilt_id: str = Form(""), db: Session = Depends(get_db)):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    for section in list(testcase.sections):
        deletion.delete_section(db, section)
    db.flush()

    prebuilt = db.get(PrebuiltTestCase, int(prebuilt_id)) if prebuilt_id.strip().isdigit() else None
    if prebuilt is not None:
        # Steps/text only — this replaces the test case's steps, it doesn't
        # touch other fields (test type, remark, etc). Screenshots are never
        # part of a template, so the case ends up with none either way.
        for source in prebuilt.sections:
            section = TestCaseSection(testcase_id=testcase.id, kind=source.kind, position=source.position)
            db.add(section)
            db.flush()
            for step in source.steps:
                db.add(
                    TestCaseStep(
                        section_id=section.id, step_no=step.step_no, step_text=step.step_text,
                        expected_result=step.expected_result, actual_result=step.actual_result,
                    )
                )
        db.commit()
        return redirect_with_flash(f"/testcases/{testcase_id}/execute", f"Steps copied from {prebuilt.name}.")

    for position, kind in enumerate(DEFAULT_SECTION_KINDS):
        db.add(TestCaseSection(testcase_id=testcase.id, kind=kind, position=position))
    db.commit()
    return redirect_with_flash(f"/testcases/{testcase_id}/execute", "Steps reset to blank.")
