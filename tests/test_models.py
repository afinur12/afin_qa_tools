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
