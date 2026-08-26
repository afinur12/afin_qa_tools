from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import deletion
from app.database import get_db
from app.templating import templates
from app.models import (
    DEFAULT_SECTION_KINDS, PrebuiltTestCase, Subtask, TestCase, TestCaseSection, TestCaseStep,
    generate_internal_key,
)

router = APIRouter()


@router.get("/subtasks/{subtask_id}/testcases/new")
def new_testcase_form(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "testcases/form.html",
        {
            "testcase": None, "subtask": subtask, "error": None,
            "values": {"display_code": "", "title": ""},
            "prebuilts": db.query(PrebuiltTestCase).order_by(PrebuiltTestCase.name).all(),
        },
    )


@router.post("/subtasks/{subtask_id}/testcases")
def create_testcase(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    prebuilt_id: str = Form(""),
    db: Session = Depends(get_db),
):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    if db.query(TestCase).filter(TestCase.subtask_id == subtask_id, TestCase.display_code == display_code).first():
        return templates.TemplateResponse(
            request,
            "testcases/form.html",
            {
                "testcase": None,
                "subtask": subtask,
                "error": f'Code "{display_code}" is already used in this subtask.',
                "values": {"display_code": display_code, "title": title},
                "prebuilts": db.query(PrebuiltTestCase).order_by(PrebuiltTestCase.name).all(),
            },
            status_code=422,
        )
    testcase = TestCase(subtask_id=subtask_id, display_code=display_code, title=title, internal_key=generate_internal_key())
    db.add(testcase)
    db.flush()

    prebuilt = db.get(PrebuiltTestCase, int(prebuilt_id)) if prebuilt_id.strip().isdigit() else None
    if prebuilt is not None:
        # Copy the template's structure and step text. Screenshots are never
        # part of a template, so the new case starts with none.
        testcase.test_type = prebuilt.test_type
        testcase.remark = prebuilt.remark
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
    else:
        # Blank case: one of each section, in the usual order, with no steps.
        for position, kind in enumerate(DEFAULT_SECTION_KINDS):
            db.add(TestCaseSection(testcase_id=testcase.id, kind=kind, position=position))
    db.commit()
    return RedirectResponse(url=f"/subtasks/{subtask_id}", status_code=303)


@router.get("/testcases/{testcase_id}/edit")
def edit_testcase_form(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "testcases/form.html",
        {
            "testcase": testcase,
            "subtask": testcase.subtask,
            "error": None,
            "values": {"display_code": testcase.display_code, "title": testcase.title},
        },
    )


@router.post("/testcases/{testcase_id}/edit")
def update_testcase(
    request: Request,
    testcase_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = (
        db.query(TestCase)
        .filter(TestCase.subtask_id == testcase.subtask_id, TestCase.display_code == display_code, TestCase.id != testcase_id)
        .first()
    )
    if conflict:
        return templates.TemplateResponse(
            request,
            "testcases/form.html",
            {
                "testcase": testcase,
                "subtask": testcase.subtask,
                "error": f'Code "{display_code}" is already used in this subtask.',
                "values": {"display_code": display_code, "title": title},
            },
            status_code=422,
        )
    testcase.display_code = display_code
    testcase.title = title
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase.id}/execute", status_code=303)


@router.post("/testcases/{testcase_id}/delete")
def delete_testcase(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    subtask_id = testcase.subtask_id
    # Cascades to its steps, their screenshots, and those files on disk, so
    # the case can be removed without clearing its steps out first.
    deletion.delete_testcase(db, testcase)
    db.commit()
    return RedirectResponse(url=f"/subtasks/{subtask_id}", status_code=303)
