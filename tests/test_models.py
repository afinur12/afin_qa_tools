import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Bug, BugSeverity, BugStatus, Label, LabelAssignment, LabelAttachType, Note, NoteAttachType, Phase, PhaseType, PrebuiltTestCase, Service, Simulate, Story, Subtask, SubtaskType, StepSection, TaskStatus, TestCase, TestCaseCategory, TestCaseSection, TestCaseStatus, TestCaseStep, TestPriority, TestType, User, UserType


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
    assert tc.status == TestCaseStatus.TO_DO
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
    section = TestCaseSection(testcase_id=tc.id, kind=StepSection.MAIN, position=0)
    db_session.add(section)
    db_session.commit()
    db_session.add(TestCaseStep(section_id=section.id, step_no=2, step_text="second"))
    db_session.add(TestCaseStep(section_id=section.id, step_no=1, step_text="first"))
    db_session.commit()
    db_session.refresh(tc)
    main_steps = [s for s in tc.all_steps if s.section.kind == StepSection.MAIN]
    assert [s.step_no for s in main_steps] == [1, 2]


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


def test_task_status_label_replaces_underscore_with_space():
    assert TaskStatus.TO_DO.label == "TO DO"
    assert TaskStatus.BACK_LOG.label == "BACK LOG"
    assert TaskStatus.DONE.label == "DONE"


def test_story_status_defaults_to_to_do(db_session):
    story = Story(display_code="EX-30", title="A", internal_key="k30")
    db_session.add(story)
    db_session.commit()
    db_session.refresh(story)
    assert story.status == TaskStatus.TO_DO


def test_subtask_status_defaults_to_to_do(db_session):
    story = Story(display_code="EX-31", title="A", internal_key="k31")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k32", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    db_session.refresh(subtask)
    assert subtask.status == TaskStatus.TO_DO


