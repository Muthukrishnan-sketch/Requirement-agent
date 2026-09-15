"""
Database engine and session management.

Reads DATABASE_URL from the environment. Defaults to a local SQLite file so
the prototype runs with zero external setup; point DATABASE_URL at Postgres
(e.g. Supabase) for anything beyond local development:

    DATABASE_URL=postgresql+psycopg2://user:password@host:5432/dbname

Never hard-code credentials here - they must come from the environment
(.env file, which is git-ignored, or real environment variables in
production).
"""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./recruitment.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: yields a session and guarantees it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Context manager for use outside FastAPI (e.g. inside MCP tools)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
