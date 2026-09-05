"""app/jira_io.py: Subtask + Test Cases <-> Jira/Zephyr-shaped JSON."""

# testcase_to_jira_dict aliased to dump_testcase_jira on import: its name
# starts with "test", which pytest's default collector treats as a test
# function to call — aliasing avoids a spurious collection error without
# touching pytest config (see the same pattern in tests/test_testcase_io.py).
from app.jira_io import subtask_to_jira_json
from app.jira_io import testcase_to_jira_dict as dump_testcase_jira
from app.labels import get_labels, set_labels
from app.master_data import get_or_create
from app.models import (
    DEFAULT_SECTION_KINDS, Label, LabelAttachType, Phase, PhaseType, Story, Subtask,
    SubtaskType, TestCase, TestCaseCategory, TestCaseSection, TestCaseStatus, TestCaseStep,
    TestPriority, User, UserType, generate_internal_key,
)


def _make_subtask(db_session, code="SND-9874"):
    story = Story(display_code=f"{code}-STORY", title="Story", internal_key=generate_internal_key())
    db_session.add(story)
    db_session.flush()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.flush()
    subtask = Subtask(
        phase_id=phase.id, display_code=code, title="SIT Subtask",
        internal_key=generate_internal_key(), subtask_type=SubtaskType.EXECUTION,
    )
    db_session.add(subtask)
    db_session.flush()
    return subtask


def _make_testcase(db_session, subtask, code="SND-10055", **overrides):
    title = overrides.pop("title", "Verify something")
    testcase = TestCase(
        subtask_id=subtask.id, display_code=code, title=title,
        internal_key=generate_internal_key(), **overrides,
    )
    db_session.add(testcase)
    db_session.flush()
    for position, kind in enumerate(DEFAULT_SECTION_KINDS):
        db_session.add(TestCaseSection(testcase_id=testcase.id, kind=kind, position=position))
    db_session.flush()
    return testcase


def test_export_blank_testcase_uses_placeholders_for_every_unset_field(db_session):
    subtask = _make_subtask(db_session)
    testcase = _make_testcase(db_session, subtask)
    db_session.commit()

    data = dump_testcase_jira(testcase, db_session)
    assert data["issue_key"] == "SND-10055"
    assert data["summary"] == "Verify something"
    assert data["category"] == "{{placeholder_category}}"
    assert data["msisdn"] == "{{placeholder_msisdn_value}}"
    assert data["planned_cost"] == "{{placeholder_planned_cost_value}}"
    assert data["actual_cost"] == "{{placeholder_actual_cost_value}}"
    assert data["number_of_iteration"] == "{{placeholder_number_of_iteration_value}}"
    assert data["assignee"] == {"name": "{{placeholder_assignee_display_name}}", "username": "{{placeholder_assignee_username}}"}
    assert data["developer"] == {"name": "{{placeholder_developer_display_name}}", "username": "{{placeholder_developer_username}}"}
    assert data["tester"] == {"name": "{{placeholder_tester_display_name}}", "username": "{{placeholder_tester_username}}"}
    assert data["execution"]["status"] == "UNEXECUTED"
    assert data["execution"]["execution_id"] == "{{placeholder_execution_id_numeric_or_placeholder}}"
    assert data["fields"]["labels"] == []
    assert data["fields"]["description"] == "{{placeholder_description_text_or_placeholder}}"
    assert data["fields"]["priority"] == {"name": "{{placeholder_priority_name}}"}


