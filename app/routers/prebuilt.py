"""Prebuilt test cases: reusable skeletons of sections and steps."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import redirect_with_flash
from app.models import (
    DEFAULT_SECTION_KINDS,
    SECTION_LABELS,
    PrebuiltSection,
    PrebuiltStep,
    PrebuiltTestCase,
    Service,
    Simulate,
    StepSection,
    TestCase,
    TestType,
)
from app.templating import templates

router = APIRouter()


def _parse_id(raw: str) -> int | None:
    return int(raw) if raw.strip().isdigit() else None


def _render_detail(request: Request, prebuilt: PrebuiltTestCase, error: str | None = None, status_code: int = 200, db: Session | None = None):
    return templates.TemplateResponse(
        request,
        "prebuilt/detail.html",
        {
            "prebuilt": prebuilt,
            "section_kinds": list(StepSection),
            "section_labels": SECTION_LABELS,
            "services": db.query(Service).order_by(Service.name).all() if db else [],
            "simulates": db.query(Simulate).order_by(Simulate.name).all() if db else [],
            "test_types": db.query(TestType).order_by(TestType.name).all() if db else [],
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/prebuilt")
def list_prebuilt(request: Request, db: Session = Depends(get_db)):
    items = db.query(PrebuiltTestCase).order_by(PrebuiltTestCase.name).all()
    return templates.TemplateResponse(
        request,
        "prebuilt/list.html",
        {
            "prebuilts": items,
            "services": db.query(Service).order_by(Service.name).all(),
            "simulates": db.query(Simulate).order_by(Simulate.name).all(),
            "test_types": db.query(TestType).order_by(TestType.name).all(),
        },
    )


@router.post("/prebuilt")
def create_prebuilt(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    service_id: str = Form(""),
    test_type_id: str = Form(""),
    simulate_id: str = Form(""),
    remark: str = Form(""),
    db: Session = Depends(get_db),
):
    prebuilt = PrebuiltTestCase(
        name=name.strip(),
        description=description.strip() or None,
        service_id=_parse_id(service_id),
        test_type_id=_parse_id(test_type_id),
        simulate_id=_parse_id(simulate_id),
        remark=remark.strip() or None,
    )
    db.add(prebuilt)
    db.flush()
    for position, kind in enumerate(DEFAULT_SECTION_KINDS):
        db.add(PrebuiltSection(prebuilt_id=prebuilt.id, kind=kind, position=position))
    db.commit()
    db.refresh(prebuilt)
    return redirect_with_flash(f"/prebuilt/{prebuilt.id}", f'Template "{prebuilt.name}" created.')


@router.get("/prebuilt/{prebuilt_id}")
def prebuilt_detail(request: Request, prebuilt_id: int, db: Session = Depends(get_db)):
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return _render_detail(request, prebuilt, db=db)


@router.post("/prebuilt/{prebuilt_id}/edit")
def update_prebuilt(
    request: Request,
    prebuilt_id: int,
    name: str = Form(...),
    description: str = Form(""),
    service_id: str = Form(""),
    test_type_id: str = Form(""),
    simulate_id: str = Form(""),
    remark: str = Form(""),
    db: Session = Depends(get_db),
):
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    prebuilt.name = name.strip()
    prebuilt.description = description.strip() or None
    prebuilt.service_id = _parse_id(service_id)
    prebuilt.test_type_id = _parse_id(test_type_id)
    prebuilt.simulate_id = _parse_id(simulate_id)
    prebuilt.remark = remark.strip() or None
    db.commit()
    return redirect_with_flash(f"/prebuilt/{prebuilt_id}", f'Template "{prebuilt.name}" updated.')


@router.post("/prebuilt/{prebuilt_id}/delete")
def delete_prebuilt(request: Request, prebuilt_id: int, db: Session = Depends(get_db)):
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    name = prebuilt.name
    for section in list(prebuilt.sections):
        for step in list(section.steps):
            db.delete(step)
        db.delete(section)
    db.delete(prebuilt)
    db.commit()
    return redirect_with_flash("/prebuilt", f'Template "{name}" deleted.', category="danger")


@router.post("/prebuilt/{prebuilt_id}/sections/reorder")
def reorder_sections(
    request: Request,
    prebuilt_id: int,
    order: str = Form(...),
    db: Session = Depends(get_db),
):
    """Persist a new section order.

    ``order`` is a comma-separated list of section ids in their new order.
    Ids that don't belong to this template are rejected outright rather
    than partially applied.
    """
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    by_id = {section.id: section for section in prebuilt.sections}
    try:
        requested = [int(value) for value in order.split(",") if value.strip()]
    except ValueError:
        return _render_detail(request, prebuilt, error="Invalid section order.", status_code=422, db=db)

    if sorted(requested) != sorted(by_id):
        return _render_detail(request, prebuilt, error="Section order does not match this template.", status_code=422, db=db)

    for position, section_id in enumerate(requested):
        by_id[section_id].position = position
    db.commit()
    return RedirectResponse(url=f"/prebuilt/{prebuilt_id}", status_code=303)


@router.post("/prebuilt/{prebuilt_id}/sections")
def create_section(
    request: Request,
    prebuilt_id: int,
    kind: str = Form(...),
    db: Session = Depends(get_db),
):
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    try:
        kind_enum = StepSection(kind)
    except ValueError:
        return _render_detail(request, prebuilt, error=f'Invalid section "{kind}".', status_code=422, db=db)

    position = max((section.position for section in prebuilt.sections), default=-1) + 1
    db.add(PrebuiltSection(prebuilt_id=prebuilt_id, kind=kind_enum, position=position))
    db.commit()
    return RedirectResponse(url=f"/prebuilt/{prebuilt_id}", status_code=303)


@router.post("/prebuilt/{prebuilt_id}/sections/{section_id}/delete")
def delete_section(request: Request, prebuilt_id: int, section_id: int, db: Session = Depends(get_db)):
    section = db.get(PrebuiltSection, section_id)
    if section is None or section.prebuilt_id != prebuilt_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    for step in list(section.steps):
        db.delete(step)
    db.delete(section)
    db.commit()
    return RedirectResponse(url=f"/prebuilt/{prebuilt_id}", status_code=303)


@router.post("/prebuilt/{prebuilt_id}/sections/{section_id}/steps")
def create_step(
    request: Request,
    prebuilt_id: int,
    section_id: int,
    step_text: str = Form(""),
    expected_result: str = Form(""),
    actual_result: str = Form(""),
    db: Session = Depends(get_db),
):
    section = db.get(PrebuiltSection, section_id)
    if section is None or section.prebuilt_id != prebuilt_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    next_no = max((step.step_no for step in section.steps), default=0) + 1
    db.add(
        PrebuiltStep(
            section_id=section_id, step_no=next_no,
            step_text=step_text, expected_result=expected_result, actual_result=actual_result,
        )
    )
    db.commit()
    return RedirectResponse(url=f"/prebuilt/{prebuilt_id}", status_code=303)


@router.post("/prebuilt/{prebuilt_id}/sections/{section_id}/steps/reorder")
def reorder_steps(
    request: Request,
    prebuilt_id: int,
    section_id: int,
    order: str = Form(...),
    db: Session = Depends(get_db),
):
    """Persist a new step order within a section.

    ``order`` is a comma-separated list of step ids in their new order.
    Ids that don't belong to this section are rejected outright rather than
    partially applied.
    """
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    section = db.get(PrebuiltSection, section_id)
    if section is None or section.prebuilt_id != prebuilt_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    by_id = {step.id: step for step in section.steps}
    try:
        requested = [int(value) for value in order.split(",") if value.strip()]
    except ValueError:
        return _render_detail(request, prebuilt, error="Invalid step order.", status_code=422, db=db)

    if sorted(requested) != sorted(by_id):
        return _render_detail(request, prebuilt, error="Step order does not match this section.", status_code=422, db=db)

    for step_no, step_id in enumerate(requested, start=1):
        by_id[step_id].step_no = step_no
    db.commit()
    return RedirectResponse(url=f"/prebuilt/{prebuilt_id}", status_code=303)


@router.post("/prebuilt/{prebuilt_id}/steps/{step_id}/edit")
def update_step(
    request: Request,
    prebuilt_id: int,
    step_id: int,
    step_text: str = Form(""),
    expected_result: str = Form(""),
    actual_result: str = Form(""),
    db: Session = Depends(get_db),
):
    step = db.get(PrebuiltStep, step_id)
    if step is None or step.section.prebuilt_id != prebuilt_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    step.step_text = step_text
    step.expected_result = expected_result
    step.actual_result = actual_result
    db.commit()
    return RedirectResponse(url=f"/prebuilt/{prebuilt_id}", status_code=303)


@router.post("/prebuilt/{prebuilt_id}/steps/{step_id}/delete")
def delete_step(request: Request, prebuilt_id: int, step_id: int, db: Session = Depends(get_db)):
    step = db.get(PrebuiltStep, step_id)
    if step is None or step.section.prebuilt_id != prebuilt_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    db.delete(step)
    db.commit()
    return RedirectResponse(url=f"/prebuilt/{prebuilt_id}", status_code=303)


@router.post("/testcases/{testcase_id}/save-as-prebuilt")
def save_testcase_as_prebuilt(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    """Turn a real test case into a reusable template.

    Copies the section/step structure and text; screenshots and execution
    fields are deliberately left behind.
    """
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    prebuilt = PrebuiltTestCase(
        name=testcase.title or testcase.display_code,
        description=f"Saved from {testcase.display_code}",
        test_type=testcase.test_type,
        test_type_id=testcase.test_type_id,
        remark=testcase.remark,
    )
    db.add(prebuilt)
    db.flush()
    for section in testcase.sections:
        copy = PrebuiltSection(prebuilt_id=prebuilt.id, kind=section.kind, position=section.position)
        db.add(copy)
        db.flush()
        for step in section.steps:
            db.add(
                PrebuiltStep(
                    section_id=copy.id, step_no=step.step_no, step_text=step.step_text,
                    expected_result=step.expected_result, actual_result=step.actual_result,
                )
            )
    db.commit()
    db.refresh(prebuilt)
    return redirect_with_flash(f"/prebuilt/{prebuilt.id}", f'Saved "{prebuilt.name}" as a template.')
