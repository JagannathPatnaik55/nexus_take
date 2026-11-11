"""Engine construction and safe session lifecycle."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from nexus.database.models import Base


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> Engine:
    options: dict = {"pool_pre_ping": True, "future": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **options)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    return engine


def get_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def initialize_local_schema(database_url: str) -> None:
    if database_url.startswith("sqlite"):
        Base.metadata.create_all(get_engine(database_url))


def database_health(database_url: str) -> tuple[bool, str]:
    try:
        with get_engine(database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "Connected"
    except Exception as exc:
        return False, f"Connection failed: {exc.__class__.__name__}"