def test_export_populated_testcase_has_real_values(db_session):
    subtask = _make_subtask(db_session, code="SND-9875")
    tester = get_or_create(db_session, User, "Andri Firman Nurvianto", type=UserType.TESTER)
    tester.jira_username = "ADL.ANDRIF"
    priority = get_or_create(db_session, TestPriority, "Highest")
    testcase = _make_testcase(
        db_session, subtask, code="SND-10056",
        category=TestCaseCategory.POSITIVE, msisdn="MSISDN #A: 62812",
        planned_cost="0", actual_cost="0", number_of_iteration=1,
        tester_id=tester.id, status=TestCaseStatus.PASS, jira_execution_id="196724",
        remark="Steps to reproduce", test_priority_id=priority.id,
    )
    label = get_or_create(db_session, Label, "SITScenario")
    set_labels(db_session, LabelAttachType.TESTCASE, testcase.id, [label.id])
    db_session.commit()

    data = dump_testcase_jira(testcase, db_session)
    assert data["category"] == "Positive"
    assert data["msisdn"] == "MSISDN #A: 62812"
    assert data["number_of_iteration"] == 1
    assert data["tester"] == {"name": "Andri Firman Nurvianto", "username": "ADL.ANDRIF"}
    assert data["execution"] == {
        "execution_id": "196724", "status": "PASS", "executed_on": None, "executed_by": None,
        "cycle_name": "SIT Subtask",
    }
    assert data["fields"]["labels"] == ["SITScenario"]
    assert data["fields"]["priority"] == {"name": "Highest"}
    assert data["fields"]["description"] == "Steps to reproduce"


def test_export_concatenates_steps_into_one_numbered_zephyr_entry(db_session):
    subtask = _make_subtask(db_session, code="SND-9876")
    testcase = _make_testcase(db_session, subtask, code="SND-10057")
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=1, step_text="Do A", expected_result="A happens", actual_result=""))
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=2, step_text="Do B", expected_result="B happens", actual_result=""))
    db_session.commit()

    data = dump_testcase_jira(testcase, db_session)
    assert len(data["zephyr_steps"]) == 3
    main_entry = next(z for z in data["zephyr_steps"] if z["step_type"] == "MAIN TEST")
    assert main_entry["order_id"] == 2
    assert main_entry["step"] == "MAIN TEST\r\n1. Do A\r\n2. Do B"
    assert main_entry["expected_result"] == "1. A happens\r\n2. B happens"
    pre_entry = next(z for z in data["zephyr_steps"] if z["step_type"] == "PRE CONDITION")
    assert pre_entry["order_id"] == 1
    assert pre_entry["step"] == "{{placeholder_precondition_step}}"


def test_subtask_to_jira_json_returns_envelope_with_one_entry_per_testcase_in_order(db_session):
    subtask = _make_subtask(db_session, code="SND-9877")
    _make_testcase(db_session, subtask, code="SND-10058")
    _make_testcase(db_session, subtask, code="SND-10059")
    db_session.commit()

    result = subtask_to_jira_json(subtask, db_session)
    assert result["parent_ticket"] == "SND-9877"
    assert result["test_suite"] == "SIT Subtask"
    assert result["total_test_cases"] == 2
    assert result["parent_ticket_info"]["assignee"] == {
        "name": "{{placeholder_assignee_display_name}}", "username": "{{placeholder_assignee_username}}",
    }
    assert result["parent_ticket_info"]["labels"] == []
    assert [entry["issue_key"] for entry in result["test_cases"]] == ["SND-10058", "SND-10059"]


import pytest

from app.jira_io import apply_jira_json_to_subtask


def _base_test_case_entry(issue_key="SND-10055", **overrides):
    entry = {
        "issue_key": issue_key,
        "summary": "Verify top-up",
        "category": "Positive",
        "planned_cost": "0",
        "actual_cost": "0",
        "number_of_iteration": 0,
        "msisdn": "MSISDN #A: 62812",
        "assignee": {"name": "Andri Firman Nurvianto", "username": "ADL.ANDRIF"},
        "developer": {"name": "Andi Tune", "username": "ADL.ANDIM"},
        "tester": {"name": "Andri Firman Nurvianto", "username": "ADL.ANDRIF"},
        "zephyr_steps": [
            {"order_id": 1, "step_type": "PRE CONDITION", "step": "PRE CONDITION\r\n1. Has account", "expected_result": "1. Ready"},
            {"order_id": 2, "step_type": "MAIN TEST", "step": "MAIN TEST\r\n1. Do A\r\n2. Do B", "expected_result": "1. A happens\r\n2. B happens"},
            {"order_id": 3, "step_type": "POST CONDITION", "step": "POST CONDITION\r\n1. Verify", "expected_result": "1. Logged"},
        ],
        "execution": {"execution_id": 196724, "status": "PASS", "executed_on": None, "executed_by": None, "cycle_name": "SIT"},
        "fields": {"description": "Steps to reproduce", "priority": {"name": "Highest"}, "labels": ["SITScenario"]},
    }
    entry.update(overrides)
    return entry


