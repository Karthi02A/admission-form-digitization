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


# Document-level analytics are best-effort: a PostgreSQL issue must never
# interrupt admission uploads or AI extraction.
def record_document_upload(
    *,
    document_id: str,
    batch_id: str,
    visitor_id: str | None,
    session_id: str | None,
    file_type: str,
    file_size_bytes: int,
    upload_status: str,
    error_message: str | None = None,
) -> None:
    from app.analytics.database import SessionLocal
    from app.analytics.models import DocumentUsage
    import uuid

    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        db.add(DocumentUsage(
            usage_id=str(uuid.uuid4()),
            document_id=document_id,
            batch_id=batch_id,
            visitor_id=visitor_id,
            session_id=session_id,
            file_type=(file_type or "unknown")[:20],
            file_size_bytes=max(0, int(file_size_bytes or 0)),
            upload_status=upload_status,
            extraction_status="pending" if upload_status == "success" else "not_started",
            uploaded_at=datetime.now(timezone.utc),
            error_message=(error_message or "")[:1000] or None,
        ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def update_document_extraction(
    *,
    document_id: str,
    extraction_status: str,
    extraction_duration_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    from app.analytics.database import SessionLocal
    from app.analytics.models import DocumentUsage

    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        row = db.query(DocumentUsage).filter(
            DocumentUsage.document_id == document_id
        ).first()
        if row is not None:
            row.extraction_status = extraction_status
            row.extracted_at = datetime.now(timezone.utc)
            row.extraction_duration_ms = (
                max(0, int(extraction_duration_ms))
                if extraction_duration_ms is not None else None
            )
            row.error_message = (error_message or "")[:1000] or None
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
