from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Subtask, TestCase, generate_internal_key

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/subtasks/{subtask_id}/testcases/new")
def new_testcase_form(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "testcases/form.html",
        {"testcase": None, "subtask": subtask, "error": None, "values": {"display_code": "", "title": ""}},
    )


@router.post("/subtasks/{subtask_id}/testcases")
def create_testcase(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
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
            },
            status_code=422,
        )
    testcase = TestCase(subtask_id=subtask_id, display_code=display_code, title=title, internal_key=generate_internal_key())
    db.add(testcase)
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
    if len(testcase.steps) > 0:
        return templates.TemplateResponse(
            request,
            "testcases/form.html",
            {
                "testcase": testcase,
                "subtask": testcase.subtask,
                "error": f"Delete {len(testcase.steps)} step(s) first.",
                "values": {"display_code": testcase.display_code, "title": testcase.title},
            },
            status_code=422,
        )
    subtask_id = testcase.subtask_id
    db.delete(testcase)
    db.commit()
    return RedirectResponse(url=f"/subtasks/{subtask_id}", status_code=303)