def test_import_creates_new_testcase_with_all_mapped_fields(db_session):
    subtask = _make_subtask(db_session, code="SND-9878")
    data = {
        "parent_ticket_info": {
            "assignee": {"name": "Andri Firman Nurvianto", "username": "ADL.ANDRIF"},
            "developer": {"name": "Andi Tune", "username": "ADL.ANDIM"},
            "tester": {"name": "Andri Firman Nurvianto", "username": "ADL.ANDRIF"},
            "labels": ["SITScenario"],
        },
        "test_cases": [_base_test_case_entry()],
    }

    apply_jira_json_to_subtask(db_session, subtask, data)
    db_session.commit()

    testcase = next(tc for tc in subtask.testcases if tc.display_code == "SND-10055")
    assert testcase.title == "Verify top-up"
    assert testcase.category.value == "Positive"
    assert testcase.msisdn == "MSISDN #A: 62812"
    assert testcase.test_priority_ref.name == "Highest"
    assert testcase.status == TestCaseStatus.PASS
    assert testcase.jira_execution_id == "196724"
    assert testcase.tester_user.name == "Andri Firman Nurvianto"
    assert testcase.tester_user.jira_username == "ADL.ANDRIF"
    assert testcase.developer.name == "Andi Tune"
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    assert [s.step_text for s in main_section.steps] == ["Do A", "Do B"]
    assert [s.expected_result for s in main_section.steps] == ["A happens", "B happens"]
    assert subtask.assignee.name == "Andri Firman Nurvianto"
    assert [l.name for l in get_labels(db_session, LabelAttachType.SUBTASK, subtask.id)] == ["SITScenario"]


def test_import_updates_existing_testcase_matched_by_issue_key(db_session):
    subtask = _make_subtask(db_session, code="SND-9879")
    testcase = _make_testcase(db_session, subtask, code="SND-10060", title="Old title")
    db_session.commit()

    apply_jira_json_to_subtask(
        db_session, subtask, {"test_cases": [_base_test_case_entry(issue_key="SND-10060", summary="New title")]},
    )
    db_session.commit()

    db_session.refresh(testcase)
    assert testcase.title == "New title"
    assert testcase.category.value == "Positive"


def test_import_skips_placeholder_fields_on_existing_testcase(db_session):
    subtask = _make_subtask(db_session, code="SND-9880")
    existing_priority = get_or_create(db_session, TestPriority, "Medium")
    testcase = _make_testcase(
        db_session, subtask, code="SND-10061", title="Keep me",
        msisdn="Already set", category=TestCaseCategory.NEGATIVE, test_priority_id=existing_priority.id,
    )
    db_session.commit()

    entry = _base_test_case_entry(
        issue_key="SND-10061",
        summary="{{placeholder_test_case_summary}}",
        category="{{placeholder_category}}",
        msisdn="{{placeholder_msisdn_value}}",
        fields={"description": "Steps to reproduce", "priority": {"name": "{{placeholder_priority_name}}"}, "labels": ["SITScenario"]},
    )
    apply_jira_json_to_subtask(db_session, subtask, {"test_cases": [entry]})
    db_session.commit()

    db_session.refresh(testcase)
    assert testcase.title == "Keep me"
    assert testcase.category == TestCaseCategory.NEGATIVE
    assert testcase.msisdn == "Already set"
    assert testcase.test_priority_ref.name == "Medium"


def test_import_leaves_section_steps_untouched_when_zephyr_entry_is_all_placeholder(db_session):
    subtask = _make_subtask(db_session, code="SND-9881")
    testcase = _make_testcase(db_session, subtask, code="SND-10062")
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=1, step_text="Existing step", expected_result="Existing result", actual_result=""))
    db_session.commit()

    entry = _base_test_case_entry(issue_key="SND-10062", zephyr_steps=[
        {"order_id": 1, "step_type": "PRE CONDITION", "step": "{{placeholder_pre_condition_step}}", "expected_result": "{{placeholder_pre_condition_expected}}"},
        {"order_id": 2, "step_type": "MAIN TEST", "step": "{{placeholder_main_test_step}}", "expected_result": "{{placeholder_main_test_expected}}"},
        {"order_id": 3, "step_type": "POST CONDITION", "step": "{{placeholder_post_condition_step}}", "expected_result": "{{placeholder_post_condition_expected}}"},
    ])
    apply_jira_json_to_subtask(db_session, subtask, {"test_cases": [entry]})
    db_session.commit()

    db_session.refresh(main_section)
    assert [s.step_text for s in main_section.steps] == ["Existing step"]


