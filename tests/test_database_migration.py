"""ensure_columns / backfill_column: the lightweight migration helpers used
on startup so an existing qa_toolbox.db picks up new columns without losing
data already on disk (create_all() never alters a table that already exists).
"""
import os
import tempfile

from sqlalchemy import create_engine

from app.database import backfill_column, ensure_columns, migrate_table


def _make_engine():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE widgets (id INTEGER PRIMARY KEY, category VARCHAR(64))")
        conn.exec_driver_sql("INSERT INTO widgets (id, category) VALUES (1, 'legacy value')")
        conn.commit()
    return engine, db_path


def test_ensure_columns_adds_only_missing_columns():
    engine, db_path = _make_engine()
    try:
        import app.database as dbmod
        original = dbmod.engine
        dbmod.engine = engine
        try:
            ensure_columns("widgets", {"category": "VARCHAR(64)", "service_name": "VARCHAR(64)"})
        finally:
            dbmod.engine = original

        with engine.connect() as conn:
            cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(widgets)")]
            assert "service_name" in cols
            row = conn.exec_driver_sql("SELECT category FROM widgets WHERE id = 1").fetchone()
            assert row[0] == "legacy value", "existing data must survive an additive migration"
    finally:
        engine.dispose()
        os.remove(db_path)


def test_backfill_column_copies_only_into_empty_destinations():
    engine, db_path = _make_engine()
    try:
        import app.database as dbmod
        original = dbmod.engine
        dbmod.engine = engine
        try:
            ensure_columns("widgets", {"service_name": "VARCHAR(64)"})
            with engine.connect() as conn:
                conn.exec_driver_sql("INSERT INTO widgets (id, category, service_name) VALUES (2, 'ignored', 'already set')")
                conn.commit()
            backfill_column("widgets", dest="service_name", src="category")
        finally:
            dbmod.engine = original

        with engine.connect() as conn:
            rows = dict(conn.exec_driver_sql("SELECT id, service_name FROM widgets").fetchall())
        assert rows[1] == "legacy value"
        assert rows[2] == "already set", "backfill must not clobber a value the new column already has"
    finally:
        engine.dispose()
        os.remove(db_path)


def test_migrate_table_copies_rows_and_drops_the_source():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE old_gadgets (id INTEGER PRIMARY KEY, label VARCHAR(64))")
        conn.exec_driver_sql("INSERT INTO old_gadgets (id, label) VALUES (1, 'thing one')")
        conn.exec_driver_sql("INSERT INTO old_gadgets (id, label) VALUES (2, 'thing two')")
        conn.exec_driver_sql("CREATE TABLE new_gadgets (id INTEGER PRIMARY KEY, name VARCHAR(64), note TEXT)")
        conn.commit()

    try:
        import app.database as dbmod
        original = dbmod.engine
        dbmod.engine = engine
        try:
            migrate_table("new_gadgets", "old_gadgets", {"id": "id", "name": "label", "note": "NULL"})
        finally:
            dbmod.engine = original

        with engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT id, name, note FROM new_gadgets ORDER BY id").fetchall()
            assert rows == [(1, "thing one", None), (2, "thing two", None)]
            tables = {row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
            assert "old_gadgets" not in tables, "source table should be dropped after a successful migration"

            # A second call must be a no-op: dest already has rows, and the source is gone.
            migrate_table("new_gadgets", "old_gadgets", {"id": "id", "name": "label", "note": "NULL"})
            count = conn.exec_driver_sql("SELECT count(*) FROM new_gadgets").scalar()
            assert count == 2, "re-running the migration must not duplicate rows"
    finally:
        engine.dispose()
        os.remove(db_path)
