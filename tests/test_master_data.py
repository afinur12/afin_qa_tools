"""app/master_data.py: get-or-create, default seeding, and the one-time
free-text -> FK backfill migration for Service/Simulate/TestType."""

from app.master_data import (
    get_or_create,
    merge_duplicate_names,
    migrate_free_text_to_master,
    migrate_testcase_tester_to_user,
    seed_defaults,
)
from app.models import (
    Label,
    LabelAssignment,
    LabelAttachType,
    PrebuiltTestCase,
    Service,
    Simulate,
    TestCase,
    TestPriority,
    TestType,
    User,
    UserType,
)


def test_get_or_create_returns_none_for_blank_name(db_session):
    assert get_or_create(db_session, Service, "") is None
    assert get_or_create(db_session, Service, None) is None
    assert get_or_create(db_session, Service, "   ") is None


def test_get_or_create_trims_and_reuses_existing_row(db_session):
    first = get_or_create(db_session, Service, "  payment-service  ")
    db_session.commit()
    second = get_or_create(db_session, Service, "payment-service")
    assert first.id == second.id
    assert db_session.query(Service).count() == 1


def test_get_or_create_is_case_insensitive(db_session):
    lower = get_or_create(db_session, Service, "payment-service")
    db_session.commit()
    upper = get_or_create(db_session, Service, "Payment-Service")
    db_session.commit()
    assert lower.id == upper.id
    assert db_session.query(Service).count() == 1


def test_seed_defaults_populates_test_types_and_simulates_once(db_session):
    seed_defaults(db_session)
    test_type_names = {t.name for t in db_session.query(TestType).all()}
    simulate_names = {s.name for s in db_session.query(Simulate).all()}
    assert test_type_names == {"Positive", "Negative", "Regression"}
    assert simulate_names == {"E2E", "API Testing"}

    # A custom value already in the table (e.g. from a real user's DB)
    # must survive a second seed call untouched — seeding never re-runs
    # once the table already has rows.
    db_session.add(TestType(name="CUSTOM"))
    db_session.commit()
    seed_defaults(db_session)
    assert db_session.query(TestType).filter(TestType.name == "CUSTOM").count() == 1
    assert db_session.query(TestType).filter(TestType.name == "Positive").count() == 1


def _make_prebuilt_with_legacy_text(db, name, service_name=None, simulate=None, test_type=None):
    prebuilt = PrebuiltTestCase(name=name, service_name=service_name, simulate=simulate, test_type=test_type)
    db.add(prebuilt)
    db.commit()
    db.refresh(prebuilt)
    return prebuilt


def test_migrate_backfills_prebuilt_fk_columns_from_legacy_text(db_session):
    prebuilt = _make_prebuilt_with_legacy_text(
        db_session, "Legacy", service_name="auth-service", simulate="E2E", test_type="POSITIVE",
    )

    migrate_free_text_to_master(db_session)
    db_session.refresh(prebuilt)

    assert prebuilt.service.name == "auth-service"
    assert prebuilt.simulate_ref.name == "E2E"
    assert prebuilt.test_type_ref.name == "POSITIVE"
    # Old columns are left untouched.
    assert prebuilt.service_name == "auth-service"
    assert prebuilt.simulate == "E2E"
    assert prebuilt.test_type == "POSITIVE"


def test_migrate_backfills_testcase_test_type_from_legacy_text(db_session):
    from app.models import Phase, PhaseType, Story, Subtask, SubtaskType

    story = Story(display_code="EX-50", title="A", internal_key="k50")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k51", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k52", test_type="NEGATIVE")
    db_session.add(tc)
    db_session.commit()

    migrate_free_text_to_master(db_session)
    db_session.refresh(tc)
    assert tc.test_type_ref.name == "NEGATIVE"


def test_migrate_reuses_one_master_row_for_matching_legacy_values(db_session):
    _make_prebuilt_with_legacy_text(db_session, "One", service_name="auth-service")
    _make_prebuilt_with_legacy_text(db_session, "Two", service_name="auth-service")

    migrate_free_text_to_master(db_session)

    assert db_session.query(Service).filter(Service.name == "auth-service").count() == 1


def test_migrate_leaves_blank_legacy_values_unset(db_session):
    prebuilt = _make_prebuilt_with_legacy_text(db_session, "Blank")

    migrate_free_text_to_master(db_session)
    db_session.refresh(prebuilt)

    assert prebuilt.service_id is None
    assert prebuilt.simulate_id is None
    assert prebuilt.test_type_id is None


