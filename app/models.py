import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def generate_internal_key() -> str:
    return uuid.uuid4().hex


class PhaseType(str, enum.Enum):
    SIT = "SIT"
    SIT_AFTER_ROLLBACK = "SIT_AFTER_ROLLBACK"
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


class TaskStatus(str, enum.Enum):
    """Status for a Story ("task") or Subtask.

    Deliberately its own enum rather than reusing TestCaseStatus: the two
    are independent even though they share most of their values, so
    adding DONE here (a story/subtask concept — a test case is PASS/FAIL,
    never "done") never affects TestCase's own status options.
    """
    TO_DO = "TO_DO"
    IN_PROGRESS = "IN_PROGRESS"
    BACK_LOG = "BACK_LOG"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    POSTPONED = "POSTPONED"
    DONE = "DONE"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    internal_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, default=generate_internal_key)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), nullable=False, default=TaskStatus.TO_DO)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    phases: Mapped[list["Phase"]] = relationship("Phase", back_populates="story", order_by="Phase.id")
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_id])
    tester_user: Mapped["User | None"] = relationship("User", foreign_keys=[tester_id])
    developer: Mapped["User | None"] = relationship("User", foreign_keys=[developer_id])


class Phase(Base):
    __tablename__ = "phases"
    __table_args__ = (UniqueConstraint("story_id", "type", name="uq_phase_story_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), nullable=False)
    type: Mapped[PhaseType] = mapped_column(SAEnum(PhaseType), nullable=False)

    story: Mapped["Story"] = relationship("Story", back_populates="phases")
    subtasks: Mapped[list["Subtask"]] = relationship("Subtask", back_populates="phase", order_by="Subtask.position")

    @property
    def allowed_subtask_types(self) -> list["SubtaskType"]:
        """Subtask types this phase will still accept.

        The after-rollback phases (SIT and STAGING) skip the usual five-way
        breakdown: each takes a single EXECUTION subtask and nothing more.
        Lives on the model so the routers and the templates agree on one rule.
        """
        if self.type in (PhaseType.SIT_AFTER_ROLLBACK, PhaseType.STAGING_AFTER_ROLLBACK):
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
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), nullable=False, default=TaskStatus.TO_DO)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    phase: Mapped["Phase"] = relationship("Phase", back_populates="subtasks")
    testcases: Mapped[list["TestCase"]] = relationship(
        "TestCase", back_populates="subtask", order_by="TestCase.id"
    )
    bugs: Mapped[list["Bug"]] = relationship("Bug", back_populates="subtask", order_by="Bug.id")
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_id])
    tester_user: Mapped["User | None"] = relationship("User", foreign_keys=[tester_id])
    developer: Mapped["User | None"] = relationship("User", foreign_keys=[developer_id])


class TestCaseStatus(str, enum.Enum):
    # Stored with underscores so the value stays safe in CSS class names and
    # filenames; `label` is what the UI and the exported document show.
    TO_DO = "TO_DO"
    IN_PROGRESS = "IN_PROGRESS"
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


