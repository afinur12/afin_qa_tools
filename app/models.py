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

    @property
    def allowed_subtask_types(self) -> list["SubtaskType"]:
        """Subtask types this phase will still accept.

        STAGING_AFTER_ROLLBACK skips the usual five-way breakdown: it takes a
        single EXECUTION subtask and nothing more. Lives on the model so the
        routers and the templates agree on one rule.
        """
        if self.type == PhaseType.STAGING_AFTER_ROLLBACK:
            return [] if self.subtasks else [SubtaskType.EXECUTION]
        return list(SubtaskType)


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
    # Stored with underscores so the value stays safe in CSS class names and
    # filenames; `label` is what the UI and the exported document show.
    TO_DO = "TO_DO"
    BACK_LOG = "BACK_LOG"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    POSTPONED = "POSTPONED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


# Statuses that mean the case has not been executed yet.
UNEXECUTED_STATUSES = {TestCaseStatus.TO_DO, TestCaseStatus.BACK_LOG}


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
    status: Mapped[TestCaseStatus] = mapped_column(SAEnum(TestCaseStatus), nullable=False, default=TestCaseStatus.TO_DO)

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
    sections: Mapped[list["TestCaseSection"]] = relationship(
        "TestCaseSection", back_populates="testcase", order_by="TestCaseSection.position"
    )

    @property
    def all_steps(self) -> list["TestCaseStep"]:
        """Every step across every section, in document order."""
        return [step for section in self.sections for step in section.steps]


SECTION_LABELS = {
    StepSection.PRECONDITION: "Pre Condition",
    StepSection.MAIN: "Main Test",
    StepSection.POSTCONDITION: "Post Condition",
}

# Sections a new test case starts with, in order.
DEFAULT_SECTION_KINDS = [StepSection.PRECONDITION, StepSection.MAIN, StepSection.POSTCONDITION]


class TestCaseSection(Base):
    """One PRE/MAIN/POST block on a test case.

    A test case holds an ordered list of these rather than one block per
    kind, so a run like PRE -> MAIN -> POST -> MAIN -> POST can be recorded
    as it actually happened. ``position`` is the order within the test case;
    ``kind`` may repeat.
    """

    __tablename__ = "testcase_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    testcase_id: Mapped[int] = mapped_column(ForeignKey("testcases.id"), nullable=False)
    kind: Mapped[StepSection] = mapped_column(SAEnum(StepSection), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    testcase: Mapped["TestCase"] = relationship("TestCase", back_populates="sections")
    steps: Mapped[list["TestCaseStep"]] = relationship(
        "TestCaseStep", back_populates="section", order_by="TestCaseStep.step_no"
    )

    @property
    def label(self) -> str:
        return SECTION_LABELS[self.kind]


class TestCaseStep(Base):
    __tablename__ = "testcase_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("testcase_sections.id"), nullable=False)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actual_result: Mapped[str] = mapped_column(Text, nullable=False, default="")

    section: Mapped["TestCaseSection"] = relationship("TestCaseSection", back_populates="steps")
    screenshots: Mapped[list["Screenshot"]] = relationship(
        "Screenshot", back_populates="step", order_by="Screenshot.id"
    )

    @property
    def testcase_id(self) -> int:
        return self.section.testcase_id


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


class PrebuiltTestCase(Base):
    """A reusable skeleton of sections and steps.

    Kept separate from TestCase rather than flagged on it: a real test case
    must belong to a subtask and carries execution data (status, tester,
    balances, screenshots), none of which a template has. Creating a case
    from one copies its sections and steps; screenshots are never part of a
    template.
    """

    __tablename__ = "prebuilt_testcases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    test_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    simulate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    sections: Mapped[list["PrebuiltSection"]] = relationship(
        "PrebuiltSection", back_populates="prebuilt", order_by="PrebuiltSection.position"
    )

    @property
    def step_count(self) -> int:
        return sum(len(section.steps) for section in self.sections)


class PrebuiltSection(Base):
    __tablename__ = "prebuilt_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prebuilt_id: Mapped[int] = mapped_column(ForeignKey("prebuilt_testcases.id"), nullable=False)
    kind: Mapped[StepSection] = mapped_column(SAEnum(StepSection), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    prebuilt: Mapped["PrebuiltTestCase"] = relationship("PrebuiltTestCase", back_populates="sections")
    steps: Mapped[list["PrebuiltStep"]] = relationship(
        "PrebuiltStep", back_populates="section", order_by="PrebuiltStep.step_no"
    )

    @property
    def label(self) -> str:
        return SECTION_LABELS[self.kind]


class PrebuiltStep(Base):
    __tablename__ = "prebuilt_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("prebuilt_sections.id"), nullable=False)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actual_result: Mapped[str] = mapped_column(Text, nullable=False, default="")

    section: Mapped["PrebuiltSection"] = relationship("PrebuiltSection", back_populates="steps")
