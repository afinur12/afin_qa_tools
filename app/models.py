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
    testcases: Mapped[list["TestCase"]] = relationship(
        "TestCase", back_populates="subtask", order_by="TestCase.id"
    )
    bugs: Mapped[list["Bug"]] = relationship("Bug", back_populates="subtask", order_by="Bug.id")


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
