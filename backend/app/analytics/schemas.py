from uuid import UUID

from pydantic import BaseModel, Field


class SessionIdentity(BaseModel):
    visitor_id: UUID
    session_id: UUID


class SessionHeartbeat(SessionIdentity):
    # The browser sends active time in small increments. Limit each request
    # so a faulty client cannot add an unreasonable amount of time at once.
    active_seconds: int = Field(ge=0, le=60)
