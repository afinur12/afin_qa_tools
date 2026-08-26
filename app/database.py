import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("QA_TOOLBOX_DB_URL", "sqlite:///./qa_toolbox.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns(table: str, columns: dict[str, str]) -> None:
    """Add any of `columns` (name -> SQL type) missing from `table`.

    create_all() only creates tables that don't exist yet; it never alters
    ones that do, so a schema addition on an existing qa_toolbox.db needs
    this instead.
    """
    with engine.connect() as conn:
        existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
        for name, sql_type in columns.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
        conn.commit()


def backfill_column(table: str, dest: str, src: str) -> None:
    """One-time copy of `src` into `dest` (where `dest` is still empty).

    Used right after a rename via ensure_columns(): the old column is left
    in place (SQLite can't drop columns easily) and its values are copied
    across, so renaming a field doesn't lose data already on disk.
    """
    with engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
        if src in cols and dest in cols:
            conn.exec_driver_sql(f"UPDATE {table} SET {dest} = {src} WHERE {dest} IS NULL AND {src} IS NOT NULL")
            conn.commit()


def migrate_table(dest_table: str, source_table: str, column_exprs: dict[str, str]) -> None:
    """One-time row copy from `source_table` into a brand-new `dest_table`.

    Used when a model is replaced outright (not just a renamed column) —
    e.g. CurlCollection -> Note. `column_exprs` maps each destination
    column to a SQL expression over the source table's columns (a plain
    column name, or a literal like "'TEXT'" / "NULL"). Only runs once: if
    `dest_table` already has rows, it's a no-op. The now-redundant source
    table is dropped after a successful copy.
    """
    with engine.connect() as conn:
        tables = {row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        if source_table not in tables or dest_table not in tables:
            return
        if conn.exec_driver_sql(f"SELECT count(*) FROM {dest_table}").scalar():
            return
        if not conn.exec_driver_sql(f"SELECT count(*) FROM {source_table}").scalar():
            return
        dest_cols = ", ".join(column_exprs.keys())
        src_exprs = ", ".join(column_exprs.values())
        conn.exec_driver_sql(f"INSERT INTO {dest_table} ({dest_cols}) SELECT {src_exprs} FROM {source_table}")
        conn.exec_driver_sql(f"DROP TABLE {source_table}")
        conn.commit()