def test_import_missing_test_cases_key_raises_value_error(db_session):
    subtask = _make_subtask(db_session, code="SND-9882")
    with pytest.raises(ValueError):
        apply_jira_json_to_subtask(db_session, subtask, {})


def test_export_then_import_round_trips_steps(db_session):
    subtask = _make_subtask(db_session, code="SND-9883")
    testcase = _make_testcase(db_session, subtask, code="SND-10063")
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=1, step_text="Do A", expected_result="A happens", actual_result=""))
    db_session.commit()

    exported = subtask_to_jira_json(subtask, db_session)
    other_subtask = _make_subtask(db_session, code="SND-9884")
    apply_jira_json_to_subtask(db_session, other_subtask, exported)
    db_session.commit()

    imported_tc = next(tc for tc in other_subtask.testcases if tc.display_code == "SND-10063")
    imported_main = next(s for s in imported_tc.sections if s.kind.value == "MAIN")
    assert [s.step_text for s in imported_main.steps] == ["Do A"]
    assert [s.expected_result for s in imported_main.steps] == ["A happens"]


def test_import_zephyr_entry_with_placeholder_step_keeps_real_expected_result(db_session):
    # Regression test: _apply_zephyr_entry used to derive the number of
    # TestCaseStep rows to create from step_lines alone, so a placeholder
    # `step` (real `expected_result`) produced zero step_lines and silently
    # discarded the real expected_result content entirely.
    subtask = _make_subtask(db_session, code="SND-9885")
    testcase = _make_testcase(db_session, subtask, code="SND-10064")
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=1, step_text="Old step", expected_result="Old result", actual_result=""))
    db_session.commit()

    entry = _base_test_case_entry(issue_key="SND-10064", zephyr_steps=[
        {"order_id": 1, "step_type": "PRE CONDITION", "step": "{{placeholder_pre_condition_step}}", "expected_result": "{{placeholder_pre_condition_expected}}"},
        {"order_id": 2, "step_type": "MAIN TEST", "step": "{{placeholder_main_test_step}}", "expected_result": "1. A happens\r\n2. B happens"},
        {"order_id": 3, "step_type": "POST CONDITION", "step": "{{placeholder_post_condition_step}}", "expected_result": "{{placeholder_post_condition_expected}}"},
    ])
    apply_jira_json_to_subtask(db_session, subtask, {"test_cases": [entry]})
    db_session.commit()

    db_session.refresh(main_section)
    # step_text is preserved by position from the old row: position 0 keeps
    # "Old step" (the only old row that existed); position 1 has no old row
    # to preserve so it comes back blank.
    assert [s.step_text for s in main_section.steps] == ["Old step", ""]
    assert [s.expected_result for s in main_section.steps] == ["A happens", "B happens"]


def test_import_zephyr_entry_with_placeholder_expected_result_keeps_real_step(db_session):
    # Companion test, symmetric with the one above: real `step`, placeholder
    # `expected_result` -> real step text is written, and expected_result is
    # preserved BY POSITION from the old row (not blanked) — this is Bug 3
    # from the final whole-branch review: the mirror direction used to blank
    # expected_result to "" instead of preserving it.
    subtask = _make_subtask(db_session, code="SND-9886")
    testcase = _make_testcase(db_session, subtask, code="SND-10065")
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=1, step_text="Old step", expected_result="Old result", actual_result=""))
    db_session.commit()

    entry = _base_test_case_entry(issue_key="SND-10065", zephyr_steps=[
        {"order_id": 1, "step_type": "PRE CONDITION", "step": "{{placeholder_pre_condition_step}}", "expected_result": "{{placeholder_pre_condition_expected}}"},
        {"order_id": 2, "step_type": "MAIN TEST", "step": "MAIN TEST\r\n1. Do A\r\n2. Do B", "expected_result": "{{placeholder_main_test_expected}}"},
        {"order_id": 3, "step_type": "POST CONDITION", "step": "{{placeholder_post_condition_step}}", "expected_result": "{{placeholder_post_condition_expected}}"},
    ])
    apply_jira_json_to_subtask(db_session, subtask, {"test_cases": [entry]})
    db_session.commit()

    db_session.refresh(main_section)
    assert [s.step_text for s in main_section.steps] == ["Do A", "Do B"]
    assert [s.expected_result for s in main_section.steps] == ["Old result", ""]


