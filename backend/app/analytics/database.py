
import logging
import os
from collections.abc import Generator

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# Load environment variables from the backend .env file
load_dotenv()


class Base(DeclarativeBase):
    pass


def _database_url() -> str | None:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        return None

    # Render may provide either postgres:// or postgresql:// URLs.
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+psycopg://", 1)
    elif value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)

    return value


DATABASE_URL = _database_url()

engine = (
    create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
        pool_recycle=1800,
    )
    if DATABASE_URL
    else None
)

SessionLocal = (
    sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    if engine
    else None
)


def initialize_database() -> bool:
    """Create analytics tables without making the core app depend on PostgreSQL."""

    if engine is None:
        logger.warning(
            "Analytics database is not configured; usage tracking is disabled"
        )
        return False

    try:
        # Import models so their tables are registered with Base.metadata.
        from app.analytics import models  # noqa: F401

        Base.metadata.create_all(bind=engine)

        logger.info("Analytics database tables are ready")
        return True

    except Exception:
        logger.exception("Could not initialize the analytics database")
        return False


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise HTTPException(
            status_code=503,
            detail="Usage tracking is not configured on this server",
        )

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
