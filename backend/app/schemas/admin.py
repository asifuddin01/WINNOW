"""The instance administrator's panel (guide 8.18)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr


class AdminUserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    email_verified: bool
    two_factor: bool
    is_instance_admin: bool
    disabled: bool
    reviews: int
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    next_cursor: str | None
    total: int


class Source(BaseModel):
    """A setting's value and where it comes from: set here, or read from the environment."""

    value: Any
    source: Literal["admin", "environment"]


class InstanceSettingsOut(BaseModel):
    # Changeable here.
    registration: Source
    unpaywall_email: Source
    # Read from the environment (.env), shown so the administrator can check them.
    public_url: str
    single_user: bool
    email_configured: bool
    email_from: str
    storage_backend: str
    open_access_lookup: bool
    llm_provider: str
    llm_model: str | None
    llm_configured: bool
    virus_scanner: bool
    max_upload_mb: int
    max_pdf_mb: int
    max_backup_mb: int
    version: str


class InstanceSettingsPatch(BaseModel):
    # "environment" goes back to the value in .env.
    registration: Literal["open", "invite_only", "closed", "environment"] | None = None
    # "" goes back to the value in .env.
    unpaywall_email: EmailStr | Literal[""] | None = None


class QueueHealth(BaseModel):
    waiting: int
    worker_alive: bool
    # From the worker's last health check: jobs done, failed, retried, running.
    worker_report: dict[str, int]


class DiskHealth(BaseModel):
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int


class LastBackup(BaseModel):
    at: datetime
    file: str | None = None
    size_bytes: int | None = None


class HealthOut(BaseModel):
    database_bytes: int
    queue: QueueHealth
    disk: DiskHealth | None
    last_backup: LastBackup | None
    users: int
    reviews: int
    records: int
    version: str