class TestCaseCategory(str, enum.Enum):
    """Matches Jira's category field values exactly (title-case, no
    underscores) — export/import need no translation table for this one,
    unlike status."""
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    REGRESSION = "Regression"


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
    test_priority_id: Mapped[int | None] = mapped_column(ForeignKey("test_priorities.id"), nullable=True)
    test_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    test_type_id: Mapped[int | None] = mapped_column(ForeignKey("test_types.id"), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    iteration: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    balance_before: Mapped[str] = mapped_column(String(64), nullable=False, default="Rp. -")
    balance_after: Mapped[str] = mapped_column(String(64), nullable=False, default="Rp. -")
    usage: Mapped[str] = mapped_column(String(64), nullable=False, default="Rp. -")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_test: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Set once the legacy `tester` text has been considered for backfilling
    # tester_id (whether or not a match was actually found) — see
    # migrate_testcase_tester_to_user in app/master_data.py. Without this,
    # a user deliberately clearing tester_id back to None would have it
    # silently restored from the untouched `tester` column on every restart.
    tester_migrated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Jira Sync fields (see app/jira_io.py) — all optional, populated either
    # by hand in Section 1 or by importing a Jira-sourced JSON.
    category: Mapped[TestCaseCategory | None] = mapped_column(SAEnum(TestCaseCategory), nullable=True)
    msisdn: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_cost: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual_cost: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number_of_iteration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Captured on import from execution.execution_id; echoed back unchanged
    # on the next export so CodeBuddy updates the same Zephyr execution.
    jira_execution_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    subtask: Mapped["Subtask"] = relationship("Subtask", back_populates="testcases")
    test_type_ref: Mapped["TestType | None"] = relationship("TestType")
    test_priority_ref: Mapped["TestPriority | None"] = relationship("TestPriority")
    sections: Mapped[list["TestCaseSection"]] = relationship(
        "TestCaseSection", back_populates="testcase", order_by="TestCaseSection.position"
    )
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_id])
    tester_user: Mapped["User | None"] = relationship("User", foreign_keys=[tester_id])
    developer: Mapped["User | None"] = relationship("User", foreign_keys=[developer_id])

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
    data_items: Mapped[list["TestCaseStepData"]] = relationship(
        "TestCaseStepData", back_populates="step", order_by="TestCaseStepData.order_no"
    )

    @property
    def testcase_id(self) -> int:
        return self.section.testcase_id


class TestCaseStepData(Base):
    """One titled, syntax-highlighted data item (a curl command, a SQL
    query, etc.) attached to a step. A step can hold any number of these —
    unlike step_text/expected_result, which are always exactly one value
    per step. `language` is detected client-side (same detectSnippetLanguage
    heuristic Notes already uses) and stored, not picked from a dropdown."""

    __tablename__ = "testcase_step_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("testcase_steps.id"), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="TEXT")

    step: Mapped["TestCaseStep"] = relationship("TestCaseStep", back_populates="data_items")


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

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


class BugStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


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
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    subtask: Mapped["Subtask"] = relationship("Subtask", back_populates="bugs")
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_id])
    tester_user: Mapped["User | None"] = relationship("User", foreign_keys=[tester_id])
    developer: Mapped["User | None"] = relationship("User", foreign_keys=[developer_id])


class UserType(str, enum.Enum):
    TESTER = "TESTER"
    DEVELOPER = "DEVELOPER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    type: Mapped[UserType] = mapped_column(SAEnum(UserType), nullable=False)
    jira_username: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class LabelAttachType(str, enum.Enum):
    STORY = "STORY"
    SUBTASK = "SUBTASK"
    TESTCASE = "TESTCASE"
    BUG = "BUG"


