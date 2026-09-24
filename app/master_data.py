"""Master data: Service, Simulate, and Test Type.

get_or_create() is the single place that resolves a free-text name to a
master row (used by the startup migration below, and by JSON import in
app/testcase_io.py so an imported test_type string that isn't already a
known value gets its own row rather than being rejected).
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Label, LabelAssignment, PrebuiltTestCase, Service, Simulate, TestCase, TestPriority, TestType, User, UserType

DEFAULT_TEST_TYPES = ["Positive", "Negative", "Regression"]
DEFAULT_SIMULATES = ["E2E", "API Testing"]
DEFAULT_TEST_PRIORITIES = ["Highest", "High", "Medium", "Low"]


def get_or_create(db: Session, model, name: str | None, **extra_fields):
    """Case-insensitive, trimmed match on `name` — "High" and "HIGH" resolve
    to the same row rather than creating a second one; whichever casing got
    there first wins. None in, None out — there's nothing to link a blank
    value to. `extra_fields` are only used when actually creating a new row
    (e.g. `type=UserType.TESTER` for User, which has a second required
    column Service/Simulate/TestType don't) — reusing an existing row never
    touches its other columns."""
    name = (name or "").strip()
    if not name:
        return None
    row = db.query(model).filter(func.lower(model.name) == name.lower()).first()
    if row is None:
        row = model(name=name, **extra_fields)
        db.add(row)
        db.flush()
    return row


def seed_defaults(db: Session) -> None:
    """Insert the default Test Type, Simulate, and Test Priority values
    once, on an empty table. From then on they're ordinary rows the user
    can rename or delete freely, so this never runs again once a table
    already has a row."""
    if not db.query(TestType).first():
        for name in DEFAULT_TEST_TYPES:
            db.add(TestType(name=name))
    if not db.query(Simulate).first():
        for name in DEFAULT_SIMULATES:
            db.add(Simulate(name=name))
    if not db.query(TestPriority).first():
        for name in DEFAULT_TEST_PRIORITIES:
            db.add(TestPriority(name=name))
    db.commit()


def _migrate_column(db: Session, model, old_column: str, new_column: str, master_model) -> None:
    rows = db.query(model).filter(getattr(model, new_column).is_(None)).all()
    for row in rows:
        master_row = get_or_create(db, master_model, getattr(row, old_column))
        if master_row is not None:
            setattr(row, new_column, master_row.id)


def migrate_free_text_to_master(db: Session) -> None:
    """One-time-per-row backfill of the new *_id FK columns from the old
    free-text columns. Only rows whose new column is still NULL are
    touched, so this is safe to call on every startup: once a row has its
    FK set, it's never looked at again."""
    _migrate_column(db, PrebuiltTestCase, "service_name", "service_id", Service)
    _migrate_column(db, PrebuiltTestCase, "simulate", "simulate_id", Simulate)
    _migrate_column(db, PrebuiltTestCase, "test_type", "test_type_id", TestType)
    _migrate_column(db, TestCase, "test_type", "test_type_id", TestType)
    _migrate_column(db, TestCase, "test_priority", "test_priority_id", TestPriority)
    db.commit()


def migrate_testcase_tester_to_user(db: Session) -> None:
    """One-time-per-row backfill of TestCase.tester_id from the existing
    free-text tester column. Kept separate from migrate_free_text_to_master
    / _migrate_column above: those assume a bare (id, name) master model,
    but User also needs `type` set on creation, which get_or_create's
    extra_fields now supports directly.

    Gated on `tester_migrated` rather than `tester_id IS NULL`: unlike the
    *_id columns _migrate_column backfills, tester_id is user-editable after
    the fact (Section 1's edit form lets someone clear it back to blank).
    Gating on tester_id being NULL would silently restore the old free-text
    value from the still-untouched `tester` column on every app restart,
    undoing a deliberate edit. tester_migrated is set on every row this
    function considers, whether or not a match was found, so each row is
    looked at at most once, ever.
    """
    rows = db.query(TestCase).filter(TestCase.tester_migrated.isnot(True)).all()
    for row in rows:
        if row.tester_id is None:
            user = get_or_create(db, User, row.tester, type=UserType.TESTER)
            if user is not None:
                row.tester_id = user.id
        row.tester_migrated = True
    db.commit()


def _pick_survivor(rows: list, capitalize: bool):
    """Of a group of rows whose names collide case-insensitively, keeps the
    one already closest to the wanted display form (or the lowest id, as a
    deterministic tie-break) and returns (survivor, the rest). `capitalize`
    forces the survivor's own name to str.capitalize() ("HIGH" -> "High")
    regardless of which variant it started as — only right for TestType/
    TestPriority, whose values are short display words; Service/Simulate/
    Label names can be kebab-case identifiers or intentionally-cased
    phrases ("API Testing") that capitalize() would mangle, so those keep
    whichever existing spelling wins the sort, untouched."""
    ordered = sorted(rows, key=lambda row: (row.name != row.name.capitalize(), row.id))
    survivor, others = ordered[0], ordered[1:]
    if capitalize:
        survivor.name = survivor.name.capitalize()
    return survivor, others


def _reassign_fk(db: Session, ref_model, fk_column: str, old_ids: set[int], new_id: int) -> None:
    column = getattr(ref_model, fk_column)
    for row in db.query(ref_model).filter(column.in_(old_ids)).all():
        setattr(row, fk_column, new_id)


def _merge_label_group(db: Session, survivor: Label, others: list[Label]) -> None:
    """Same idea as _reassign_fk, but LabelAssignment has a UNIQUE(label_id,
    attach_type, attach_id) — if the surviving label is already attached to
    something a duplicate was also attached to, reassigning would collide,
    so the duplicate's (now-redundant) assignment is dropped instead."""
    other_ids = {row.id for row in others}
    for assignment in db.query(LabelAssignment).filter(LabelAssignment.label_id.in_(other_ids)).all():
        collides = db.query(LabelAssignment).filter(
            LabelAssignment.label_id == survivor.id,
            LabelAssignment.attach_type == assignment.attach_type,
            LabelAssignment.attach_id == assignment.attach_id,
        ).first()
        if collides:
            db.delete(assignment)
        else:
            assignment.label_id = survivor.id
    for row in others:
        db.delete(row)


def merge_duplicate_names(db: Session) -> None:
    """One-time cleanup for rows that differ only by letter case (e.g. both
    "HIGH" and "High" existing as separate rows) — the result of every
    create/rename/import path comparing names case-sensitively before
    get_or_create and the settings routes were fixed to match
    case-insensitively. Groups each table's rows by lower(name), and for
    any group bigger than one: reassigns every FK reference from the
    losers onto one surviving row, then deletes the losers. Safe on every
    startup — a table with no case-collision has nothing to do.

    User is deliberately left out: two rows named "Alex Kim" differing
    only by case could be two different real people, and silently merging
    identities is a materially riskier call than merging a dropdown
    option, so that stays a manual (Settings > Users) decision.
    """
    plans = [
        (TestType, [(PrebuiltTestCase, "test_type_id"), (TestCase, "test_type_id")], True),
        (TestPriority, [(TestCase, "test_priority_id")], True),
        (Service, [(PrebuiltTestCase, "service_id")], False),
        (Simulate, [(PrebuiltTestCase, "simulate_id")], False),
    ]
    for model, fk_targets, capitalize in plans:
        groups: dict[str, list] = {}
        for row in db.query(model).all():
            groups.setdefault(row.name.lower(), []).append(row)
        for rows in groups.values():
            if len(rows) < 2:
                continue
            survivor, others = _pick_survivor(rows, capitalize)
            other_ids = {row.id for row in others}
            for ref_model, fk_column in fk_targets:
                _reassign_fk(db, ref_model, fk_column, other_ids, survivor.id)
            for row in others:
                db.delete(row)

    label_groups: dict[str, list] = {}
    for row in db.query(Label).all():
        label_groups.setdefault(row.name.lower(), []).append(row)
    for rows in label_groups.values():
        if len(rows) < 2:
            continue
        survivor, others = _pick_survivor(rows, capitalize=False)
        _merge_label_group(db, survivor, others)

    db.commit()