def test_migrate_is_idempotent(db_session):
    _make_prebuilt_with_legacy_text(db_session, "One", service_name="auth-service")

    migrate_free_text_to_master(db_session)
    migrate_free_text_to_master(db_session)

    assert db_session.query(Service).count() == 1


def test_migrate_does_not_overwrite_an_already_set_fk(db_session):
    other_service = Service(name="different-service")
    db_session.add(other_service)
    db_session.commit()
    prebuilt = _make_prebuilt_with_legacy_text(db_session, "Already linked", service_name="auth-service")
    prebuilt.service_id = other_service.id
    db_session.commit()

    migrate_free_text_to_master(db_session)
    db_session.refresh(prebuilt)

    assert prebuilt.service_id == other_service.id, "a row that already has its FK set must not be re-derived from stale free text"


def test_get_or_create_passes_through_extra_fields_on_creation(db_session):
    user = get_or_create(db_session, User, "Jane Doe", type=UserType.TESTER)
    db_session.commit()
    assert user.name == "Jane Doe"
    assert user.type == UserType.TESTER


def test_get_or_create_extra_fields_are_ignored_when_reusing_an_existing_row(db_session):
    existing = User(name="Jane Doe", type=UserType.TESTER)
    db_session.add(existing)
    db_session.commit()

    # Reusing by name must not try to change `type` on the existing row —
    # get_or_create only uses extra_fields when actually creating.
    found = get_or_create(db_session, User, "Jane Doe", type=UserType.DEVELOPER)
    db_session.commit()
    assert found.id == existing.id
    assert found.type == UserType.TESTER


def test_migrate_testcase_tester_creates_a_tester_type_user(db_session):
    from app.models import Phase, PhaseType, Story, Subtask, SubtaskType

    story = Story(display_code="EX-70", title="A", internal_key="k70")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k71", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k72", tester="Existing Tester")
    db_session.add(tc)
    db_session.commit()

    migrate_testcase_tester_to_user(db_session)
    db_session.refresh(tc)

    assert tc.tester_id is not None
    assert tc.tester_user.name == "Existing Tester"
    assert tc.tester_user.type == UserType.TESTER
    # Old column is untouched.
    assert tc.tester == "Existing Tester"


def test_migrate_testcase_tester_is_idempotent_and_reuses_one_user_per_name(db_session):
    from app.models import Phase, PhaseType, Story, Subtask, SubtaskType

    story = Story(display_code="EX-71", title="A", internal_key="k73")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k74", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    tc1 = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k75", tester="Same Person")
    tc2 = TestCase(subtask_id=subtask.id, display_code="TC-2", title="B", internal_key="k76", tester="Same Person")
    db_session.add_all([tc1, tc2])
    db_session.commit()

    migrate_testcase_tester_to_user(db_session)
    migrate_testcase_tester_to_user(db_session)  # second call must be a no-op

    assert db_session.query(User).filter(User.name == "Same Person").count() == 1
    db_session.refresh(tc1)
    db_session.refresh(tc2)
    assert tc1.tester_id == tc2.tester_id


def test_migrate_testcase_tester_does_not_overwrite_an_already_set_fk(db_session):
    from app.models import Phase, PhaseType, Story, Subtask, SubtaskType

    other_user = User(name="Different Person", type=UserType.TESTER)
    db_session.add(other_user)
    db_session.commit()

    story = Story(display_code="EX-72", title="A", internal_key="k77")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k78", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k79",
                   tester="Original", tester_id=other_user.id)
    db_session.add(tc)
    db_session.commit()

    migrate_testcase_tester_to_user(db_session)
    db_session.refresh(tc)

    assert tc.tester_id == other_user.id, "a row that already has its FK set must not be re-derived from stale free text"


def test_migrate_testcase_tester_does_not_restore_a_deliberately_cleared_fk(db_session):
    """Simulates an app restart after a user clears Section 1's Tester
    dropdown back to blank: the legacy `tester` text column is untouched,
    so a naive `tester_id IS NULL` migration would silently re-derive and
    restore the old value. Once a row has been considered (tester_migrated),
    it must never be reconsidered, even if tester_id later goes back to
    None."""
    from app.models import Phase, PhaseType, Story, Subtask, SubtaskType

    story = Story(display_code="EX-73", title="A", internal_key="k80")
    db_session.add(story)
    db_session.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db_session.add(phase)
    db_session.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key="k81", subtask_type=SubtaskType.EXECUTION)
    db_session.add(subtask)
    db_session.commit()
    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k82",
                   tester="Legacy Name")
    db_session.add(tc)
    db_session.commit()

    # First run (e.g. first startup after the FK column was introduced):
    # backfills tester_id from the legacy text, same as any fresh migration.
    migrate_testcase_tester_to_user(db_session)
    db_session.refresh(tc)
    assert tc.tester_id is not None

    # The user then deliberately clears the Tester dropdown on Section 1's
    # edit form. The legacy `tester` column is never touched by that edit.
    tc.tester_id = None
    db_session.commit()

    # Simulates the next app restart re-running the migration.
    migrate_testcase_tester_to_user(db_session)
    db_session.refresh(tc)

    assert tc.tester_id is None, "a deliberately cleared tester_id must not be resurrected from stale legacy text"


