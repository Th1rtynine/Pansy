"""SQLite connection setup and initialization of a new database."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import load_paths
from app.models import Base


def create_db_engine() -> Engine:
    paths = load_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.covers_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{paths.database.as_posix()}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db() -> Engine:
    """Create missing tables; existing tables are left unchanged."""
    engine = create_db_engine()
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide one session: commit on success, roll back on failure, always close.
    `expire_on_commit` 关着,否则块里读过的属性出了块就失效 —— 页面渲染正是在块外读的。
    """
    engine = create_db_engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