def test_service_name_is_unique(db_session):
    db_session.add(Service(name="payment-service"))
    db_session.commit()
    db_session.add(Service(name="payment-service"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_simulate_name_is_unique(db_session):
    db_session.add(Simulate(name="E2E"))
    db_session.commit()
    db_session.add(Simulate(name="E2E"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_test_type_name_is_unique(db_session):
    db_session.add(TestType(name="POSITIVE"))
    db_session.commit()
    db_session.add(TestType(name="POSITIVE"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_test_priority_name_is_unique(db_session):
    db_session.add(TestPriority(name="HIGH"))
    db_session.commit()
    db_session.add(TestPriority(name="HIGH"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_prebuilt_service_simulate_test_type_relationships(db_session):
    service = Service(name="auth-service")
    simulate = Simulate(name="E2E")
    test_type = TestType(name="POSITIVE")
    db_session.add_all([service, simulate, test_type])
    db_session.commit()

    prebuilt = PrebuiltTestCase(name="Login", service_id=service.id, simulate_id=simulate.id, test_type_id=test_type.id)
    db_session.add(prebuilt)
    db_session.commit()
    db_session.refresh(prebuilt)
    assert prebuilt.service.name == "auth-service"
    assert prebuilt.simulate_ref.name == "E2E"
    assert prebuilt.test_type_ref.name == "POSITIVE"


def test_prebuilt_service_simulate_test_type_default_to_none(db_session):
    prebuilt = PrebuiltTestCase(name="Untagged")
    db_session.add(prebuilt)
    db_session.commit()
    db_session.refresh(prebuilt)
    assert prebuilt.service is None
    assert prebuilt.simulate_ref is None
    assert prebuilt.test_type_ref is None


def test_testcase_test_type_relationship(db_session):
    story = Story(display_code="EX-40", title="A", internal_key="k40")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k41", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    test_type = TestType(name="REGRESSION")
    db_session.add(test_type)
    db_session.commit()

    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k42", test_type_id=test_type.id)
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    assert tc.test_type_ref.name == "REGRESSION"


def test_testcase_test_priority_relationship(db_session):
    story = Story(display_code="EX-43", title="A", internal_key="k43")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k44", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    priority = TestPriority(name="HIGHEST")
    db_session.add(priority)
    db_session.commit()

    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k45", test_priority_id=priority.id)
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)
    assert tc.test_priority_ref.name == "HIGHEST"


def test_note_create(db_session):
    story = Story(display_code="EX-9", title="A", internal_key="k24")
    db_session.add(story)
    db_session.commit()
    note = Note(
        attach_type=NoteAttachType.STORY,
        attach_id=story.id,
        language="CURL",
        content="curl https://api.example.com/health",
        remark="Health check",
    )
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)
    assert note.id is not None


def test_user_name_is_unique(db_session):
    db_session.add(User(name="Jane Doe", type=UserType.TESTER))
    db_session.commit()
    db_session.add(User(name="Jane Doe", type=UserType.DEVELOPER))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_label_name_is_unique(db_session):
    db_session.add(Label(name="regression"))
    db_session.commit()
    db_session.add(Label(name="regression"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_label_assignment_rejects_exact_duplicate(db_session):
    label = Label(name="flaky")
    db_session.add(label)
    db_session.commit()
    db_session.add(LabelAssignment(label_id=label.id, attach_type=LabelAttachType.STORY, attach_id=1))
    db_session.commit()
    db_session.add(LabelAssignment(label_id=label.id, attach_type=LabelAttachType.STORY, attach_id=1))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_story_assignee_tester_developer_relationships(db_session):
    tester = User(name="Tess Tester", type=UserType.TESTER)
    developer = User(name="Dave Dev", type=UserType.DEVELOPER)
    assignee = User(name="Ann Assignee", type=UserType.TESTER)
    db_session.add_all([tester, developer, assignee])
    db_session.commit()

    story = Story(
        display_code="EX-60", title="A", internal_key="k60",
        tester_id=tester.id, developer_id=developer.id, assignee_id=assignee.id,
    )
    db_session.add(story)
    db_session.commit()
    db_session.refresh(story)
    assert story.tester_user.name == "Tess Tester"
    assert story.developer.name == "Dave Dev"
    assert story.assignee.name == "Ann Assignee"


def test_story_assignee_tester_developer_default_to_none(db_session):
    story = Story(display_code="EX-61", title="A", internal_key="k61")
    db_session.add(story)
    db_session.commit()
    db_session.refresh(story)
    assert story.assignee is None
    assert story.tester_user is None
    assert story.developer is None


def test_subtask_bug_testcase_have_the_same_three_relationships(db_session):
    """One combined test covering all three remaining entities — same
    shape as the Story tests above, just confirming the pattern was
    applied uniformly rather than re-deriving it three more times.
    Uses distinct users for each FK field to catch wrong foreign_keys assignments."""
    users = [
        User(name="Tester1", type=UserType.TESTER),
        User(name="Developer1", type=UserType.DEVELOPER),
        User(name="Assignee1", type=UserType.TESTER),
        User(name="Tester2", type=UserType.TESTER),
        User(name="Developer2", type=UserType.DEVELOPER),
        User(name="Assignee2", type=UserType.TESTER),
        User(name="Tester3", type=UserType.TESTER),
        User(name="Developer3", type=UserType.DEVELOPER),
        User(name="Assignee3", type=UserType.TESTER),
    ]
    db_session.add_all(users)
    db_session.commit()

    story = Story(display_code="EX-62", title="A", internal_key="k62")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()

    # Subtask with all three distinct users
    subtask = Subtask(
        phase_id=phase.id, display_code="S-1", title="Exec", internal_key="k63",
        subtask_type=SubtaskType.EXECUTION,
        tester_id=users[0].id, developer_id=users[1].id, assignee_id=users[2].id,
    )
    db_session.add(subtask)
    db_session.commit()

    # TestCase with all three distinct users
    tc = TestCase(
        subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k64",
        tester_id=users[3].id, developer_id=users[4].id, assignee_id=users[5].id,
    )
    db_session.add(tc)
    db_session.commit()

    # Bug with all three distinct users
    bug = Bug(
        subtask_id=subtask.id, display_code="B-1", title="[ISSUE] a", internal_key="k65",
        tester_id=users[6].id, developer_id=users[7].id, assignee_id=users[8].id,
    )
    db_session.add(bug)
    db_session.commit()

    db_session.refresh(subtask)
    db_session.refresh(tc)
    db_session.refresh(bug)

    # Subtask assertions
    assert subtask.tester_user.name == "Tester1"
    assert subtask.developer.name == "Developer1"
    assert subtask.assignee.name == "Assignee1"

    # TestCase assertions
    assert tc.tester_user.name == "Tester2"
    assert tc.developer.name == "Developer2"
    assert tc.assignee.name == "Assignee2"

    # Bug assertions
    assert bug.tester_user.name == "Tester3"
    assert bug.developer.name == "Developer3"
    assert bug.assignee.name == "Assignee3"


def test_testcase_new_jira_fields_default_to_none(db_session):
    story = Story(display_code="JR-1", title="A", internal_key="jk1")
    db_session.add(story)
    db_session.flush()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.flush()
    subtask = Subtask(phase_id=phase.id, display_code="JR-1-S1", title="S", internal_key="jk2", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.flush()
    testcase = TestCase(subtask_id=subtask.id, display_code="JR-1-TC1", title="T", internal_key="jk3")
    db_session.add(testcase)
    db_session.commit()

    assert testcase.category is None
    assert testcase.msisdn is None
    assert testcase.planned_cost is None
    assert testcase.actual_cost is None
    assert testcase.number_of_iteration is None
    assert testcase.jira_execution_id is None


def test_testcase_category_accepts_all_three_values(db_session):
    story = Story(display_code="JR-2", title="A", internal_key="jk4")
    db_session.add(story)
    db_session.flush()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.flush()
    subtask = Subtask(phase_id=phase.id, display_code="JR-2-S1", title="S", internal_key="jk5", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.flush()
    for i, category in enumerate(TestCaseCategory):
        testcase = TestCase(
            subtask_id=subtask.id, display_code=f"JR-2-TC{i}", title="T", internal_key=f"jk6{i}",
            category=category,
        )
        db_session.add(testcase)
    db_session.commit()

    values = {tc.category.value for tc in subtask.testcases}
    assert values == {"Positive", "Negative", "Regression"}


def test_user_jira_username_defaults_to_none(db_session):
    user = User(name="Jira Test User", type=UserType.TESTER)
    db_session.add(user)
    db_session.commit()
    assert user.jira_username is None

    user.jira_username = "ADL.TEST"
    db_session.commit()
    assert user.jira_username == "ADL.TEST"