def _make_subtask_for_testcase(db, code="EX-90"):
    from app.models import Phase, PhaseType, Story, Subtask, SubtaskType

    story = Story(display_code=code, title="A", internal_key=f"k-{code}")
    db.add(story)
    db.commit()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db.add(phase)
    db.commit()
    subtask = Subtask(phase_id=phase.id, display_code="S-1", title="Exec",
                       internal_key=f"k-{code}-s", subtask_type=SubtaskType.EXECUTION)
    db.add(subtask)
    db.commit()
    return subtask


def test_merge_duplicate_names_merges_test_type_case_variants_and_reassigns_fk(db_session):
    all_caps = TestType(name="POSITIVE")
    proper = TestType(name="Positive")
    db_session.add_all([all_caps, proper])
    db_session.commit()

    subtask = _make_subtask_for_testcase(db_session, "EX-91")
    tc = TestCase(subtask_id=subtask.id, display_code="TC-1", title="A", internal_key="k91",
                   test_type_id=all_caps.id)
    db_session.add(tc)
    db_session.commit()

    merge_duplicate_names(db_session)

    remaining = db_session.query(TestType).filter(TestType.name.ilike("positive")).all()
    assert len(remaining) == 1
    assert remaining[0].name == "Positive"
    db_session.refresh(tc)
    assert tc.test_type_id == remaining[0].id


def test_merge_duplicate_names_capitalizes_test_priority_survivor(db_session):
    db_session.add_all([TestPriority(name="HIGH"), TestPriority(name="high")])
    db_session.commit()

    merge_duplicate_names(db_session)

    remaining = db_session.query(TestPriority).all()
    assert [p.name for p in remaining] == ["High"]


def test_merge_duplicate_names_leaves_non_duplicate_rows_untouched(db_session):
    """Only an actual case-collision group is touched — a lone all-caps
    value with nothing to merge against keeps its existing spelling."""
    db_session.add(TestType(name="SMOKE"))
    db_session.commit()

    merge_duplicate_names(db_session)

    assert [t.name for t in db_session.query(TestType).all()] == ["SMOKE"]


def test_merge_duplicate_names_does_not_capitalize_service_or_simulate_survivors(db_session):
    db_session.add_all([Service(name="payment-service"), Service(name="Payment-Service")])
    db_session.commit()

    merge_duplicate_names(db_session)

    remaining = db_session.query(Service).all()
    assert len(remaining) == 1
    assert remaining[0].name in ("payment-service", "Payment-Service")


def test_merge_duplicate_names_merges_labels_and_drops_redundant_assignment_on_collision(db_session):
    lower = Label(name="flaky")
    proper = Label(name="Flaky")
    db_session.add_all([lower, proper])
    db_session.commit()

    # Both duplicate labels attached to the SAME story — merging must not
    # violate LabelAssignment's UNIQUE(label_id, attach_type, attach_id).
    db_session.add_all([
        LabelAssignment(label_id=lower.id, attach_type=LabelAttachType.STORY, attach_id=1),
        LabelAssignment(label_id=proper.id, attach_type=LabelAttachType.STORY, attach_id=1),
    ])
    db_session.commit()

    merge_duplicate_names(db_session)

    remaining_labels = db_session.query(Label).all()
    assert len(remaining_labels) == 1
    survivor = remaining_labels[0]
    assignments = db_session.query(LabelAssignment).filter(
        LabelAssignment.attach_type == LabelAttachType.STORY, LabelAssignment.attach_id == 1
    ).all()
    assert len(assignments) == 1
    assert assignments[0].label_id == survivor.id


def test_merge_duplicate_names_is_idempotent(db_session):
    db_session.add_all([TestType(name="POSITIVE"), TestType(name="Positive")])
    db_session.commit()

    merge_duplicate_names(db_session)
    merge_duplicate_names(db_session)  # second call must be a no-op, not an error

    assert db_session.query(TestType).count() == 1
