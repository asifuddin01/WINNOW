"""Who is screening right now (guide 8.17)."""

import uuid

from pydantic import BaseModel

from app.models import ScreeningStage


class PresenceIn(BaseModel):
    stage: ScreeningStage


class PresentMember(BaseModel):
    user_id: uuid.UUID
    name: str
    stage: ScreeningStage
