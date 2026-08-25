import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Phase, PhaseType, Story, Subtask, SubtaskType, StepSection, TestCase, TestCaseStatus, TestCaseStep


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
