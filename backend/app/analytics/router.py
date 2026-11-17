import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analytics.database import get_db
from app.analytics.schemas import SessionHeartbeat, SessionIdentity
from app.analytics.service import record_heartbeat, start_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Usage analytics"])


@router.post("/session/start")
def create_or_resume_session(
    payload: SessionIdentity,
    db: Session = Depends(get_db),
):
    try:
        return start_session(db, payload)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not start analytics session")
        raise HTTPException(status_code=503, detail="Usage tracking is temporarily unavailable") from exc


@router.post("/session/heartbeat")
def session_heartbeat(
    payload: SessionHeartbeat,
    db: Session = Depends(get_db),
):
    try:
        return record_heartbeat(db, payload)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not record analytics heartbeat")
        raise HTTPException(status_code=503, detail="Usage tracking is temporarily unavailable") from exc
