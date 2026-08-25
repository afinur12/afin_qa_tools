# QA Toolbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local-only QA Toolbox web app: FastAPI + SQLite + Jinja2, covering the Story→Phase→Subtask→TestCase/Bug hierarchy, testcase execution with pasted screenshots, and docx export matching `Template_Artifact_V1.docx`.

**Architecture:** A single FastAPI app (`app/main.py`) with one router module per resource, SQLAlchemy models in one file, Jinja2 server-rendered templates (no SPA framework), and a `docx/builder.py` module that fills a copy of the docx template per export. SQLite is the only datastore; screenshots and exported docx files live on disk under `app/uploads/`, with the on-disk path recorded in the DB. Every form follows one pattern: POST re-renders the same template with entered values + an inline error on validation failure (422), or redirects (303) to the created/updated resource on success.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite, Jinja2, python-docx, pytest + httpx (via FastAPI TestClient).

**Spec:** `docs/superpowers/specs/2026-08-26-qa-toolbox-design.md`

## Global Constraints

- No authentication — single local user, runs on `localhost` only.
- `display_code` uniqueness is per parent scope: Story globally, Subtask within its Phase, TestCase/Bug within their Subtask — enforced server-side at save time via SQLAlchemy `UniqueConstraint` + a pre-check that returns a friendly inline error instead of a raw `IntegrityError`.
- Delete is **blocked if children exist** for Story/Phase/Subtask/TestCase (no cascade). TestCaseStep delete is NOT blocked but cascades to delete its own Screenshots (DB rows + files) — this is a small, contained cascade, distinct from the hierarchy's no-cascade rule.
- STAGING_AFTER_ROLLBACK phase accepts only one Subtask, and it must be of type EXECUTION.
- Every entity has at most one Phase per type per Story (`unique(story_id, type)`).
- Validation failures re-render the submitting form with entered values preserved and an inline error, HTTP 422. No flash/session messaging.
- Screenshots: no format or size validation, stored as-is.
- Curl collections store and display only — no re-run/execution of stored requests.
- **Spec extension (flag to user):** the spec's `testcase` table only has `id, subtask_id, display_code, title, internal_key, status`, but the spec's own docx header-table mapping (Project, Scenario, Tester, Test Date, Environment, Test Priority, Test Type, Channel, Iteration, Balance Before/After, Usage, Final Status, Remark, Data Test) needs a place to live. This plan adds those as columns on `TestCase` (Task 3) — `Project`/`Scenario`/`Environment` are derived from Story/Subtask/Phase rather than duplicated, the rest are new columns filled in from the execution page. Task-2-item confirmed against the real template file at `D:\MAIN\PROGRAM\toolbox\data\templates\Template_Artifact_V1.docx` (see Task 15) — column layout for the step tables is `cell(row, 2)`/`cell(row, 5)` for values (6 grid columns with spacers), not the simplified 4-column description in the spec text.

---

## File Structure

```
qa-toolbox/
  app/
    main.py
    database.py
    models.py
    routers/
      dashboard.py
      stories.py
      subtasks.py
      testcases.py
      bugs.py
      curls.py
      docx_export.py
    templates/
      base.html
      not_found.html
      dashboard.html
      stories/{list,form,detail}.html
      subtasks/{form,detail}.html
      testcases/{form,execute}.html
      bugs/{form,detail}.html
      curls/_panel.html
    static/
      css/style.css
      js/paste_screenshot.js
    docx/
      Template_Artifact_V1.docx
      builder.py
    uploads/
      screenshots/
      exports/
  tests/
    conftest.py
    test_models.py
    test_stories.py
    test_subtasks.py
    test_testcases.py
    test_execution.py
    test_screenshots.py
    test_bugs.py
    test_curls.py
    test_dashboard.py
    test_docx_builder.py
    test_docx_export.py
    test_smoke.py
  requirements.txt
  README.md
```

---

### Task 1: Project scaffolding & test harness

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/database.py`
- Create: `app/main.py`
- Create: `app/static/css/style.css`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: `app.database.Base` (declarative base), `app.database.engine`, `app.database.get_db()` (FastAPI dependency, yields a `Session`), `app.main.app` (the FastAPI instance).

- [ ] **Step 1: Write requirements.txt**

```
fastapi
uvicorn
sqlalchemy>=2.0
jinja2
python-multipart
python-docx
pytest
httpx
```

- [ ] **Step 2: Create `app/database.py`**

```python
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("QA_TOOLBOX_DB_URL", "sqlite:///./qa_toolbox.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: Create `app/main.py` (no routers yet — added in later tasks)**

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="QA Toolbox")

