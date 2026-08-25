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