def test_import_zephyr_entry_always_preserves_actual_result_by_position(db_session):
    # Regression (Bug 2, final whole-branch review): export never carries
    # actual_result (Jira's schema has no field for it), and the old code
    # ALWAYS wrote "" for it on import — silently wiping every
    # tester-recorded actual_result on any section an import touched, even
    # when the step/expected_result content was otherwise real and unrelated.
    subtask = _make_subtask(db_session, code="SND-9887")
    testcase = _make_testcase(db_session, subtask, code="SND-10066")
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=1, step_text="Old step", expected_result="Old result", actual_result="Recorded by tester"))
    db_session.commit()

    entry = _base_test_case_entry(issue_key="SND-10066")  # real step + expected_result content
    apply_jira_json_to_subtask(db_session, subtask, {"test_cases": [entry]})
    db_session.commit()

    db_session.refresh(main_section)
    assert [s.step_text for s in main_section.steps] == ["Do A", "Do B"]
    assert [s.expected_result for s in main_section.steps] == ["A happens", "B happens"]
    assert [s.actual_result for s in main_section.steps] == ["Recorded by tester", ""]


def test_import_zephyr_entry_with_matching_step_counts_preserves_expected_result_cleanly(db_session):
    # A cleaner companion to the placeholder-expected_result test above:
    # same old-step count as new-step count, so the "preserve by position"
    # behavior reads unambiguously for every position, not just the first.
    subtask = _make_subtask(db_session, code="SND-9888")
    testcase = _make_testcase(db_session, subtask, code="SND-10067")
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=1, step_text="Old A", expected_result="Old expected A", actual_result=""))
    db_session.add(TestCaseStep(section_id=main_section.id, step_no=2, step_text="Old B", expected_result="Old expected B", actual_result=""))
    db_session.commit()

    entry = _base_test_case_entry(issue_key="SND-10067", zephyr_steps=[
        {"order_id": 1, "step_type": "PRE CONDITION", "step": "{{placeholder_pre_condition_step}}", "expected_result": "{{placeholder_pre_condition_expected}}"},
        {"order_id": 2, "step_type": "MAIN TEST", "step": "MAIN TEST\r\n1. New A\r\n2. New B", "expected_result": "{{placeholder_main_test_expected}}"},
        {"order_id": 3, "step_type": "POST CONDITION", "step": "{{placeholder_post_condition_step}}", "expected_result": "{{placeholder_post_condition_expected}}"},
    ])
    apply_jira_json_to_subtask(db_session, subtask, {"test_cases": [entry]})
    db_session.commit()

    db_session.refresh(main_section)
    assert [s.step_text for s in main_section.steps] == ["New A", "New B"]
    assert [s.expected_result for s in main_section.steps] == ["Old expected A", "Old expected B"]


