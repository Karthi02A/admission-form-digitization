from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.analytics.models import UserSession, Visitor
from app.analytics.schemas import SessionHeartbeat, SessionIdentity


def start_session(db: Session, payload: SessionIdentity) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    visitor_id = str(payload.visitor_id)
    session_id = str(payload.session_id)

    visitor_insert = insert(Visitor).values(
        visitor_id=visitor_id,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.execute(
        visitor_insert.on_conflict_do_update(
            index_elements=[Visitor.visitor_id],
            set_={"last_seen_at": now},
        )
    )

    session_insert = insert(UserSession).values(
        session_id=session_id,
        visitor_id=visitor_id,
        started_at=now,
        last_activity_at=now,
        active_seconds=0,
    )
    db.execute(
        session_insert.on_conflict_do_nothing(index_elements=[UserSession.session_id])
    )

    session = db.get(UserSession, session_id)
    if session is None or session.visitor_id != visitor_id:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invalid analytics session")

    session.last_activity_at = now
    db.commit()
    return {"status": "started"}


def record_heartbeat(db: Session, payload: SessionHeartbeat) -> dict[str, int | str]:
    now = datetime.now(timezone.utc)
    visitor_id = str(payload.visitor_id)
    session_id = str(payload.session_id)

    result = db.execute(
        update(UserSession)
        .where(
            UserSession.session_id == session_id,
            UserSession.visitor_id == visitor_id,
        )
        .values(
            active_seconds=UserSession.active_seconds + payload.active_seconds,
            last_activity_at=now,
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="Analytics session not found")

    db.execute(
        update(Visitor)
        .where(Visitor.visitor_id == visitor_id)
        .values(last_seen_at=now)
    )
    db.commit()
    return {"status": "recorded", "active_seconds": payload.active_seconds}