Path("app/static").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
```

- [ ] **Step 4: Create `app/static/css/style.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", sans-serif; background: #f6f7f9; color: #1b2027; }
a { color: #3454d1; }
nav { background: #fff; border-bottom: 1px solid #e3e6ea; padding: 12px 24px; display: flex; gap: 20px; align-items: center; }
nav a { text-decoration: none; color: #626b79; font-weight: 500; font-size: 14px; }
nav a.brand { color: #1b2027; font-weight: 700; }
main { padding: 24px; max-width: 1100px; margin: 0 auto; }
.card { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #eceef1; font-size: 14px; }
th { font-size: 11px; text-transform: uppercase; color: #8a93a1; }
.btn { display: inline-block; background: #3454d1; color: #fff; border: none; padding: 8px 14px; border-radius: 6px; font-size: 13px; font-weight: 600; text-decoration: none; cursor: pointer; }
.btn.secondary { background: #fff; color: #1b2027; border: 1px solid #d5d9e0; }
.btn.danger { background: #fff; color: #b91c1c; border: 1px solid #d5d9e0; }
.error { background: #fee2e2; color: #b91c1c; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 13px; }
.field { margin-bottom: 14px; }
.field label { display: block; font-size: 12px; font-weight: 600; color: #626b79; margin-bottom: 4px; }
.field input, .field select, .field textarea { width: 100%; padding: 8px 10px; border: 1px solid #d5d9e0; border-radius: 6px; font-size: 14px; font-family: inherit; }
.badge { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 5px; display: inline-block; }
.mono { font-family: "SFMono-Regular", Consolas, monospace; }
.dropzone { border: 1.5px dashed #d5d9e0; border-radius: 8px; padding: 14px; background: #fbfbfc; }
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    os.remove(db_path)


@pytest.fixture()
def db_session(client):
    from app.database import SessionLocal as _Unused  # noqa: F401
    override = app.dependency_overrides[get_db]
    gen = override()
    session = next(gen)
    try:
        yield session
    finally:
        gen.close()
```

- [ ] **Step 6: Write the smoke test**

```python
def test_app_boots(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 7: Run it to verify it passes**

Run: `pytest tests/test_smoke.py -v`
Expected: PASS (confirms the app imports, mounts static files, and the test DB fixture works end to end).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt app/__init__.py app/database.py app/main.py app/static tests/__init__.py tests/conftest.py tests/test_smoke.py
git commit -m "chore: scaffold FastAPI app and pytest harness"
```

---

### Task 2: Core hierarchy models (Story, Phase, Subtask)

**Files:**
- Create: `app/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `app.database.Base` (Task 1).
- Produces: `generate_internal_key()`, `PhaseType`, `SubtaskType`, `Story`, `Phase`, `Subtask` — reused by every later task.

- [ ] **Step 1: Write failing tests for the hierarchy constraints**

```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Phase, PhaseType, Story, Subtask, SubtaskType


def test_story_display_code_globally_unique(db_session):
    db_session.add(Story(display_code="EX-1", title="A", internal_key="k1"))
    db_session.commit()
    db_session.add(Story(display_code="EX-1", title="B", internal_key="k2"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_phase_type_unique_per_story(db_session):
    story = Story(display_code="EX-2", title="A", internal_key="k3")
    db_session.add(story)
    db_session.commit()
    db_session.add(Phase(story_id=story.id, type=PhaseType.SIT))
    db_session.commit()
    db_session.add(Phase(story_id=story.id, type=PhaseType.SIT))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_subtask_display_code_unique_within_phase(db_session):
    story = Story(display_code="EX-3", title="A", internal_key="k4")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    db_session.add(
        Subtask(phase_id=phase.id, display_code="S-1", title="Planning",
                internal_key="k5", subtask_type=SubtaskType.TEST_PLANNING)
    )
    db_session.commit()
    db_session.add(
        Subtask(phase_id=phase.id, display_code="S-1", title="Execution",
                internal_key="k6", subtask_type=SubtaskType.EXECUTION)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: Write `app/models.py` (hierarchy portion)**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def generate_internal_key() -> str:
    return uuid.uuid4().hex


class PhaseType(str, enum.Enum):
    SIT = "SIT"
    STAGING = "STAGING"
    STAGING_AFTER_ROLLBACK = "STAGING_AFTER_ROLLBACK"
    SANITY = "SANITY"


class SubtaskType(str, enum.Enum):
    TEST_PLANNING = "TEST_PLANNING"
    TEST_DATA_PREP = "TEST_DATA_PREP"
    EXECUTION = "EXECUTION"
    TEST_AUTOMATION = "TEST_AUTOMATION"
    TEST_REPORTING = "TEST_REPORTING"


SUBTASK_TYPE_LABELS = {
    SubtaskType.TEST_PLANNING: "Test Planning",
    SubtaskType.TEST_DATA_PREP: "Test Data Preparation",
    SubtaskType.EXECUTION: "Execution",
    SubtaskType.TEST_AUTOMATION: "Test Automation",
    SubtaskType.TEST_REPORTING: "Test Reporting",
}


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    internal_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=generate_internal_key)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    phases: Mapped[list["Phase"]] = relationship("Phase", back_populates="story", order_by="Phase.id")


class Phase(Base):
    __tablename__ = "phases"
    __table_args__ = (UniqueConstraint("story_id", "type", name="uq_phase_story_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), nullable=False)
    type: Mapped[PhaseType] = mapped_column(SAEnum(PhaseType), nullable=False)

    story: Mapped["Story"] = relationship("Story", back_populates="phases")
    subtasks: Mapped[list["Subtask"]] = relationship("Subtask", back_populates="phase", order_by="Subtask.id")


class Subtask(Base):
    __tablename__ = "subtasks"
    __table_args__ = (UniqueConstraint("phase_id", "display_code", name="uq_subtask_phase_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("phases.id"), nullable=False)
    display_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    internal_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=generate_internal_key)
    subtask_type: Mapped[SubtaskType] = mapped_column(SAEnum(SubtaskType), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    phase: Mapped["Phase"] = relationship("Phase", back_populates="subtasks")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: add Story, Phase, Subtask models with scoped uniqueness"
```

---

### Task 3: Execution models (TestCase, TestCaseStep, Screenshot)

**Files:**
- Modify: `app/models.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Consumes: `Subtask` (Task 2).
- Produces: `TestCaseStatus`, `StepSection`, `TestCase`, `TestCaseStep`, `Screenshot`.

- [ ] **Step 1: Add failing tests**

```python
from app.models import StepSection, TestCase, TestCaseStatus, TestCaseStep


def test_testcase_display_code_unique_within_subtask(db_session):
    story = Story(display_code="EX-4", title="A", internal_key="k7")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k8", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    db_session.add(TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k9"))
    db_session.commit()
    db_session.add(TestCase(subtask_id=subtask.id, display_code="TC-1", title="B", internal_key="k10"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_testcase_defaults(db_session):
    story = Story(display_code="EX-5", title="A", internal_key="k11")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k12", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k13")
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    assert tc.status == TestCaseStatus.NOT_RUN
    assert tc.tester == "Andri Firman Nurvianto"
    assert tc.iteration == "1"
    assert tc.balance_before == "Rp. -"


def test_testcase_step_ordering(db_session):
    story = Story(display_code="EX-6", title="A", internal_key="k14")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k15", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k16")
    db_session.add(tc)
    db_session.commit()
    db_session.add(TestCaseStep(testcase_id=tc.id, section=StepSection.MAIN, step_no=2, step_text="second"))
    db_session.add(TestCaseStep(testcase_id=tc.id, section=StepSection.MAIN, step_no=1, step_text="first"))
    db_session.commit()
    db_session.refresh(tc)
    main_steps = [s for s in tc.steps if s.section == StepSection.MAIN]
    assert [s.step_no for s in main_steps] == [1, 2]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'TestCase'`

- [ ] **Step 3: Append to `app/models.py`**

```python
class TestCaseStatus(str, enum.Enum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    POSTPONED = "POSTPONED"


class StepSection(str, enum.Enum):
    PRECONDITION = "PRECONDITION"
    MAIN = "MAIN"
    POSTCONDITION = "POSTCONDITION"


class TestCase(Base):
    __tablename__ = "testcases"
    __table_args__ = (UniqueConstraint("subtask_id", "display_code", name="uq_testcase_subtask_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subtask_id: Mapped[int] = mapped_column(ForeignKey("subtasks.id"), nullable=False)
    display_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    internal_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=generate_internal_key)
    status: Mapped[TestCaseStatus] = mapped_column(SAEnum(TestCaseStatus), nullable=False, default=TestCaseStatus.NOT_RUN)

    # Section 1 / docx header fields not covered elsewhere in the hierarchy.
    tester: Mapped[str] = mapped_column(String(255), nullable=False, default="Andri Firman Nurvianto")
    test_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    test_priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    test_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    iteration: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    balance_before: Mapped[str] = mapped_column(String(64), nullable=False, default="Rp. -")
    balance_after: Mapped[str] = mapped_column(String(64), nullable=False, default="Rp. -")
    usage: Mapped[str] = mapped_column(String(64), nullable=False, default="Rp. -")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_test: Mapped[str | None] = mapped_column(Text, nullable=True)

    subtask: Mapped["Subtask"] = relationship("Subtask", back_populates="testcases")
    steps: Mapped[list["TestCaseStep"]] = relationship(
        "TestCaseStep", back_populates="testcase", order_by="TestCaseStep.step_no"
    )


class TestCaseStep(Base):
    __tablename__ = "testcase_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    testcase_id: Mapped[int] = mapped_column(ForeignKey("testcases.id"), nullable=False)
    section: Mapped[StepSection] = mapped_column(SAEnum(StepSection), nullable=False)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actual_result: Mapped[str] = mapped_column(Text, nullable=False, default="")

    testcase: Mapped["TestCase"] = relationship("TestCase", back_populates="steps")
    screenshots: Mapped[list["Screenshot"]] = relationship("Screenshot", back_populates="step")


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("testcase_steps.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    step: Mapped["TestCaseStep"] = relationship("TestCaseStep", back_populates="screenshots")
```

Add the reverse side on `Subtask` (edit the class from Task 2):

```python
    testcases: Mapped[list["TestCase"]] = relationship(
        "TestCase", back_populates="subtask", order_by="TestCase.id"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: add TestCase, TestCaseStep, Screenshot models"
```

---

### Task 4: Bug model

**Files:**
- Modify: `app/models.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Consumes: `Subtask` (Task 2).
- Produces: `BugSeverity`, `BugStatus`, `Bug`.

- [ ] **Step 1: Add failing test**

```python
from app.models import Bug, BugSeverity, BugStatus


def test_bug_display_code_unique_within_subtask(db_session):
    story = Story(display_code="EX-7", title="A", internal_key="k17")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k18", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    db_session.add(Bug(subtask_id=subtask.id, display_code="B-1", title="[ISSUE] a", internal_key="k19"))
    db_session.commit()
    db_session.add(Bug(subtask_id=subtask.id, display_code="B-1", title="[ISSUE] b", internal_key="k20"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_bug_defaults(db_session):
    story = Story(display_code="EX-8", title="A", internal_key="k21")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k22", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    bug = Bug(subtask_id=subtask.id, display_code="B-1", title="[ISSUE] a", internal_key="k23")
    db_session.add(bug)
    db_session.commit()
    db_session.refresh(bug)
    assert bug.severity == BugSeverity.MEDIUM
    assert bug.status == BugStatus.OPEN
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Bug'`

- [ ] **Step 3: Append to `app/models.py`**

```python
class BugSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BugStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Bug(Base):
    __tablename__ = "bugs"
    __table_args__ = (UniqueConstraint("subtask_id", "display_code", name="uq_bug_subtask_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subtask_id: Mapped[int] = mapped_column(ForeignKey("subtasks.id"), nullable=False)
    display_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    internal_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=generate_internal_key)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[BugSeverity] = mapped_column(SAEnum(BugSeverity), nullable=False, default=BugSeverity.MEDIUM)
    status: Mapped[BugStatus] = mapped_column(SAEnum(BugStatus), nullable=False, default=BugStatus.OPEN)

    subtask: Mapped["Subtask"] = relationship("Subtask", back_populates="bugs")
```

Add the reverse side on `Subtask`:

```python
    bugs: Mapped[list["Bug"]] = relationship("Bug", back_populates="subtask", order_by="Bug.id")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: add Bug model"
```

---

### Task 5: CurlCollection model

**Files:**
- Modify: `app/models.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Produces: `CurlAttachType`, `CurlCollection`.

- [ ] **Step 1: Add failing test**

```python
from app.models import CurlAttachType, CurlCollection


def test_curl_collection_create(db_session):
    story = Story(display_code="EX-9", title="A", internal_key="k24")
    db_session.add(story)
    db_session.commit()
    curl = CurlCollection(
        attach_type=CurlAttachType.STORY,
        attach_id=story.id,
        raw_text="curl https://api.example.com/health",
        method="GET",
        url="https://api.example.com/health",
        headers="{}",
        body="",
    )
    db_session.add(curl)
    db_session.commit()
    db_session.refresh(curl)
    assert curl.id is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'CurlCollection'`

- [ ] **Step 3: Append to `app/models.py`**

```python
class CurlAttachType(str, enum.Enum):
    STORY = "STORY"
    SUBTASK = "SUBTASK"


class CurlCollection(Base):
    __tablename__ = "curl_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attach_type: Mapped[CurlAttachType] = mapped_column(SAEnum(CurlAttachType), nullable=False)
    attach_id: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: add CurlCollection model"
```

---

### Task 6: Base template, nav, and app wiring

**Files:**
- Create: `app/templates/base.html`
- Create: `app/templates/not_found.html`
- Modify: `app/main.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: `base.html` (Jinja2 block `content`, expects `request` in context — required by `Jinja2Templates`), a working `templates.TemplateResponse` setup other tasks reuse.

- [ ] **Step 1: Write a failing test for a template-rendering route**

```python
def test_base_layout_renders_nav(client):
    response = client.get("/__template_check")
    assert response.status_code == 200
    assert "QA Toolbox" in response.text
    assert "Dashboard" in response.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Write `app/templates/base.html`**

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{% block title %}QA Toolbox{% endblock %}</title>
  <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
  <nav>
    <a class="brand" href="/">QA Toolbox</a>
    <a href="/">Dashboard</a>
    <a href="/stories">Stories</a>
    <a href="/bugs">Bugs</a>
  </nav>
  <main>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 4: Write `app/templates/not_found.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">Not found.</div>
{% endblock %}
```

- [ ] **Step 5: Wire `Jinja2Templates` into `app/main.py` and add a temporary check route**

Add near the top of `app/main.py`:

```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
```

Add at the bottom (this route is REMOVED in Step 7 below once Task 14's real `/` dashboard route exists):

```python
@app.get("/__template_check")
def _template_check(request: Request):
    return templates.TemplateResponse(request, "base.html", {})
```

Add `from fastapi import Request` to the imports.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/templates/base.html app/templates/not_found.html app/main.py tests/test_smoke.py
git commit -m "feat: add base layout and template wiring"
```

> Note for Task 10: delete the `_template_check` route and its test once a real route that renders `base.html` exists — leave a TODO comment is NOT acceptable per plan rules, so Task 10 explicitly includes removing it.

---

### Task 7: Story CRUD + Phase creation

**Files:**
- Create: `app/routers/__init__.py`
- Create: `app/routers/stories.py`
- Create: `app/templates/stories/list.html`
- Create: `app/templates/stories/form.html`
- Create: `app/templates/stories/detail.html`
- Modify: `app/main.py`
- Test: `tests/test_stories.py`

**Interfaces:**
- Consumes: `Story`, `Phase`, `PhaseType` (Task 2), `get_db` (Task 1).
- Produces: routes `GET/POST /stories`, `GET /stories/{id}`, `GET/POST /stories/{id}/edit`, `POST /stories/{id}/delete`, `POST /stories/{id}/phases`.

- [ ] **Step 1: Write failing tests**

```python
def test_create_story(client):
    response = client.post("/stories", data={"display_code": "EX-100", "title": "Payments"}, follow_redirects=False)
    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "EX-100" in detail.text
    assert "Payments" in detail.text


def test_create_story_duplicate_code_shows_inline_error(client):
    client.post("/stories", data={"display_code": "EX-101", "title": "A"})
    response = client.post("/stories", data={"display_code": "EX-101", "title": "B"})
    assert response.status_code == 422
    assert "already used" in response.text
    assert 'value="B"' in response.text


def test_delete_story_blocked_when_phase_exists(client):
    create = client.post("/stories", data={"display_code": "EX-102", "title": "A"}, follow_redirects=False)
    story_url = create.headers["location"]
    story_id = story_url.rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    response = client.post(f"/stories/{story_id}/delete")
    assert response.status_code == 422
    assert "Delete" in response.text


def test_create_phase_rejects_duplicate_type(client):
    create = client.post("/stories", data={"display_code": "EX-103", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    first = client.post(f"/stories/{story_id}/phases", data={"type": "SIT"}, follow_redirects=False)
    assert first.status_code == 303
    second = client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    assert second.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_stories.py -v`
Expected: FAIL (404 — no `/stories` route yet)

- [ ] **Step 3: Write `app/routers/stories.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Phase, PhaseType, Story, generate_internal_key

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/stories")
def list_stories(request: Request, db: Session = Depends(get_db)):
    stories = db.query(Story).order_by(Story.created_at.desc()).all()
    return templates.TemplateResponse(request, "stories/list.html", {"stories": stories})


@router.get("/stories/new")
def new_story_form(request: Request):
    return templates.TemplateResponse(
        request, "stories/form.html", {"story": None, "error": None, "values": {"display_code": "", "title": ""}}
    )


@router.post("/stories")
def create_story(
    request: Request,
    display_code: str = Form(...),
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    display_code = display_code.strip()
    title = title.strip()
    if db.query(Story).filter(Story.display_code == display_code).first():
        return templates.TemplateResponse(
            request,
            "stories/form.html",
            {
                "story": None,
                "error": f'Code "{display_code}" is already used by another story.',
                "values": {"display_code": display_code, "title": title},
            },
            status_code=422,
        )
    story = Story(display_code=display_code, title=title, internal_key=generate_internal_key())
    db.add(story)
    db.commit()
    db.refresh(story)
    return RedirectResponse(url=f"/stories/{story.id}", status_code=303)


def _available_phase_types(story: Story) -> list[PhaseType]:
    used = {p.type for p in story.phases}
    return [t for t in PhaseType if t not in used]


@router.get("/stories/{story_id}")
def story_detail(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "stories/detail.html",
        {"story": story, "available_phase_types": _available_phase_types(story), "error": None},
    )


@router.get("/stories/{story_id}/edit")
def edit_story_form(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "stories/form.html",
        {"story": story, "error": None, "values": {"display_code": story.display_code, "title": story.title}},
    )


@router.post("/stories/{story_id}/edit")
def update_story(
    request: Request,
    story_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = db.query(Story).filter(Story.display_code == display_code, Story.id != story_id).first()
    if conflict:
        return templates.TemplateResponse(
            request,
            "stories/form.html",
            {
                "story": story,
                "error": f'Code "{display_code}" is already used by another story.',
                "values": {"display_code": display_code, "title": title},
            },
            status_code=422,
        )
    story.display_code = display_code
    story.title = title
    db.commit()
    return RedirectResponse(url=f"/stories/{story.id}", status_code=303)


@router.post("/stories/{story_id}/delete")
def delete_story(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    if len(story.phases) > 0:
        return templates.TemplateResponse(
            request,
            "stories/detail.html",
            {
                "story": story,
                "available_phase_types": _available_phase_types(story),
                "error": f"Delete {len(story.phases)} phase(s) first.",
            },
            status_code=422,
        )
    db.delete(story)
    db.commit()
    return RedirectResponse(url="/stories", status_code=303)


@router.post("/stories/{story_id}/phases")
def create_phase(request: Request, story_id: int, type: str = Form(...), db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    available = _available_phase_types(story)
    try:
        phase_type = PhaseType(type)
    except ValueError:
        phase_type = None
    if phase_type is None or phase_type not in available:
        return templates.TemplateResponse(
            request,
            "stories/detail.html",
            {"story": story, "available_phase_types": available, "error": "Invalid or already-used phase type."},
            status_code=422,
        )
    db.add(Phase(story_id=story.id, type=phase_type))
    db.commit()
    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)
```

- [ ] **Step 4: Write `app/templates/stories/list.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
  <div style="display:flex;align-items:center;margin-bottom:14px;">
    <h2 style="margin:0;">Stories</h2>
    <div style="flex-grow:1;"></div>
    <a class="btn" href="/stories/new">+ New Story</a>
  </div>
  <table>
    <thead><tr><th>Code</th><th>Title</th><th>Created</th></tr></thead>
    <tbody>
      {% for s in stories %}
      <tr>
        <td class="mono"><a href="/stories/{{ s.id }}">{{ s.display_code }}</a></td>
        <td>{{ s.title }}</td>
        <td>{{ s.created_at.strftime("%Y-%m-%d") }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 5: Write `app/templates/stories/form.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width:480px;">
  <h2>{% if story %}Edit Story{% else %}New Story{% endif %}</h2>
  <form method="post" action="{% if story %}/stories/{{ story.id }}/edit{% else %}/stories{% endif %}">
    <div class="field">
      <label>Code</label>
      <input name="display_code" value="{{ values.display_code }}" required>
    </div>
    <div class="field">
      <label>Title</label>
      <input name="title" value="{{ values.title }}" required>
    </div>
    <button class="btn" type="submit">Save</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Write `app/templates/stories/detail.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
  <div style="display:flex;align-items:center;">
    <div>
      <span class="mono badge" style="background:#eef1fd;color:#3454d1;">{{ story.display_code }}</span>
      <span style="font-size:18px;font-weight:600;margin-left:8px;">{{ story.title }}</span>
    </div>
    <div style="flex-grow:1;"></div>
    <a class="btn secondary" href="/stories/{{ story.id }}/edit">Edit</a>
    <form method="post" action="/stories/{{ story.id }}/delete" style="display:inline;">
      <button class="btn danger" type="submit">Delete</button>
    </form>
  </div>
</div>

<div class="card">
  <h3>Phases</h3>
  {% for phase in story.phases %}
    <div style="margin-bottom:8px;"><a href="/stories/{{ story.id }}#{{ phase.type.value }}">{{ phase.type.value }}</a> ({{ phase.subtasks|length }} subtasks)</div>
  {% endfor %}
  {% if available_phase_types %}
  <form method="post" action="/stories/{{ story.id }}/phases" style="margin-top:10px;">
    <select name="type">
      {% for t in available_phase_types %}<option value="{{ t.value }}">{{ t.value }}</option>{% endfor %}
    </select>
    <button class="btn secondary" type="submit">+ Add Phase</button>
  </form>
  {% endif %}
</div>

{% for phase in story.phases %}
<div class="card" id="{{ phase.type.value }}">
  <h3>{{ phase.type.value }}</h3>
  {% for subtask in phase.subtasks %}
    <div style="padding:8px 0;border-bottom:1px solid #eceef1;">
      <span class="mono">{{ subtask.display_code }}</span>
      <a href="/subtasks/{{ subtask.id }}">{{ subtask.title }}</a>
      <span style="color:#8a93a1;">({{ subtask.subtask_type.value }})</span>
    </div>
  {% endfor %}
  <a class="btn secondary" style="margin-top:10px;" href="/phases/{{ phase.id }}/subtasks/new">+ New Subtask</a>
</div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 7: Wire the router into `app/main.py`**

```python
from app.routers import stories

app.include_router(stories.router)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_stories.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Commit**

```bash
git add app/routers/__init__.py app/routers/stories.py app/templates/stories app/main.py tests/test_stories.py
git commit -m "feat: add Story CRUD and Phase creation"
```

---

### Task 8: Subtask CRUD

**Files:**
- Create: `app/routers/subtasks.py`
- Create: `app/templates/subtasks/form.html`
- Create: `app/templates/subtasks/detail.html`
- Modify: `app/main.py`
- Test: `tests/test_subtasks.py`

**Interfaces:**
- Consumes: `Phase`, `PhaseType`, `Subtask`, `SubtaskType`, `SUBTASK_TYPE_LABELS` (Task 2).
- Produces: routes `GET/POST /phases/{phase_id}/subtasks`, `GET /subtasks/{id}`, `GET/POST /subtasks/{id}/edit`, `POST /subtasks/{id}/delete`. A helper `_allowed_subtask_types(phase)` other tasks don't need but tests exercise indirectly.

- [ ] **Step 1: Write failing tests**

```python
def _create_story_and_phase(client, code="EX-200", phase_type="SIT"):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    phase_resp = client.post(f"/stories/{story_id}/phases", data={"type": phase_type}, follow_redirects=False)
    story_page = client.get(f"/stories/{story_id}")
    import re
    phase_id = re.search(r'/phases/(\d+)/subtasks/new', story_page.text)
    return story_id, phase_id


def test_create_subtask(client):
    create = client.post("/stories", data={"display_code": "EX-201", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    from app.database import SessionLocal  # noqa
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    response = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "SIT Planning", "subtask_type": "TEST_PLANNING"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_staging_after_rollback_restricts_to_single_execution_subtask(client):
    create = client.post("/stories", data={"display_code": "EX-202", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "STAGING_AFTER_ROLLBACK"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    rejected = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Planning", "subtask_type": "TEST_PLANNING"},
    )
    assert rejected.status_code == 422

    accepted = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Execution", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    assert accepted.status_code == 303

    second = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-2", "title": "Execution 2", "subtask_type": "EXECUTION"},
    )
    assert second.status_code == 422


def test_delete_subtask_blocked_when_testcase_exists(client):
    create = client.post("/stories", data={"display_code": "EX-203", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    response = client.post(f"/subtasks/{subtask_id}/delete")
    assert response.status_code == 422
    assert "Delete" in response.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_subtasks.py -v`
Expected: FAIL (404 — no `/phases/{id}/subtasks` route yet; the last test also depends on Task 9's testcase route, so run only the first two for now — see Step 6)

- [ ] **Step 3: Write `app/routers/subtasks.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Phase, PhaseType, Subtask, SubtaskType, generate_internal_key

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _allowed_subtask_types(phase: Phase) -> list[SubtaskType]:
    if phase.type == PhaseType.STAGING_AFTER_ROLLBACK:
        if len(phase.subtasks) >= 1:
            return []
        return [SubtaskType.EXECUTION]
    return list(SubtaskType)


@router.get("/phases/{phase_id}/subtasks/new")
def new_subtask_form(request: Request, phase_id: int, db: Session = Depends(get_db)):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "subtasks/form.html",
        {
            "subtask": None,
            "phase": phase,
            "allowed_types": _allowed_subtask_types(phase),
            "error": None,
            "values": {"display_code": "", "title": "", "subtask_type": ""},
        },
    )


@router.post("/phases/{phase_id}/subtasks")
def create_subtask(
    request: Request,
    phase_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    subtask_type: str = Form(...),
    db: Session = Depends(get_db),
):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    allowed = _allowed_subtask_types(phase)
    try:
        st_type = SubtaskType(subtask_type)
    except ValueError:
        st_type = None

    error = None
    if st_type is None or st_type not in allowed:
        error = "That subtask type isn't allowed for this phase."
    elif db.query(Subtask).filter(Subtask.phase_id == phase.id, Subtask.display_code == display_code).first():
        error = f'Code "{display_code}" is already used in this phase.'

    if error:
        return templates.TemplateResponse(
            request,
            "subtasks/form.html",
            {
                "subtask": None,
                "phase": phase,
                "allowed_types": allowed,
                "error": error,
                "values": {"display_code": display_code, "title": title, "subtask_type": subtask_type},
            },
            status_code=422,
        )

    subtask = Subtask(
        phase_id=phase.id,
        display_code=display_code,
        title=title,
        internal_key=generate_internal_key(),
        subtask_type=st_type,
    )
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return RedirectResponse(url=f"/subtasks/{subtask.id}", status_code=303)


@router.get("/subtasks/{subtask_id}")
def subtask_detail(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(request, "subtasks/detail.html", {"subtask": subtask, "error": None})


@router.get("/subtasks/{subtask_id}/edit")
def edit_subtask_form(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "subtasks/form.html",
        {
            "subtask": subtask,
            "phase": subtask.phase,
            "allowed_types": _allowed_subtask_types(subtask.phase) or [subtask.subtask_type],
            "error": None,
            "values": {
                "display_code": subtask.display_code,
                "title": subtask.title,
                "subtask_type": subtask.subtask_type.value,
                "notes": subtask.notes or "",
            },
        },
    )


@router.post("/subtasks/{subtask_id}/edit")
def update_subtask(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = (
        db.query(Subtask)
        .filter(Subtask.phase_id == subtask.phase_id, Subtask.display_code == display_code, Subtask.id != subtask_id)
        .first()
    )
    if conflict:
        return templates.TemplateResponse(
            request,
            "subtasks/form.html",
            {
                "subtask": subtask,
                "phase": subtask.phase,
                "allowed_types": [subtask.subtask_type],
                "error": f'Code "{display_code}" is already used in this phase.',
                "values": {"display_code": display_code, "title": title, "subtask_type": subtask.subtask_type.value, "notes": notes},
            },
            status_code=422,
        )
    subtask.display_code = display_code
    subtask.title = title
    subtask.notes = notes
    db.commit()
    return RedirectResponse(url=f"/subtasks/{subtask.id}", status_code=303)


@router.post("/subtasks/{subtask_id}/delete")
def delete_subtask(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    children = len(subtask.testcases) + len(subtask.bugs)
    if children > 0:
        return templates.TemplateResponse(
            request,
            "subtasks/detail.html",
            {"subtask": subtask, "error": f"Delete {len(subtask.testcases)} testcase(s) and {len(subtask.bugs)} bug(s) first."},
            status_code=422,
        )
    story_id = subtask.phase.story_id
    db.delete(subtask)
    db.commit()
    return RedirectResponse(url=f"/stories/{story_id}", status_code=303)
```

- [ ] **Step 4: Write `app/templates/subtasks/form.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width:520px;">
  <h2>{% if subtask %}Edit Subtask{% else %}New Subtask ({{ phase.type.value }}){% endif %}</h2>
  <form method="post" action="{% if subtask %}/subtasks/{{ subtask.id }}/edit{% else %}/phases/{{ phase.id }}/subtasks{% endif %}">
    <div class="field">
      <label>Code</label>
      <input name="display_code" value="{{ values.display_code }}" required>
    </div>
    <div class="field">
      <label>Title</label>
      <input name="title" value="{{ values.title }}" required>
    </div>
    {% if not subtask %}
    <div class="field">
      <label>Type</label>
      <select name="subtask_type" required>
        <option value="">Select&hellip;</option>
        {% for t in allowed_types %}<option value="{{ t.value }}">{{ t.value }}</option>{% endfor %}
      </select>
    </div>
    {% else %}
    <div class="field">
      <label>Notes</label>
      <textarea name="notes" rows="4">{{ values.notes }}</textarea>
    </div>
    {% endif %}
    <button class="btn" type="submit">Save</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 5: Write `app/templates/subtasks/detail.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
  <div style="display:flex;align-items:center;">
    <div>
      <span class="mono badge" style="background:#eef1fd;color:#3454d1;">{{ subtask.display_code }}</span>
      <span style="font-size:18px;font-weight:600;margin-left:8px;">{{ subtask.title }}</span>
      <span style="color:#8a93a1;">({{ subtask.subtask_type.value }})</span>
    </div>
    <div style="flex-grow:1;"></div>
    <a class="btn secondary" href="/subtasks/{{ subtask.id }}/edit">Edit</a>
    <form method="post" action="/subtasks/{{ subtask.id }}/delete" style="display:inline;">
      <button class="btn danger" type="submit">Delete</button>
    </form>
  </div>
  {% if subtask.notes %}<p style="margin-top:12px;">{{ subtask.notes }}</p>{% endif %}
</div>

{% if subtask.subtask_type.value == "EXECUTION" %}
<div class="card">
  <div style="display:flex;align-items:center;"><h3 style="margin:0;">TestCases</h3><div style="flex-grow:1;"></div><a class="btn secondary" href="/subtasks/{{ subtask.id }}/testcases/new">+ New TestCase</a></div>
  <table>
    <thead><tr><th>Code</th><th>Title</th><th>Status</th></tr></thead>
    <tbody>
      {% for tc in subtask.testcases %}
      <tr><td class="mono"><a href="/testcases/{{ tc.id }}/execute">{{ tc.display_code }}</a></td><td>{{ tc.title }}</td><td>{{ tc.status.value }}</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
<div class="card">
  <div style="display:flex;align-items:center;"><h3 style="margin:0;">Bugs</h3><div style="flex-grow:1;"></div><a class="btn secondary" href="/subtasks/{{ subtask.id }}/bugs/new">+ New Bug</a></div>
  <table>
    <thead><tr><th>Code</th><th>Title</th><th>Severity</th><th>Status</th></tr></thead>
    <tbody>
      {% for bug in subtask.bugs %}
      <tr><td class="mono"><a href="/bugs/{{ bug.id }}">{{ bug.display_code }}</a></td><td>{{ bug.title }}</td><td>{{ bug.severity.value }}</td><td>{{ bug.status.value }}</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 6: Wire the router into `app/main.py`, then run the full suite**

```python
from app.routers import stories, subtasks

app.include_router(stories.router)
app.include_router(subtasks.router)
```

Run: `pytest tests/test_subtasks.py -v`
Expected: first two tests PASS; `test_delete_subtask_blocked_when_testcase_exists` still FAILs (needs Task 9's `/subtasks/{id}/testcases` route) — confirm the failure is a 404 on that route, not an error elsewhere, then proceed; Task 9 makes it pass.

- [ ] **Step 7: Commit**

```bash
git add app/routers/subtasks.py app/templates/subtasks app/main.py tests/test_subtasks.py
git commit -m "feat: add Subtask CRUD with STAGING_AFTER_ROLLBACK restriction"
```

---

### Task 9: TestCase CRUD (code, title, status)

**Files:**
- Create: `app/routers/testcases.py`
- Create: `app/templates/testcases/form.html`
- Modify: `app/main.py`
- Test: `tests/test_testcases.py`
- Modify: `tests/test_subtasks.py` (none needed — Task 8's blocked-delete test starts passing once this router exists)

**Interfaces:**
- Consumes: `TestCase`, `TestCaseStatus`, `Subtask` (Tasks 2-3).
- Produces: routes `GET/POST /subtasks/{subtask_id}/testcases`, `GET/POST /testcases/{id}/edit`, `POST /testcases/{id}/delete`.

- [ ] **Step 1: Write failing tests**

```python
def _create_execution_subtask(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    return sub_resp.headers["location"].rstrip("/").split("/")[-1]


def test_create_testcase_defaults_to_not_run(client):
    subtask_id = _create_execution_subtask(client, "EX-300")
    response = client.post(
        f"/subtasks/{subtask_id}/testcases",
        data={"display_code": "TC-1", "title": "Login works"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/subtasks/{subtask_id}")
    assert "TC-1" in detail.text
    assert "NOT_RUN" in detail.text


def test_create_testcase_duplicate_code_within_subtask(client):
    subtask_id = _create_execution_subtask(client, "EX-301")
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    response = client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "B"})
    assert response.status_code == 422
    assert "already used" in response.text


def test_edit_testcase_code_and_title(client):
    subtask_id = _create_execution_subtask(client, "EX-303")
    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Old title"}, follow_redirects=False
    )
    testcase_id = tc_resp.headers["location"].rstrip("/").split("/")[-1]
    response = client.post(
        f"/testcases/{testcase_id}/edit", data={"display_code": "TC-1", "title": "New title"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/testcases/{testcase_id}/execute"
    detail = client.get(f"/subtasks/{subtask_id}")
    assert "New title" in detail.text


def test_delete_testcase_blocked_when_steps_exist(client):
    subtask_id = _create_execution_subtask(client, "EX-302")
    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"}, follow_redirects=False
    )
    testcase_id = tc_resp.headers["location"].rstrip("/").split("/")[-1]
    from app.database import SessionLocal  # noqa: F401 (import kept minimal; step insert below uses raw SQL-free ORM via app import)
    import app.models as m
    from app.database import get_db
    from app.main import app as fastapi_app
    override = fastapi_app.dependency_overrides[get_db]
    gen = override()
    db = next(gen)
    db.add(m.TestCaseStep(testcase_id=int(testcase_id), section=m.StepSection.MAIN, step_no=1, step_text="x"))
    db.commit()
    gen.close()

    response = client.post(f"/testcases/{testcase_id}/delete")
    assert response.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_testcases.py -v`
Expected: FAIL (404 — no `/subtasks/{id}/testcases` route yet)

- [ ] **Step 3: Write `app/routers/testcases.py`**

```python
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
```

Note: `update_testcase` redirects to `/testcases/{id}/execute`, which does not exist until Task 10. This is fine — Task 9's tests don't exercise the edit-success path via a real browser follow, and Task 10 adds the route before any manual walkthrough. `create_testcase` and `delete_testcase` redirect to the already-existing subtask detail page, so they're fully testable now.

- [ ] **Step 4: Write `app/templates/testcases/form.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width:480px;">
  <h2>{% if testcase %}Edit TestCase{% else %}New TestCase{% endif %}</h2>
  <form method="post" action="{% if testcase %}/testcases/{{ testcase.id }}/edit{% else %}/subtasks/{{ subtask.id }}/testcases{% endif %}">
    <div class="field">
      <label>Code</label>
      <input name="display_code" value="{{ values.display_code }}" required>
    </div>
    <div class="field">
      <label>Title</label>
      <input name="title" value="{{ values.title }}" required>
    </div>
    <button class="btn" type="submit">Save</button>
  </form>
  {% if testcase %}
  <form method="post" action="/testcases/{{ testcase.id }}/delete" style="margin-top:10px;">
    <button class="btn danger" type="submit">Delete</button>
  </form>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Wire the router into `app/main.py` and run both test files**

```python
from app.routers import stories, subtasks, testcases

app.include_router(stories.router)
app.include_router(subtasks.router)
app.include_router(testcases.router)
```

Run: `pytest tests/test_testcases.py tests/test_subtasks.py -v`
Expected: PASS (all tests, including Task 8's previously-blocked `test_delete_subtask_blocked_when_testcase_exists`)

- [ ] **Step 6: Commit**

```bash
git add app/routers/testcases.py app/templates/testcases app/main.py tests/test_testcases.py
git commit -m "feat: add TestCase CRUD"
```

---

### Task 10: TestCaseStep CRUD + Execution page (Section 1-4)

**Files:**
- Create: `app/routers/execution.py`
- Create: `app/templates/testcases/execute.html`
- Modify: `app/main.py`
- Test: `tests/test_execution.py`

**Interfaces:**
- Consumes: `TestCase`, `TestCaseStep`, `StepSection`, `TestCaseStatus` (Tasks 2-3).
- Produces: routes `GET /testcases/{id}/execute`, `POST /testcases/{id}/section1`, `POST /testcases/{id}/steps`, `POST /testcases/{id}/steps/{step_id}/edit`, `POST /testcases/{id}/steps/{step_id}/delete`. Helper `_render_execute(...)` reused only within this router.

- [ ] **Step 1: Write failing tests**

```python
def _create_testcase(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]
    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login"}, follow_redirects=False
    )
    return tc_resp.headers["location"].rstrip("/").split("/")[-1]


def test_execute_page_renders(client):
    testcase_id = _create_testcase(client, "EX-400")
    response = client.get(f"/testcases/{testcase_id}/execute")
    assert response.status_code == 200
    assert "Pre Condition" in response.text
    assert "Main Test" in response.text
    assert "Post Condition" in response.text


def test_add_step_and_ordering(client):
    testcase_id = _create_testcase(client, "EX-401")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "first", "expected_result": "e1", "actual_result": "a1"})
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "second", "expected_result": "e2", "actual_result": "a2"})
    response = client.get(f"/testcases/{testcase_id}/execute")
    assert response.text.index("first") < response.text.index("second")


def test_update_section1_fields(client):
    testcase_id = _create_testcase(client, "EX-402")
    response = client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "tester": "Jane Doe", "test_date": "2026-08-26", "test_priority": "High",
            "test_type": "Functional", "channel": "Mobile App", "iteration": "1",
            "balance_before": "Rp. -", "balance_after": "Rp. -", "usage": "Rp. -",
            "remark": "", "data_test": "msisdn: 62812", "status": "PASS",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/testcases/{testcase_id}/execute")
    assert "Jane Doe" in page.text
    assert "PASS" in page.text


def test_edit_and_delete_step(client):
    testcase_id = _create_testcase(client, "EX-403")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "PRECONDITION", "step_text": "orig", "expected_result": "e", "actual_result": "a"})
    page = client.get(f"/testcases/{testcase_id}/execute")
    step_id = page.text.split('/steps/')[1].split('/edit')[0]

    edited = client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/edit",
        data={"step_text": "changed", "expected_result": "e2", "actual_result": "a2"},
        follow_redirects=False,
    )
    assert edited.status_code == 303
    page2 = client.get(f"/testcases/{testcase_id}/execute")
    assert "changed" in page2.text

    deleted = client.post(f"/testcases/{testcase_id}/steps/{step_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    page3 = client.get(f"/testcases/{testcase_id}/execute")
    assert "changed" not in page3.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_execution.py -v`
Expected: FAIL (404 — no `/testcases/{id}/execute` route yet)

- [ ] **Step 3: Write `app/routers/execution.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import StepSection, TestCase, TestCaseStatus, TestCaseStep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _steps_by_section(testcase: TestCase) -> dict[str, list[TestCaseStep]]:
    grouped: dict[str, list[TestCaseStep]] = {"PRECONDITION": [], "MAIN": [], "POSTCONDITION": []}
    for step in testcase.steps:
        grouped[step.section.value].append(step)
    for steps in grouped.values():
        steps.sort(key=lambda s: s.step_no)
    return grouped


def _render_execute(request: Request, testcase: TestCase, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "testcases/execute.html",
        {
            "testcase": testcase,
            "steps": _steps_by_section(testcase),
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
    try:
        status_enum = TestCaseStatus(status)
    except ValueError:
        return _render_execute(request, testcase, error="Invalid status.", status_code=422)

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
        return _render_execute(request, testcase, error="Invalid section.", status_code=422)
    existing = [s for s in testcase.steps if s.section == section_enum]
    next_no = max((s.step_no for s in existing), default=0) + 1
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
```

> Task 11 modifies `delete_step` to also remove each screenshot's file from disk before deleting its row.

- [ ] **Step 4: Write `app/templates/testcases/execute.html`**

```html
{% extends "base.html" %}
{% block content %}
<div style="font-size:12px;color:#8a93a1;margin-bottom:8px;">
  <a href="/subtasks/{{ testcase.subtask.id }}">{{ testcase.subtask.phase.story.display_code }} / {{ testcase.subtask.display_code }}</a> / {{ testcase.display_code }}
</div>

<div class="card">
  <div style="display:flex;align-items:center;">
    <h2 style="margin:0;">{{ testcase.display_code }} &mdash; {{ testcase.title }}</h2>
    <div style="flex-grow:1;"></div>
    <span class="badge" style="background:#eef1f4;">{{ testcase.status.value }}</span>
    <a class="btn secondary" style="margin-left:10px;" href="/testcases/{{ testcase.id }}/export-docx">Export .docx</a>
  </div>
</div>

<div class="card">
  <h3>1. Description</h3>
  <form method="post" action="/testcases/{{ testcase.id }}/section1">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px 24px;">
      <div class="field"><label>Project</label><input value="{{ testcase.subtask.phase.story.title }}" disabled></div>
      <div class="field"><label>Scenario</label><input value="{{ testcase.subtask.title }}" disabled></div>
      <div class="field"><label>Tester (PIC)</label><input name="tester" value="{{ testcase.tester }}"></div>
      <div class="field"><label>Test Date</label><input name="test_date" value="{{ testcase.test_date or '' }}" placeholder="YYYY-MM-DD"></div>
      <div class="field"><label>Environment</label><input value="{{ testcase.subtask.phase.type.value }}" disabled></div>
      <div class="field"><label>Test Priority</label><input name="test_priority" value="{{ testcase.test_priority or '' }}"></div>
      <div class="field"><label>Test Type</label><input name="test_type" value="{{ testcase.test_type or '' }}"></div>
      <div class="field"><label>Channel</label><input name="channel" value="{{ testcase.channel or '' }}"></div>
      <div class="field"><label>Iteration</label><input name="iteration" value="{{ testcase.iteration }}"></div>
      <div class="field"><label>Balance Before</label><input name="balance_before" value="{{ testcase.balance_before }}"></div>
      <div class="field"><label>Balance After</label><input name="balance_after" value="{{ testcase.balance_after }}"></div>
      <div class="field"><label>Usage</label><input name="usage" value="{{ testcase.usage }}"></div>
      <div class="field">
        <label>Final Status</label>
        <select name="status">
          {% for s in statuses %}<option value="{{ s.value }}" {% if s == testcase.status %}selected{% endif %}>{{ s.value }}</option>{% endfor %}
        </select>
      </div>
      <div class="field"><label>Remark</label><input name="remark" value="{{ testcase.remark or '' }}"></div>
    </div>
    <div class="field"><label>Data Test</label><textarea name="data_test" rows="3">{{ testcase.data_test or '' }}</textarea></div>
    <button class="btn" type="submit">Save Section 1</button>
  </form>
</div>

{% macro step_block(step) %}
<div class="card" style="margin-bottom:10px;">
  <form method="post" action="/testcases/{{ testcase.id }}/steps/{{ step.id }}/edit">
    <div style="display:flex;gap:10px;align-items:center;">
      <span class="mono badge" style="background:#eef1fd;color:#3454d1;">{{ step.step_no }}</span>
      <input name="step_text" value="{{ step.step_text }}" style="flex-grow:1;" placeholder="Step">
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px;">
      <div class="field"><label>Expected Result</label><textarea name="expected_result" rows="2">{{ step.expected_result }}</textarea></div>
      <div class="field"><label>Actual Result</label><textarea name="actual_result" rows="2">{{ step.actual_result }}</textarea></div>
    </div>
    <button class="btn secondary" type="submit">Save Step</button>
  </form>
  <form method="post" action="/testcases/{{ testcase.id }}/steps/{{ step.id }}/delete" style="margin-top:6px;">
    <button class="btn danger" type="submit">Delete Step</button>
  </form>
  <div class="dropzone" style="margin-top:10px;" data-step-id="{{ step.id }}">
    Screenshot paste zone (wired up in a later step of this build)
  </div>
</div>
{% endmacro %}

{% for section_key, section_label in [("PRECONDITION", "2. Pre Condition"), ("MAIN", "3. Main Test"), ("POSTCONDITION", "4. Post Condition")] %}
<div class="card">
  <h3>{{ section_label }}</h3>
  {% for step in steps[section_key] %}{{ step_block(step) }}{% endfor %}
  <form method="post" action="/testcases/{{ testcase.id }}/steps">
    <input type="hidden" name="section" value="{{ section_key }}">
    <button class="btn secondary" type="submit">+ Add Step</button>
  </form>
</div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 5: Wire the router into `app/main.py`, remove the Task 6 placeholder route**

```python
from app.routers import execution, stories, subtasks, testcases

app.include_router(stories.router)
app.include_router(subtasks.router)
app.include_router(testcases.router)
app.include_router(execution.router)
```

Delete the `_template_check` route and its import-only usage from `app/main.py`, and delete `test_base_layout_renders_nav` from `tests/test_smoke.py` (replace it with the equivalent assertion against `/stories`, which now renders the same `base.html`):

```python
def test_base_layout_renders_nav(client):
    response = client.get("/stories")
    assert response.status_code == 200
    assert "QA Toolbox" in response.text
    assert "Dashboard" in response.text
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_execution.py tests/test_smoke.py -v`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add app/routers/execution.py app/templates/testcases/execute.html app/main.py tests/test_execution.py tests/test_smoke.py
git commit -m "feat: add TestCaseStep CRUD and Section 1-4 execution page"
```

---

### Task 11: Screenshot paste-upload + delete

**Files:**
- Create: `app/routers/screenshots.py`
- Create: `app/static/js/paste_screenshot.js`
- Create: `.gitignore`
- Modify: `app/main.py`
- Modify: `app/routers/execution.py` (`delete_step`)
- Modify: `app/templates/testcases/execute.html` (dropzone → real upload UI)
- Test: `tests/test_screenshots.py`

**Interfaces:**
- Consumes: `Screenshot`, `TestCaseStep` (Task 3).
- Produces: routes `POST /testcases/{testcase_id}/steps/{step_id}/screenshot`, `POST /screenshots/{id}/delete`; `UPLOADS_DIR = Path("app/uploads")` constant reused by Task 15's docx builder.

- [ ] **Step 1: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
qa_toolbox.db
app/uploads/screenshots/**
app/uploads/exports/**
!app/uploads/screenshots/.gitkeep
!app/uploads/exports/.gitkeep
```

- [ ] **Step 2: Write failing test**

```python
import base64
from pathlib import Path

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _create_testcase(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]
    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login"}, follow_redirects=False
    )
    return tc_resp.headers["location"].rstrip("/").split("/")[-1]


def test_upload_and_delete_screenshot(client):
    testcase_id = _create_testcase(client, "EX-500")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "s", "expected_result": "e", "actual_result": "a"})
    page = client.get(f"/testcases/{testcase_id}/execute")
    step_id = page.text.split('/steps/')[1].split('/edit')[0]

    upload = client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/screenshot",
        files={"file": ("paste.png", PNG_BYTES, "image/png")},
        follow_redirects=False,
    )
    assert upload.status_code == 303
    page2 = client.get(f"/testcases/{testcase_id}/execute")
    assert "/uploads/screenshots/" in page2.text

    import re
    screenshot_id = re.search(r"/screenshots/(\d+)/delete", page2.text).group(1)
    disk_path = next(Path("app/uploads/screenshots").rglob("*.png"))
    assert disk_path.exists()

    delete = client.post(f"/screenshots/{screenshot_id}/delete", follow_redirects=False)
    assert delete.status_code == 303
    assert not disk_path.exists()


def test_deleting_step_removes_screenshot_file(client):
    testcase_id = _create_testcase(client, "EX-501")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "s", "expected_result": "e", "actual_result": "a"})
    page = client.get(f"/testcases/{testcase_id}/execute")
    step_id = page.text.split('/steps/')[1].split('/edit')[0]
    client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/screenshot",
        files={"file": ("paste.png", PNG_BYTES, "image/png")},
    )
    disk_path = next(Path("app/uploads/screenshots").rglob("*.png"))
    assert disk_path.exists()

    client.post(f"/testcases/{testcase_id}/steps/{step_id}/delete")
    assert not disk_path.exists()
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/test_screenshots.py -v`
Expected: FAIL (404 — no `/testcases/{id}/steps/{id}/screenshot` route yet)

- [ ] **Step 4: Write `app/routers/screenshots.py`**

```python
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Screenshot, TestCaseStep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

UPLOADS_DIR = Path("app/uploads")


@router.post("/testcases/{testcase_id}/steps/{step_id}/screenshot")
async def upload_screenshot(
    request: Request,
    testcase_id: int,
    step_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    step = db.get(TestCaseStep, step_id)
    if step is None or step.testcase_id != testcase_id:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    extension = mimetypes.guess_extension(file.content_type or "") or ".bin"
    filename = f"{uuid.uuid4().hex}{extension}"
    relative_path = f"screenshots/{testcase_id}/{step_id}/{filename}"
    disk_path = UPLOADS_DIR / relative_path
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(await file.read())

    db.add(Screenshot(step_id=step_id, file_path=relative_path))
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)


@router.post("/screenshots/{screenshot_id}/delete")
def delete_screenshot(request: Request, screenshot_id: int, db: Session = Depends(get_db)):
    screenshot = db.get(Screenshot, screenshot_id)
    if screenshot is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    testcase_id = screenshot.step.testcase_id
    disk_path = UPLOADS_DIR / screenshot.file_path
    if disk_path.exists():
        disk_path.unlink()
    db.delete(screenshot)
    db.commit()
    return RedirectResponse(url=f"/testcases/{testcase_id}/execute", status_code=303)
```

- [ ] **Step 5: Update `delete_step` in `app/routers/execution.py` to also remove files**

Replace:

```python
    for screenshot in step.screenshots:
        db.delete(screenshot)
    db.delete(step)
```

with:

```python
    from app.routers.screenshots import UPLOADS_DIR

    for screenshot in step.screenshots:
        disk_path = UPLOADS_DIR / screenshot.file_path
        if disk_path.exists():
            disk_path.unlink()
        db.delete(screenshot)
    db.delete(step)
```

- [ ] **Step 6: Write `app/static/js/paste_screenshot.js`**

```javascript
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".dropzone[data-step-id]").forEach((zone) => {
    zone.addEventListener("click", () => zone.focus());
    zone.addEventListener("paste", async (event) => {
      const items = event.clipboardData ? event.clipboardData.items : [];
      for (const item of items) {
        if (item.type.startsWith("image/")) {
          const file = item.getAsFile();
          const formData = new FormData();
          formData.append("file", file, "pasted." + item.type.split("/")[1]);
          const stepId = zone.dataset.stepId;
          const testcaseId = window.location.pathname.split("/")[2];
          await fetch(`/testcases/${testcaseId}/steps/${stepId}/screenshot`, { method: "POST", body: formData });
          window.location.reload();
        }
      }
    });
  });
});
```

- [ ] **Step 7: Update the dropzone in `app/templates/testcases/execute.html`**

Replace:

```html
  <div class="dropzone" style="margin-top:10px;" data-step-id="{{ step.id }}">
    Screenshot paste zone (wired up in a later step of this build)
  </div>
```

with:

```html
  <div class="dropzone" style="margin-top:10px;" tabindex="0" data-step-id="{{ step.id }}">
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
      {% for shot in step.screenshots %}
      <div>
        <img src="/uploads/{{ shot.file_path }}" style="width:80px;height:56px;object-fit:cover;border-radius:6px;border:1px solid #e3e6ea;">
        <form method="post" action="/screenshots/{{ shot.id }}/delete"><button class="btn danger" type="submit" style="font-size:11px;padding:2px 6px;">Remove</button></form>
      </div>
      {% endfor %}
    </div>
    <div style="font-size:12px;color:#8a93a1;">Click here, then press Ctrl+V to paste a screenshot.</div>
  </div>
```

Add before `{% endblock %}` at the end of the file:

```html
<script src="/static/js/paste_screenshot.js"></script>
```

- [ ] **Step 8: Wire uploads directory + static mount into `app/main.py`**

Add near the existing `app/static` mount:

```python
Path("app/uploads/screenshots").mkdir(parents=True, exist_ok=True)
Path("app/uploads/exports").mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="app/uploads"), name="uploads")

from app.routers import screenshots

app.include_router(screenshots.router)
```

Also create the placeholder files so git tracks the empty directories:

```bash
touch app/uploads/screenshots/.gitkeep app/uploads/exports/.gitkeep
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_screenshots.py tests/test_execution.py -v`
Expected: PASS (all tests)

- [ ] **Step 10: Commit**

```bash
git add app/routers/screenshots.py app/static/js/paste_screenshot.js app/main.py app/routers/execution.py app/templates/testcases/execute.html .gitignore app/uploads/screenshots/.gitkeep app/uploads/exports/.gitkeep tests/test_screenshots.py
git commit -m "feat: add clipboard-paste screenshot upload and delete"
```

---

### Task 12: Bug CRUD

**Files:**
- Create: `app/routers/bugs.py`
- Create: `app/templates/bugs/form.html`
- Create: `app/templates/bugs/detail.html`
- Create: `app/templates/bugs/list.html`
- Modify: `app/main.py`
- Test: `tests/test_bugs.py`

**Interfaces:**
- Consumes: `Bug`, `BugSeverity`, `BugStatus`, `Subtask` (Task 4).
- Produces: routes `GET /bugs`, `GET/POST /subtasks/{subtask_id}/bugs`, `GET /bugs/{id}`, `GET/POST /bugs/{id}/edit`, `POST /bugs/{id}/delete`.

- [ ] **Step 1: Write failing tests**

```python
def _create_execution_subtask(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    return sub_resp.headers["location"].rstrip("/").split("/")[-1]


def test_create_bug_with_defaults(client):
    subtask_id = _create_execution_subtask(client, "EX-600")
    response = client.post(
        f"/subtasks/{subtask_id}/bugs",
        data={"display_code": "B-1", "title": "[ISSUE] OTP fails", "description": "steps..."},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert "MEDIUM" in detail.text
    assert "OPEN" in detail.text


def test_create_bug_duplicate_code_within_subtask(client):
    subtask_id = _create_execution_subtask(client, "EX-601")
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"})
    response = client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] b"})
    assert response.status_code == 422


def test_edit_bug_severity_and_status(client):
    subtask_id = _create_execution_subtask(client, "EX-602")
    create = client.post(
        f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"}, follow_redirects=False
    )
    bug_id = create.headers["location"].rstrip("/").split("/")[-1]
    response = client.post(
        f"/bugs/{bug_id}/edit",
        data={
            "display_code": "B-1", "title": "[ISSUE] a", "description": "updated",
            "severity": "HIGH", "status": "IN_PROGRESS",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/bugs/{bug_id}")
    assert "HIGH" in detail.text
    assert "IN_PROGRESS" in detail.text


def test_bug_list_route(client):
    subtask_id = _create_execution_subtask(client, "EX-603")
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"})
    response = client.get("/bugs")
    assert response.status_code == 200
    assert "B-1" in response.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_bugs.py -v`
Expected: FAIL (404 — no `/subtasks/{id}/bugs` route yet)

- [ ] **Step 3: Write `app/routers/bugs.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bug, BugSeverity, BugStatus, Subtask, generate_internal_key

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/bugs")
def list_bugs(request: Request, db: Session = Depends(get_db)):
    bugs = db.query(Bug).order_by(Bug.id.desc()).all()
    return templates.TemplateResponse(request, "bugs/list.html", {"bugs": bugs})


@router.get("/subtasks/{subtask_id}/bugs/new")
def new_bug_form(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "bugs/form.html",
        {
            "bug": None,
            "subtask": subtask,
            "severities": list(BugSeverity),
            "statuses": list(BugStatus),
            "error": None,
            "values": {"display_code": "", "title": "", "description": "", "severity": "MEDIUM", "status": "OPEN"},
        },
    )


@router.post("/subtasks/{subtask_id}/bugs")
def create_bug(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    if db.query(Bug).filter(Bug.subtask_id == subtask_id, Bug.display_code == display_code).first():
        return templates.TemplateResponse(
            request,
            "bugs/form.html",
            {
                "bug": None,
                "subtask": subtask,
                "severities": list(BugSeverity),
                "statuses": list(BugStatus),
                "error": f'Code "{display_code}" is already used in this subtask.',
                "values": {"display_code": display_code, "title": title, "description": description, "severity": "MEDIUM", "status": "OPEN"},
            },
            status_code=422,
        )
    bug = Bug(
        subtask_id=subtask_id, display_code=display_code, title=title, description=description,
        internal_key=generate_internal_key(),
    )
    db.add(bug)
    db.commit()
    db.refresh(bug)
    return RedirectResponse(url=f"/bugs/{bug.id}", status_code=303)


@router.get("/bugs/{bug_id}")
def bug_detail(request: Request, bug_id: int, db: Session = Depends(get_db)):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(request, "bugs/detail.html", {"bug": bug})


@router.get("/bugs/{bug_id}/edit")
def edit_bug_form(request: Request, bug_id: int, db: Session = Depends(get_db)):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "bugs/form.html",
        {
            "bug": bug,
            "subtask": bug.subtask,
            "severities": list(BugSeverity),
            "statuses": list(BugStatus),
            "error": None,
            "values": {
                "display_code": bug.display_code, "title": bug.title, "description": bug.description,
                "severity": bug.severity.value, "status": bug.status.value,
            },
        },
    )


@router.post("/bugs/{bug_id}/edit")
def update_bug(
    request: Request,
    bug_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    severity: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = (
        db.query(Bug)
        .filter(Bug.subtask_id == bug.subtask_id, Bug.display_code == display_code, Bug.id != bug_id)
        .first()
    )
    try:
        severity_enum = BugSeverity(severity)
        status_enum = BugStatus(status)
    except ValueError:
        conflict = True  # reuse the same error branch below for any invalid enum value

    if conflict:
        return templates.TemplateResponse(
            request,
            "bugs/form.html",
            {
                "bug": bug,
                "subtask": bug.subtask,
                "severities": list(BugSeverity),
                "statuses": list(BugStatus),
                "error": f'Code "{display_code}" is already used in this subtask, or the severity/status was invalid.',
                "values": {"display_code": display_code, "title": title, "description": description, "severity": severity, "status": status},
            },
            status_code=422,
        )

    bug.display_code = display_code
    bug.title = title
    bug.description = description
    bug.severity = severity_enum
    bug.status = status_enum
    db.commit()
    return RedirectResponse(url=f"/bugs/{bug.id}", status_code=303)


@router.post("/bugs/{bug_id}/delete")
def delete_bug(request: Request, bug_id: int, db: Session = Depends(get_db)):
    bug = db.get(Bug, bug_id)
    if bug is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    subtask_id = bug.subtask_id
    db.delete(bug)
    db.commit()
    return RedirectResponse(url=f"/subtasks/{subtask_id}", status_code=303)
```

- [ ] **Step 4: Write `app/templates/bugs/form.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width:520px;">
  <h2>{% if bug %}Edit Bug{% else %}New Bug{% endif %}</h2>
  <form method="post" action="{% if bug %}/bugs/{{ bug.id }}/edit{% else %}/subtasks/{{ subtask.id }}/bugs{% endif %}">
    <div class="field"><label>Code</label><input name="display_code" value="{{ values.display_code }}" required></div>
    <div class="field"><label>Title</label><input name="title" value="{{ values.title }}" required></div>
    <div class="field"><label>Description</label><textarea name="description" rows="4">{{ values.description }}</textarea></div>
    {% if bug %}
    <div class="field">
      <label>Severity</label>
      <select name="severity">{% for s in severities %}<option value="{{ s.value }}" {% if s.value == values.severity %}selected{% endif %}>{{ s.value }}</option>{% endfor %}</select>
    </div>
    <div class="field">
      <label>Status</label>
      <select name="status">{% for s in statuses %}<option value="{{ s.value }}" {% if s.value == values.status %}selected{% endif %}>{{ s.value }}</option>{% endfor %}</select>
    </div>
    {% endif %}
    <button class="btn" type="submit">Save</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 5: Write `app/templates/bugs/detail.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
  <div style="display:flex;align-items:center;">
    <span class="mono badge" style="background:#eef1fd;color:#3454d1;">{{ bug.display_code }}</span>
    <span style="font-size:18px;font-weight:600;margin-left:8px;">{{ bug.title }}</span>
    <div style="flex-grow:1;"></div>
    <span class="badge" style="background:#fef3c7;">{{ bug.severity.value }}</span>
    <span class="badge" style="background:#eef1f4;margin-left:6px;">{{ bug.status.value }}</span>
    <a class="btn secondary" style="margin-left:10px;" href="/bugs/{{ bug.id }}/edit">Edit</a>
    <form method="post" action="/bugs/{{ bug.id }}/delete" style="display:inline;"><button class="btn danger" type="submit">Delete</button></form>
  </div>
  <p style="margin-top:12px;">{{ bug.description }}</p>
  <a href="/subtasks/{{ bug.subtask_id }}">Back to subtask</a>
</div>
{% endblock %}
```

- [ ] **Step 6: Write `app/templates/bugs/list.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
  <h2>Bugs</h2>
  <table>
    <thead><tr><th>Code</th><th>Title</th><th>Severity</th><th>Status</th></tr></thead>
    <tbody>
      {% for bug in bugs %}
      <tr><td class="mono"><a href="/bugs/{{ bug.id }}">{{ bug.display_code }}</a></td><td>{{ bug.title }}</td><td>{{ bug.severity.value }}</td><td>{{ bug.status.value }}</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 7: Wire the router into `app/main.py`**

```python
from app.routers import bugs

app.include_router(bugs.router)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_bugs.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Commit**

```bash
git add app/routers/bugs.py app/templates/bugs app/main.py tests/test_bugs.py
git commit -m "feat: add Bug CRUD with severity and status"
```

---

### Task 13: CurlCollection CRUD + parser

**Files:**
- Create: `app/routers/curls.py`
- Create: `app/templates/curls/_panel.html`
- Modify: `app/templates/stories/detail.html` (include the panel)
- Modify: `app/templates/subtasks/detail.html` (include the panel)
- Modify: `app/main.py`
- Test: `tests/test_curls.py`

**Interfaces:**
- Consumes: `CurlCollection`, `CurlAttachType` (Task 5).
- Produces: `parse_curl(raw_text: str) -> dict` (keys `method`, `url`, `headers` [JSON string], `body`), routes `POST /curls`, `POST /curls/{id}/delete`.

- [ ] **Step 1: Write failing tests**

```python
import json

from app.routers.curls import parse_curl


def test_parse_curl_get_with_headers():
    result = parse_curl('curl -H "Authorization: Bearer abc" https://api.example.com/health')
    assert result["method"] == "GET"
    assert result["url"] == "https://api.example.com/health"
    assert json.loads(result["headers"]) == {"Authorization": "Bearer abc"}


def test_parse_curl_post_with_data():
    result = parse_curl("curl -X POST https://api.example.com/users -d '{\"name\":\"a\"}'")
    assert result["method"] == "POST"
    assert result["url"] == "https://api.example.com/users"
    assert result["body"] == '{"name":"a"}'


def test_create_curl_attached_to_story(client):
    create = client.post("/stories", data={"display_code": "EX-700", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    response = client.post(
        "/curls",
        data={"attach_type": "STORY", "attach_id": story_id, "raw_text": "curl https://api.example.com/health"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    story_page = client.get(f"/stories/{story_id}")
    assert "api.example.com/health" in story_page.text


def test_delete_curl(client):
    create = client.post("/stories", data={"display_code": "EX-701", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post("/curls", data={"attach_type": "STORY", "attach_id": story_id, "raw_text": "curl https://api.example.com/health"})
    story_page = client.get(f"/stories/{story_id}")
    curl_id = story_page.text.split('/curls/')[1].split('/delete')[0]
    response = client.post(f"/curls/{curl_id}/delete", data={"attach_type": "STORY", "attach_id": story_id}, follow_redirects=False)
    assert response.status_code == 303
    story_page2 = client.get(f"/stories/{story_id}")
    assert "api.example.com/health" not in story_page2.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_curls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.curls'`

- [ ] **Step 3: Write `app/routers/curls.py`**

```python
import json
import shlex

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CurlAttachType, CurlCollection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def parse_curl(raw_text: str) -> dict:
    try:
        tokens = shlex.split(raw_text.strip())
    except ValueError:
        tokens = raw_text.strip().split()

    method = "GET"
    url = ""
    headers: dict[str, str] = {}
    body = ""

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "curl":
            i += 1
        elif tok in ("-X", "--request") and i + 1 < len(tokens):
            method = tokens[i + 1].upper()
            i += 2
        elif tok in ("-H", "--header") and i + 1 < len(tokens):
            key, _, value = tokens[i + 1].partition(":")
            if value:
                headers[key.strip()] = value.strip()
            i += 2
        elif tok in ("-d", "--data", "--data-raw", "--data-binary") and i + 1 < len(tokens):
            body = tokens[i + 1]
            if method == "GET":
                method = "POST"
            i += 2
        elif tok.startswith("-"):
            i += 1
        else:
            if not url:
                url = tok
            i += 1

    return {"method": method, "url": url, "headers": json.dumps(headers), "body": body}


def _redirect_target(attach_type: CurlAttachType, attach_id: int) -> str:
    if attach_type == CurlAttachType.STORY:
        return f"/stories/{attach_id}"
    return f"/subtasks/{attach_id}"


@router.post("/curls")
def create_curl(
    request: Request,
    attach_type: str = Form(...),
    attach_id: int = Form(...),
    raw_text: str = Form(...),
    db: Session = Depends(get_db),
):
    attach_type_enum = CurlAttachType(attach_type)
    parsed = parse_curl(raw_text)
    db.add(
        CurlCollection(
            attach_type=attach_type_enum, attach_id=attach_id, raw_text=raw_text,
            method=parsed["method"], url=parsed["url"], headers=parsed["headers"], body=parsed["body"],
        )
    )
    db.commit()
    return RedirectResponse(url=_redirect_target(attach_type_enum, attach_id), status_code=303)


@router.post("/curls/{curl_id}/delete")
def delete_curl(
    request: Request,
    curl_id: int,
    attach_type: str = Form(...),
    attach_id: int = Form(...),
    db: Session = Depends(get_db),
):
    curl = db.get(CurlCollection, curl_id)
    if curl is not None:
        db.delete(curl)
        db.commit()
    return RedirectResponse(url=_redirect_target(CurlAttachType(attach_type), attach_id), status_code=303)
```

- [ ] **Step 4: Write `app/templates/curls/_panel.html`** (included with `attach_type` and `attach_id` in context, plus `curls`, a pre-filtered list)

```html
<div class="card">
  <h3>Curl Collections</h3>
  {% for curl in curls %}
  <div style="border-bottom:1px solid #eceef1;padding:8px 0;">
    <div><span class="mono badge" style="background:#eef1f4;">{{ curl.method }}</span> <span class="mono">{{ curl.url }}</span></div>
    <form method="post" action="/curls/{{ curl.id }}/delete" style="margin-top:4px;">
      <input type="hidden" name="attach_type" value="{{ attach_type }}">
      <input type="hidden" name="attach_id" value="{{ attach_id }}">
      <button class="btn danger" type="submit" style="font-size:11px;padding:2px 8px;">Remove</button>
    </form>
  </div>
  {% endfor %}
  <form method="post" action="/curls" style="margin-top:10px;">
    <input type="hidden" name="attach_type" value="{{ attach_type }}">
    <input type="hidden" name="attach_id" value="{{ attach_id }}">
    <div class="field"><textarea name="raw_text" rows="3" placeholder="curl ..."></textarea></div>
    <button class="btn secondary" type="submit">+ Add Curl</button>
  </form>
</div>
```

- [ ] **Step 5: Include the panel from story and subtask detail routes/templates**

In `app/routers/stories.py`, `story_detail` now also queries curls and passes them:

```python
from app.models import CurlAttachType, CurlCollection

...

@router.get("/stories/{story_id}")
def story_detail(request: Request, story_id: int, db: Session = Depends(get_db)):
    story = db.get(Story, story_id)
    if story is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    curls = db.query(CurlCollection).filter(
        CurlCollection.attach_type == CurlAttachType.STORY, CurlCollection.attach_id == story_id
    ).all()
    return templates.TemplateResponse(
        request,
        "stories/detail.html",
        {"story": story, "available_phase_types": _available_phase_types(story), "error": None, "curls": curls},
    )
```

Apply the equivalent change to `subtask_detail` in `app/routers/subtasks.py` — add the same import line (`from app.models import CurlAttachType, CurlCollection`, merged into that file's existing `from app.models import ...` line) and replace the function with:

```python
@router.get("/subtasks/{subtask_id}")
def subtask_detail(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    curls = db.query(CurlCollection).filter(
        CurlCollection.attach_type == CurlAttachType.SUBTASK, CurlCollection.attach_id == subtask_id
    ).all()
    return templates.TemplateResponse(request, "subtasks/detail.html", {"subtask": subtask, "error": None, "curls": curls})
```

Add these three lines, in this order, immediately before `{% endblock %}` in `app/templates/stories/detail.html`:

```html
{% set attach_type = "STORY" %}
{% set attach_id = story.id %}
{% include "curls/_panel.html" with context %}
```

Add the same three lines to `app/templates/subtasks/detail.html` (immediately before its `{% endblock %}`), with `"SUBTASK"` in place of `"STORY"` and `subtask.id` in place of `story.id`:

```html
{% set attach_type = "SUBTASK" %}
{% set attach_id = subtask.id %}
{% include "curls/_panel.html" with context %}
```

- [ ] **Step 6: Wire the router into `app/main.py`**

```python
from app.routers import curls

app.include_router(curls.router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_curls.py -v`
Expected: PASS (4 tests)

- [ ] **Step 8: Commit**

```bash
git add app/routers/curls.py app/templates/curls app/templates/stories/detail.html app/templates/subtasks/detail.html app/routers/stories.py app/routers/subtasks.py app/main.py tests/test_curls.py
git commit -m "feat: add CurlCollection store-and-display"
```

---

### Task 14: Dashboard

**Files:**
- Create: `app/routers/dashboard.py`
- Create: `app/templates/dashboard.html`
- Modify: `app/main.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `Story`, `TestCase`, `TestCaseStatus`, `Bug`, `BugStatus`.
- Produces: route `GET /`.

- [ ] **Step 1: Write failing tests**

```python
def test_dashboard_shows_story_and_counts(client):
    create = client.post("/stories", data={"display_code": "EX-800", "title": "Payments"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"})

    response = client.get("/")
    assert response.status_code == 200
    assert "EX-800" in response.text
    assert "Payments" in response.text
    assert "NOT_RUN" in response.text
    assert "1" in response.text  # open bug count appears somewhere on the page
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL with 404 on `/`

- [ ] **Step 3: Write `app/routers/dashboard.py`**

```python
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
```

- [ ] **Step 4: Write `app/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
  <h2 style="margin:0 0 12px 0;">TestCase Status Breakdown</h2>
  <div style="display:flex;gap:18px;flex-wrap:wrap;">
    {% for status, count in status_counts.items() %}
    <div><span class="badge" style="background:#eef1f4;">{{ status.value }}</span> <span class="mono">{{ count }}</span></div>
    {% endfor %}
  </div>
</div>
<div class="card">
  <h2 style="margin:0;">Open Bugs</h2>
  <div class="mono" style="font-size:28px;font-weight:700;color:#b91c1c;">{{ open_bugs }}</div>
</div>
<div class="card">
  <div style="display:flex;align-items:center;margin-bottom:14px;">
    <h2 style="margin:0;">Stories</h2>
    <div style="flex-grow:1;"></div>
    <a class="btn" href="/stories/new">+ New Story</a>
  </div>
  <table>
    <thead><tr><th>Code</th><th>Title</th><th>Created</th></tr></thead>
    <tbody>
      {% for s in stories %}
      <tr>
        <td class="mono"><a href="/stories/{{ s.id }}">{{ s.display_code }}</a></td>
        <td>{{ s.title }}</td>
        <td>{{ s.created_at.strftime("%Y-%m-%d") }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 5: Wire the router into `app/main.py`**

```python
from app.routers import dashboard

app.include_router(dashboard.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/routers/dashboard.py app/templates/dashboard.html app/main.py tests/test_dashboard.py
git commit -m "feat: add dashboard with status breakdown and open bug count"
```

---

### Task 15: Docx builder (`app/docx/builder.py`)

**Files:**
- Create: `app/docx/__init__.py`
- Create: `app/docx/builder.py`
- Create: `app/docx/Template_Artifact_V1.docx` (binary copy)
- Test: `tests/test_docx_builder.py`

**Interfaces:**
- Consumes: `TestCase` ORM instance with `.subtask.phase.story` and `.steps[].screenshots` populated (Tasks 2-4), `UPLOADS_DIR` is NOT used here — the builder receives already-resolved absolute screenshot paths.
- Produces: `build_docx(testcase: TestCase, output_path: str) -> str`.

**Verified template structure** (confirmed by directly inspecting the real file with `python-docx` before writing this task — do not trust a simplified textual description over the actual file):
- `doc.tables[0]`: header, 15 rows × 4 cols. Value cell for field at row `r` is `table.cell(r, 3)`.
- `doc.tables[1]` / `[2]` / `[3]`: PRECONDITION / MAIN / POSTCONDITION, 4 rows × 6 cols each.
  - Row 0: `cell(0, 2)` = step number, `cell(0, 5)` = step text (cols 0/1/3/4 are fixed labels/spacers, not written to).
  - Row 1: `cell(1, 2)` = actual result, `cell(1, 5)` = expected result.
  - Row 2: gridSpan=6 merged cell, fixed "Screenshot" label — not written to.
  - Row 3: gridSpan=6 merged cell, empty — images are inserted here via `cell(3, 0)` (any column index reaches the same merged cell).
- Cloning: `copy.deepcopy(table._tbl)` + `table._tbl.addnext(new_tbl)`, wrapped back into a `docx.table.Table`. **Capture all three section base tables (`doc.tables[1]`, `[2]`, `[3]`) into variables BEFORE cloning anything** — cloning inserts new tables into the document body, which shifts every later `doc.tables[N]` index. Re-deriving a table by position after an earlier section has already cloned will silently grab the wrong table.

- [ ] **Step 1: Copy the real template into the repo**

```bash
mkdir -p app/docx
cp "D:\MAIN\PROGRAM\toolbox\data\templates\Template_Artifact_V1.docx" app/docx/Template_Artifact_V1.docx
touch app/docx/__init__.py
```

- [ ] **Step 2: Write failing tests**

```python
from docx import Document

from app.docx.builder import build_docx


class _Step:
    def __init__(self, step_no, section, text, expected, actual, screenshots=None):
        self.step_no = step_no
        self.section = section
        self.step_text = text
        self.expected_result = expected
        self.actual_result = actual
        self.screenshots = screenshots or []


class _Screenshot:
    def __init__(self, file_path):
        self.file_path = file_path


class _Enum:
    def __init__(self, value):
        self.value = value


class _Phase:
    def __init__(self, story, type_value):
        self.story = story
        self.type = _Enum(type_value)


class _Subtask:
    def __init__(self, story, title, phase_type):
        self.title = title
        self.phase = _Phase(story, phase_type)


class _Story:
    def __init__(self, title):
        self.title = title


class _TestCase:
    def __init__(self, subtask, steps):
        self.subtask = subtask
        self.steps = steps
        self.tester = "Andri Firman Nurvianto"
        self.test_date = "2026-08-26"
        self.test_priority = "High"
        self.test_type = "Functional"
        self.channel = "Mobile App"
        self.iteration = "1"
        self.balance_before = "Rp. -"
        self.balance_after = "Rp. -"
        self.usage = "Rp. -"
        self.remark = ""
        self.data_test = "msisdn: 62812"
        self.status = _Enum("PASS")


def _make_testcase(steps):
    from app.models import StepSection

    story = _Story("Payments")
    subtask = _Subtask(story, "SIT Login Flow", "SIT")
    return _TestCase(subtask, steps), StepSection


def test_build_docx_header_and_single_step(tmp_path):
    tc, StepSection = _make_testcase([])
    tc.steps = [
        _Step(1, StepSection.PRECONDITION, "pre text", "pre expected", "pre actual"),
        _Step(1, StepSection.MAIN, "main text", "main expected", "main actual"),
        _Step(1, StepSection.POSTCONDITION, "post text", "post expected", "post actual"),
    ]
    output_path = str(tmp_path / "out.docx")
    build_docx(tc, output_path)

    doc = Document(output_path)
    assert doc.tables[0].cell(0, 3).text == "Payments"
    assert doc.tables[0].cell(1, 3).text == "SIT Login Flow"
    assert doc.tables[0].cell(4, 3).text == "SIT"
    assert doc.tables[1].cell(0, 5).text == "pre text"
    assert doc.tables[2].cell(1, 2).text == "main actual"
    assert doc.tables[3].cell(1, 5).text == "post expected"


def test_build_docx_clones_tables_for_multiple_steps(tmp_path):
    tc, StepSection = _make_testcase([])
    tc.steps = [
        _Step(1, StepSection.MAIN, "step one", "e1", "a1"),
        _Step(2, StepSection.MAIN, "step two", "e2", "a2"),
        _Step(3, StepSection.MAIN, "step three", "e3", "a3"),
    ]
    output_path = str(tmp_path / "out2.docx")
    build_docx(tc, output_path)

    doc = Document(output_path)
    assert len(doc.tables) == 6  # header + 3 MAIN blocks + empty PRE + empty POST
    main_texts = [t.cell(0, 5).text for t in doc.tables if len(t.rows) == 4 and t.cell(0, 5).text.startswith("step")]
    assert main_texts == ["step one", "step two", "step three"]


def test_build_docx_inserts_screenshots(tmp_path):
    import base64

    png_path = tmp_path / "shot.png"
    png_path.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    tc, StepSection = _make_testcase([])
    tc.steps = [_Step(1, StepSection.MAIN, "step", "e", "a", screenshots=[_Screenshot(str(png_path))])]
    output_path = str(tmp_path / "out3.docx")
    build_docx(tc, output_path)

    doc = Document(output_path)
    assert len(doc.inline_shapes) == 1
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/test_docx_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.docx.builder'`

- [ ] **Step 4: Write `app/docx/builder.py`**

```python
import copy
from pathlib import Path

from docx import Document
from docx.shared import Inches
from docx.table import Table

TEMPLATE_PATH = Path(__file__).parent / "Template_Artifact_V1.docx"

HEADER_FIELD_ORDER = [
    "project", "scenario", "tester", "test_date", "environment",
    "test_priority", "test_type", "channel", "iteration",
    "balance_before", "balance_after", "usage", "final_status",
    "remark", "data_test",
]

SECTION_ORDER = ["PRECONDITION", "MAIN", "POSTCONDITION"]


def _clone_table(table: Table) -> Table:
    new_tbl = copy.deepcopy(table._tbl)
    table._tbl.addnext(new_tbl)
    return Table(new_tbl, table._parent)


def _fill_header(doc: Document, fields: dict) -> None:
    table = doc.tables[0]
    for row_index, field_name in enumerate(HEADER_FIELD_ORDER):
        table.cell(row_index, 3).text = str(fields.get(field_name, "") or "")


def _fill_step_block(table: Table, step_no, step_text: str, expected: str, actual: str) -> None:
    table.cell(0, 2).text = str(step_no)
    table.cell(0, 5).text = step_text or ""
    table.cell(1, 2).text = actual or ""
    table.cell(1, 5).text = expected or ""


def _insert_screenshots(table: Table, screenshot_paths: list[str]) -> None:
    cell = table.cell(3, 0)
    for i, path in enumerate(screenshot_paths):
        paragraph = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        paragraph.add_run().add_picture(path, width=Inches(2.5))


def build_docx(testcase, output_path: str) -> str:
    doc = Document(str(TEMPLATE_PATH))

    story = testcase.subtask.phase.story
    fields = {
        "project": story.title,
        "scenario": testcase.subtask.title,
        "tester": testcase.tester,
        "test_date": testcase.test_date,
        "environment": testcase.subtask.phase.type.value,
        "test_priority": testcase.test_priority,
        "test_type": testcase.test_type,
        "channel": testcase.channel,
        "iteration": testcase.iteration,
        "balance_before": testcase.balance_before,
        "balance_after": testcase.balance_after,
        "usage": testcase.usage,
        "final_status": testcase.status.value,
        "remark": testcase.remark,
        "data_test": testcase.data_test,
    }
    _fill_header(doc, fields)

    steps_by_section = {"PRECONDITION": [], "MAIN": [], "POSTCONDITION": []}
    for step in testcase.steps:
        steps_by_section[step.section.value].append(step)

    # Capture all base tables BEFORE any cloning — cloning shifts doc.tables indices.
    section_base_tables = {
        "PRECONDITION": doc.tables[1],
        "MAIN": doc.tables[2],
        "POSTCONDITION": doc.tables[3],
    }

    for section_name in SECTION_ORDER:
        steps = sorted(steps_by_section[section_name], key=lambda s: s.step_no)
        base_table = section_base_tables[section_name]
        if not steps:
            _fill_step_block(base_table, "", "", "", "")
            continue
        current_table = base_table
        for i, step in enumerate(steps):
            if i > 0:
                current_table = _clone_table(current_table)
            _fill_step_block(current_table, step.step_no, step.step_text, step.expected_result, step.actual_result)
            _insert_screenshots(current_table, [s.file_path for s in step.screenshots])

    doc.save(output_path)
    return output_path
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_docx_builder.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add app/docx/__init__.py app/docx/builder.py app/docx/Template_Artifact_V1.docx tests/test_docx_builder.py
git commit -m "feat: add docx builder filling header and cloning step-block tables"
```

---

### Task 16: Docx export route

**Files:**
- Create: `app/routers/docx_export.py`
- Modify: `app/templates/testcases/execute.html` (Export button already links to `/testcases/{id}/export-docx` from Task 10 — no change needed)
- Modify: `app/main.py`
- Test: `tests/test_docx_export.py`

**Interfaces:**
- Consumes: `build_docx` (Task 15), `TestCase` (Task 3), `UPLOADS_DIR` (Task 11).
- Produces: route `GET /testcases/{id}/export-docx`.

- [ ] **Step 1: Write failing test**

```python
def _create_testcase_with_step(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "Payments"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "SIT Login Flow", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]
    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login"}, follow_redirects=False
    )
    testcase_id = tc_resp.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "s", "expected_result": "e", "actual_result": "a"})
    return testcase_id


def test_export_docx_downloads_file(client):
    testcase_id = _create_testcase_with_step(client, "EX-900")
    response = client.get(f"/testcases/{testcase_id}/export-docx")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(response.content) > 0


def test_export_docx_404_for_missing_testcase(client):
    response = client.get("/testcases/999999/export-docx")
    assert response.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_docx_export.py -v`
Expected: FAIL with 404 (route doesn't exist) — note the second test would currently also return 404 but for the wrong reason (route missing, not "testcase missing"); it starts asserting the right thing once Step 3 lands.

- [ ] **Step 3: Write `app/routers/docx_export.py`**

```python
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.docx.builder import build_docx
from app.models import TestCase

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EXPORTS_DIR = Path("app/uploads/exports")


def _safe_filename_part(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "export"


@router.get("/testcases/{testcase_id}/export-docx")
def export_docx(request: Request, testcase_id: int, db: Session = Depends(get_db)):
    testcase = db.get(TestCase, testcase_id)
    if testcase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    project = _safe_filename_part(testcase.subtask.phase.story.title)
    scenario = _safe_filename_part(testcase.subtask.title)
    today = date.today().isoformat()
    filename = f"{project}_{scenario}_{today}.docx"

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORTS_DIR / filename
    build_docx(testcase, str(output_path))

    return FileResponse(
        path=str(output_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
```

For screenshots to resolve as real files, `build_docx` needs absolute-ish paths. Since `Screenshot.file_path` is stored relative to `app/uploads` (Task 11), the model's `.screenshots[].file_path` used directly by the builder would be wrong. Fix this by resolving the path before passing it down: `_insert_screenshots` in `app/docx/builder.py` (Task 15) already receives whatever string is on `screenshot.file_path`, so this route must not pass the ORM object's raw `.steps` — instead it constructs the disk path itself. Update `app/docx/builder.py`'s `build_docx` loop to prefix with `UPLOADS_DIR`:

Replace in `app/docx/builder.py`:

```python
            _insert_screenshots(current_table, [s.file_path for s in step.screenshots])
```

with:

```python
            from app.routers.screenshots import UPLOADS_DIR

            _insert_screenshots(current_table, [str(UPLOADS_DIR / s.file_path) for s in step.screenshots])
```

(`tests/test_docx_builder.py`'s fake `_Screenshot.file_path` already holds an absolute `tmp_path` string in `test_build_docx_inserts_screenshots` — `UPLOADS_DIR / "<absolute path>"` still resolves to that same absolute path, since `pathlib` treats joining an absolute path as replacing the base, so that test keeps passing unchanged.)

- [ ] **Step 4: Wire the router into `app/main.py`**

```python
from app.routers import docx_export

app.include_router(docx_export.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_docx_export.py tests/test_docx_builder.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/routers/docx_export.py app/docx/builder.py app/main.py tests/test_docx_export.py
git commit -m "feat: add docx export route with generated filename"
```

---

### Task 17: End-to-end smoke test, README, and final full-suite check

**Files:**
- Create: `tests/test_smoke.py` (extend — full workflow test)
- Create: `README.md`

**Interfaces:** None — this task only adds a whole-flow regression test and setup docs; it doesn't introduce new production code.

- [ ] **Step 1: Write the end-to-end workflow test**

```python
def test_full_workflow_story_to_docx_export(client):
    create = client.post("/stories", data={"display_code": "EX-999", "title": "E2E Story"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]

    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "SIT Login Flow", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]

    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login works"}, follow_redirects=False
    )
    testcase_id = tc_resp.headers["location"].rstrip("/").split("/")[-1]

    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "enter otp", "expected_result": "logged in", "actual_result": "logged in"})
    client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "tester": "Andri Firman Nurvianto", "test_date": "2026-08-26", "test_priority": "High",
            "test_type": "Functional", "channel": "Mobile App", "iteration": "1",
            "balance_before": "Rp. -", "balance_after": "Rp. -", "usage": "Rp. -",
            "remark": "", "data_test": "msisdn: 62812", "status": "PASS",
        },
    )
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] minor UI glitch"})

    export = client.get(f"/testcases/{testcase_id}/export-docx")
    assert export.status_code == 200

    dashboard = client.get("/")
    assert "EX-999" in dashboard.text
    assert "PASS" in dashboard.text
```

- [ ] **Step 2: Run it to verify it passes**

Run: `pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 3: Write `README.md`**

```markdown
# QA Toolbox

Local-only web app for API/microservices software testing work: documentation
generator (docx test report export) and test tracking. Runs entirely on
`localhost` — no auth, no external services, SQLite for storage.

## Setup

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

## Run

    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000

## Test

    pytest
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: PASS (every test across every task)

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke.py README.md
git commit -m "test: add end-to-end workflow smoke test and README"
```

---

## Self-Review Notes

- **Spec coverage:** every spec section has a task — data model (Tasks 2-5), CRUD scope + block-on-children delete (Tasks 7-9, 12), STAGING_AFTER_ROLLBACK restriction (Task 8), dashboard (Task 14), error handling pattern (used consistently in every router task), screenshots (Task 11), curl store-and-display (Task 13), docx mapping (Tasks 15-16), testing approach (every task is TDD; Task 17 adds the full-flow regression test), success criteria (exercised end-to-end by Task 17).
- **Schema gap fixed:** the spec's `testcase` table didn't have columns for the docx header fields (Tester, Test Date, Priority, Type, Channel, Iteration, Balances, Usage, Remark, Data Test) even though the spec's own docx mapping section requires them. Task 3 adds these directly to `TestCase`, deriving `Project`/`Scenario`/`Environment` from Story/Subtask/Phase instead of duplicating them — flagged in Global Constraints.
- **Docx column indices corrected against the real file:** the spec's textual table description ("row0: `No` | `1` | `Step` | `<step text>`") undercounts the actual 6-column grid (with spacer columns) in `Template_Artifact_V1.docx`. Task 15 documents and uses the verified indices (`cell(0,2)`/`cell(0,5)` etc.), confirmed by directly inspecting the file with `python-docx` and round-tripping a save/reload before this plan was written.
- **Clone-before-index bug avoided:** Task 15's builder captures `doc.tables[1]`, `[2]`, `[3]` into variables before any cloning happens, specifically to avoid a verified failure mode where cloning tables in an earlier section shifts the positional index of tables in later sections.
- **Type consistency check:** `TestCaseStatus`, `StepSection`, `BugSeverity`, `BugStatus`, `CurlAttachType` values are used identically (as `.value` strings in templates, as enum members in Python) across every task that touches them — verified by re-reading Tasks 2-16 for name drift; none found.
- **Placeholder scan:** no TBD/TODO markers; the one cross-task dependency notes (Task 9's `update_testcase` redirecting to a not-yet-built route, Task 6's temporary `_template_check` route) are explicitly called out with the task number that resolves them, not left open-ended.
