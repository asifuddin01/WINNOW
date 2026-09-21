from typing import Literal

from pydantic import BaseModel

CheckState = Literal["ok", "unavailable"]


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessChecks(BaseModel):
    database: CheckState
    redis: CheckState


class Readiness(BaseModel):
    status: Literal["ok"] = "ok"
    checks: ReadinessChecks
