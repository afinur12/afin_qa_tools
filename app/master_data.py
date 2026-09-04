"""Master data: Service, Simulate, and Test Type.

get_or_create() is the single place that resolves a free-text name to a
master row (used by the startup migration below, and by JSON import in
app/testcase_io.py so an imported test_type string that isn't already a
known value gets its own row rather than being rejected).
"""

from sqlalchemy.orm import Session

from app.models import PrebuiltTestCase, Service, Simulate, TestCase, TestType

DEFAULT_TEST_TYPES = ["POSITIVE", "NEGATIVE", "REGRESSION"]
DEFAULT_SIMULATES = ["E2E", "API Testing"]


def get_or_create(db: Session, model, name: str | None):
    """Case-sensitive, trimmed exact match on `name`. None in, None out —
    there's nothing to link a blank value to."""
    name = (name or "").strip()
    if not name:
        return None
    row = db.query(model).filter(model.name == name).first()
    if row is None:
        row = model(name=name)
        db.add(row)
        db.flush()
    return row


def seed_defaults(db: Session) -> None:
    """Insert the default Test Types and Simulate values once, on an empty
    table. From then on they're ordinary rows the user can rename or
    delete freely, so this never runs again once either table has a row."""
    if not db.query(TestType).first():
        for name in DEFAULT_TEST_TYPES:
            db.add(TestType(name=name))
    if not db.query(Simulate).first():
        for name in DEFAULT_SIMULATES:
            db.add(Simulate(name=name))
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
    db.commit()
