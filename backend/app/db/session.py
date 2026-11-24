"""Engine and session factory."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base


def make_engine(database_url: str) -> Engine:
    """Create an engine; creates the SQLite file's folder if needed.

    `sqlite://` (no path) gives a private in-memory database shared by all
    sessions of this engine, used by the tests.
    """
    url = make_url(database_url)
    kwargs: dict = {}
    if url.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        if not url.database or url.database == ":memory:":
            kwargs["poolclass"] = StaticPool
        else:
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)

    if url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def init_db(engine: Engine) -> sessionmaker[Session]:
    """Create tables if missing and return a session factory."""
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
