"""Prebuilt test cases: reusable skeletons of sections and steps."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DEFAULT_SECTION_KINDS,
    SECTION_LABELS,
    PrebuiltSection,
    PrebuiltStep,
    PrebuiltTestCase,
    StepSection,
    TestCase,
)
from app.templating import templates

router = APIRouter()


def _render_detail(request: Request, prebuilt: PrebuiltTestCase, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "prebuilt/detail.html",
        {
            "prebuilt": prebuilt,
            "section_kinds": list(StepSection),
            "section_labels": SECTION_LABELS,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/prebuilt")
def list_prebuilt(request: Request, db: Session = Depends(get_db)):
    items = db.query(PrebuiltTestCase).order_by(PrebuiltTestCase.name).all()
    return templates.TemplateResponse(request, "prebuilt/list.html", {"prebuilts": items})


@router.post("/prebuilt")
def create_prebuilt(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    test_type: str = Form(""),
    remark: str = Form(""),
    db: Session = Depends(get_db),
):
    prebuilt = PrebuiltTestCase(
        name=name.strip(),
        description=description.strip() or None,
        category=category.strip() or None,
        test_type=test_type.strip() or None,
        remark=remark.strip() or None,
    )
    db.add(prebuilt)
    db.flush()
    for position, kind in enumerate(DEFAULT_SECTION_KINDS):
        db.add(PrebuiltSection(prebuilt_id=prebuilt.id, kind=kind, position=position))
    db.commit()
    db.refresh(prebuilt)
    return RedirectResponse(url=f"/prebuilt/{prebuilt.id}", status_code=303)


@router.get("/prebuilt/{prebuilt_id}")
def prebuilt_detail(request: Request, prebuilt_id: int, db: Session = Depends(get_db)):
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return _render_detail(request, prebuilt)


@router.post("/prebuilt/{prebuilt_id}/edit")
def update_prebuilt(
    request: Request,
    prebuilt_id: int,
    name: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    test_type: str = Form(""),
    remark: str = Form(""),
    db: Session = Depends(get_db),
):
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    prebuilt.name = name.strip()
    prebuilt.description = description.strip() or None
    prebuilt.category = category.strip() or None
    prebuilt.test_type = test_type.strip() or None
    prebuilt.remark = remark.strip() or None
    db.commit()
    return RedirectResponse(url=f"/prebuilt/{prebuilt_id}", status_code=303)


@router.post("/prebuilt/{prebuilt_id}/delete")
def delete_prebuilt(request: Request, prebuilt_id: int, db: Session = Depends(get_db)):
    prebuilt = db.get(PrebuiltTestCase, prebuilt_id)
    if prebuilt is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    for section in list(prebuilt.sections):
        for step in list(section.steps):
            db.delete(step)
        db.delete(section)
    db.delete(prebuilt)
    db.commit()
    return RedirectResponse(url="/prebuilt", status_code=303)


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
        return _render_detail(request, prebuilt, error=f'Invalid section "{kind}".', status_code=422)

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
    return RedirectResponse(url=f"/prebuilt/{prebuilt.id}", status_code=303)
