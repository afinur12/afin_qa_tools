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