class LabelAssignment(Base):
    """Polymorphic label <-> entity join, one row per (label, entity)
    pair — mirrors Note's attach_type/attach_id pattern above rather
    than four separate join tables. A dedicated LabelAttachType rather
    than reusing NoteAttachType: Notes only ever attach to Story/Subtask
    today, and coupling Label's attach-target set to Note's would
    silently let Notes attach to TestCase/Bug too.
    """
    __tablename__ = "label_assignments"
    __table_args__ = (UniqueConstraint("label_id", "attach_type", "attach_id", name="uq_label_assignment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label_id: Mapped[int] = mapped_column(ForeignKey("labels.id"), nullable=False)
    attach_type: Mapped[LabelAttachType] = mapped_column(SAEnum(LabelAttachType), nullable=False)
    attach_id: Mapped[int] = mapped_column(Integer, nullable=False)


class NoteAttachType(str, enum.Enum):
    STORY = "STORY"
    SUBTASK = "SUBTASK"


class Note(Base):
    """A saved snippet (curl, SQL, JSON, or any other text) with an optional
    remark, attached to a story or subtask. Stored verbatim — nothing here
    is ever executed or parsed."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attach_type: Mapped[NoteAttachType] = mapped_column(SAEnum(NoteAttachType), nullable=False)
    attach_id: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="TEXT")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class Simulate(Base):
    __tablename__ = "simulates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class TestType(Base):
    __tablename__ = "test_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class TestPriority(Base):
    __tablename__ = "test_priorities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


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
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    simulate_id: Mapped[int | None] = mapped_column(ForeignKey("simulates.id"), nullable=True)
    test_type_id: Mapped[int | None] = mapped_column(ForeignKey("test_types.id"), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    sections: Mapped[list["PrebuiltSection"]] = relationship(
        "PrebuiltSection", back_populates="prebuilt", order_by="PrebuiltSection.position"
    )
    service: Mapped["Service | None"] = relationship("Service")
    simulate_ref: Mapped["Simulate | None"] = relationship("Simulate")
    test_type_ref: Mapped["TestType | None"] = relationship("TestType")

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


# ── API Client ────────────────────────────────────────────────────────────

class ApiCollection(Base):
    __tablename__ = "api_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    folders: Mapped[list["ApiFolder"]] = relationship(
        "ApiFolder", back_populates="collection", order_by="ApiFolder.id"
    )
    requests: Mapped[list["ApiRequest"]] = relationship(
        "ApiRequest", back_populates="collection", order_by="ApiRequest.position, ApiRequest.id"
    )
    variables: Mapped[list["ApiVariable"]] = relationship(
        "ApiVariable", back_populates="collection", order_by="ApiVariable.id"
    )


class ApiFolder(Base):
    """A folder inside a collection. ``parent_folder_id`` is self-referencing
    so folders can nest arbitrarily deep, same as a real Postman workspace."""

    __tablename__ = "api_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("api_collections.id"), nullable=False)
    parent_folder_id: Mapped[int | None] = mapped_column(ForeignKey("api_folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    collection: Mapped["ApiCollection"] = relationship("ApiCollection", back_populates="folders")
    parent: Mapped["ApiFolder | None"] = relationship("ApiFolder", remote_side=[id], back_populates="children")
    children: Mapped[list["ApiFolder"]] = relationship(
        "ApiFolder", back_populates="parent", order_by="ApiFolder.id"
    )
    requests: Mapped[list["ApiRequest"]] = relationship(
        "ApiRequest", back_populates="folder", order_by="ApiRequest.position, ApiRequest.id"
    )


class ApiRequest(Base):
    """A saved request. Always belongs to a collection; ``folder_id`` is
    null when it sits at the collection's root rather than in a folder.

    Params has no field of its own — the query string lives directly in
    ``url``, same as pasting a full URL anywhere else.
    """

    __tablename__ = "api_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("api_collections.id"), nullable=False)
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("api_folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="GET")
    url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # See app/api_body.py — "" means saved before body modes existed.
    body_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    collection: Mapped["ApiCollection"] = relationship("ApiCollection", back_populates="requests")
    folder: Mapped["ApiFolder | None"] = relationship("ApiFolder", back_populates="requests")


class ApiVariableScope(str, enum.Enum):
    BUILTIN = "BUILTIN"
    GLOBAL = "GLOBAL"
    COLLECTION = "COLLECTION"


class ApiVariableKind(str, enum.Enum):
    VALUE = "VALUE"
    SCRIPT = "SCRIPT"


class ApiVariable(Base):
    """A ``{{key}}`` usable in a request's URL, headers, or body.

    ``scope`` decides where it's visible from and where it's managed: a
    COLLECTION variable only resolves for requests in that collection; a
    GLOBAL one resolves everywhere; a BUILTIN one also resolves everywhere
    but lives on its own page (see api_client router) rather than the quick
    per-request Variables panel. Resolution precedence at send time is
    COLLECTION > GLOBAL > BUILTIN. VALUE variables hold a plain string;
    SCRIPT variables hold a Python snippet re-run fresh on every send.
    """

    __tablename__ = "api_variables"
    __table_args__ = (UniqueConstraint("scope", "collection_id", "key", name="uq_api_variable_scope_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[ApiVariableScope] = mapped_column(SAEnum(ApiVariableScope), nullable=False)
    collection_id: Mapped[int | None] = mapped_column(ForeignKey("api_collections.id"), nullable=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[ApiVariableKind] = mapped_column(SAEnum(ApiVariableKind), nullable=False, default=ApiVariableKind.VALUE)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_sensitive: Mapped[bool] = mapped_column(nullable=False, default=False)

    collection: Mapped["ApiCollection | None"] = relationship("ApiCollection", back_populates="variables")


class ApiHistory(Base):
    """One row per /api-client/send call — request and response saved
    together so a past hit can be reopened, restored, or re-exported
    without having to re-run it."""

    __tablename__ = "api_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("api_requests.id"), nullable=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    request_headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    request_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    request_body_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    response_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


# ── Knowledge Management ────────────────────────────────────────────────
# Sections → pages → boards (free-form canvas cards) → blocks. See
# docs/superpowers/specs/2026-10-04-knowledge-management-design.md.

class KnowledgeBlockKind(str, enum.Enum):
    TEXT = "TEXT"
    CODE = "CODE"
    IMAGE = "IMAGE"
    FILE = "FILE"
    TABLE = "TABLE"


class KnowledgeLinkTarget(str, enum.Enum):
    STORY = "STORY"
    SUBTASK = "SUBTASK"


class KnowledgeSection(Base):
    __tablename__ = "knowledge_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#9b9aa4")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    pages: Mapped[list["KnowledgePage"]] = relationship(
        "KnowledgePage", back_populates="section", order_by="KnowledgePage.position"
    )


class KnowledgePage(Base):
    __tablename__ = "knowledge_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("knowledge_sections.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="Untitled page")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    section: Mapped["KnowledgeSection"] = relationship("KnowledgeSection", back_populates="pages")
    boards: Mapped[list["KnowledgeBoard"]] = relationship(
        "KnowledgeBoard", back_populates="page", order_by="KnowledgeBoard.z"
    )
    links: Mapped[list["KnowledgePageLink"]] = relationship("KnowledgePageLink", back_populates="page")


class KnowledgeBoard(Base):
    __tablename__ = "knowledge_boards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("knowledge_pages.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    x: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    y: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=380)
    # NULL until the user resizes vertically: the board grows with its content.
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    z: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    page: Mapped["KnowledgePage"] = relationship("KnowledgePage", back_populates="boards")
    blocks: Mapped[list["KnowledgeBlock"]] = relationship(
        "KnowledgeBlock", back_populates="board", order_by="KnowledgeBlock.position"
    )


class KnowledgeBlock(Base):
    __tablename__ = "knowledge_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("knowledge_boards.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[KnowledgeBlockKind] = mapped_column(SAEnum(KnowledgeBlockKind), nullable=False)
    # TEXT: sanitised HTML · CODE: plain text · IMAGE: caption · TABLE: JSON · FILE: unused
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="TEXT")
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    board: Mapped["KnowledgeBoard"] = relationship("KnowledgeBoard", back_populates="blocks")


class KnowledgePageLink(Base):
    __tablename__ = "knowledge_page_links"
    __table_args__ = (UniqueConstraint("page_id", "target_type", "target_id", name="uq_knowledge_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("knowledge_pages.id"), nullable=False)
    target_type: Mapped[KnowledgeLinkTarget] = mapped_column(SAEnum(KnowledgeLinkTarget), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)

    page: Mapped["KnowledgePage"] = relationship("KnowledgePage", back_populates="links")