def test_import_over_section_with_screenshot_cleans_up_instead_of_crashing(db_session):
    # Regression (Bug 1, final whole-branch review, Critical): _apply_zephyr_
    # entry used to call db.delete(step) directly, bypassing
    # app.deletion.delete_step's screenshot cleanup. Importing over a section
    # whose step has a Screenshot child row raised an uncaught IntegrityError
    # (NOT NULL constraint on screenshots.step_id), which propagated past the
    # route's `except ValueError` as an unhandled 500, and left the
    # screenshot's file orphaned on disk.
    from app.models import Screenshot
    from app.routers.screenshots import UPLOADS_DIR

    subtask = _make_subtask(db_session, code="SND-9889")
    testcase = _make_testcase(db_session, subtask, code="SND-10068")
    main_section = next(s for s in testcase.sections if s.kind.value == "MAIN")
    step = TestCaseStep(section_id=main_section.id, step_no=1, step_text="Old step", expected_result="Old result", actual_result="")
    db_session.add(step)
    db_session.commit()

    relative_path = f"screenshots/jira_io_test/{testcase.id}_{step.id}.png"
    disk_path = UPLOADS_DIR / relative_path
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(b"fake-image-bytes")
    screenshot = Screenshot(step_id=step.id, file_path=relative_path)
    db_session.add(screenshot)
    db_session.commit()
    screenshot_id = screenshot.id

    entry = _base_test_case_entry(issue_key="SND-10068")
    apply_jira_json_to_subtask(db_session, subtask, {"test_cases": [entry]})  # must not raise
    db_session.commit()

    assert db_session.get(Screenshot, screenshot_id) is None
    assert not disk_path.exists()


def test_export_repeated_section_kind_emits_only_first_section_of_that_kind(db_session):
    # Regression (Bug 4, final whole-branch review): a TestCase can have more
    # than one section of the same `kind` (a real, existing local feature —
    # see TestCaseSection's docstring), but Jira has no equivalent. Exporting
    # every section used to emit two "MAIN TEST" entries sharing the same
    # order_id/step_type — malformed/ambiguous output.
    subtask = _make_subtask(db_session, code="SND-9890")
    testcase = _make_testcase(db_session, subtask, code="SND-10069")
    extra_main = TestCaseSection(testcase_id=testcase.id, kind=next(s.kind for s in testcase.sections if s.kind.value == "MAIN"), position=99)
    db_session.add(extra_main)
    db_session.flush()
    db_session.expire(testcase, ["sections"])
    main_sections = [s for s in testcase.sections if s.kind.value == "MAIN"]
    assert len(main_sections) == 2
    db_session.add(TestCaseStep(section_id=main_sections[0].id, step_no=1, step_text="First main", expected_result="e1", actual_result=""))
    db_session.add(TestCaseStep(section_id=main_sections[1].id, step_no=1, step_text="Second main", expected_result="e2", actual_result=""))
    db_session.commit()

    data = dump_testcase_jira(testcase, db_session)
    main_entries = [z for z in data["zephyr_steps"] if z["step_type"] == "MAIN TEST"]
    assert len(main_entries) == 1
    assert "First main" in main_entries[0]["step"]
    assert "Second main" not in main_entries[0]["step"]


def test_import_repeated_section_kind_touches_only_first_section_of_that_kind(db_session):
    # Regression (Bug 4): matching by step_type alone made `next(...)` return
    # the SAME first matching zephyr_steps entry for every section of that
    # kind, so a second MAIN section got silently overwritten with the FIRST
    # MAIN section's content, discarding whatever was actually there.
    subtask = _make_subtask(db_session, code="SND-9891")
    testcase = _make_testcase(db_session, subtask, code="SND-10070")
    extra_main = TestCaseSection(testcase_id=testcase.id, kind=next(s.kind for s in testcase.sections if s.kind.value == "MAIN"), position=99)
    db_session.add(extra_main)
    db_session.flush()
    db_session.expire(testcase, ["sections"])
    main_sections = [s for s in testcase.sections if s.kind.value == "MAIN"]
    db_session.add(TestCaseStep(section_id=main_sections[0].id, step_no=1, step_text="First old", expected_result="e1", actual_result=""))
    db_session.add(TestCaseStep(section_id=main_sections[1].id, step_no=1, step_text="Second old", expected_result="e2", actual_result=""))
    db_session.commit()

    entry = _base_test_case_entry(issue_key="SND-10070")  # one MAIN TEST entry: "Do A" / "Do B"
    apply_jira_json_to_subtask(db_session, subtask, {"test_cases": [entry]})
    db_session.commit()

    db_session.refresh(main_sections[0])
    db_session.refresh(main_sections[1])
    assert [s.step_text for s in main_sections[0].steps] == ["Do A", "Do B"]
    assert [s.step_text for s in main_sections[1].steps] == ["Second old"]
    assert [s.expected_result for s in main_sections[1].steps] == ["e2"]
