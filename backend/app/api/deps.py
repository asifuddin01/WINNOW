"""Request-scoped dependencies: who is calling, their session, services, and protections."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from arq.connections import ArqRedis
from fastapi import Depends, Path, Request, status
from redis.asyncio import Redis

from app.config import Settings
from app.db import SessionDep
from app.email.mailer import Mailer
from app.errors import ProblemError
from app.llm.providers import Provider
from app.models import ProjectRole, User
from app.redis_client import RedisDep
from app.security import csrf
from app.security.passwords import Passwords
from app.security.permissions import (
    MemberFlag,
    ProjectAccess,
    check_project_role,
    parse_project_id,
)
from app.security.rate_limit import API_PER_USER, Limit, RateLimiter
from app.security.sessions import SESSION_COOKIE, Session, SessionStore, session_key
from app.services.accounts import AccountService
from app.services.audit import Actor
from app.services.conflicts import ConflictService
from app.services.dedup import DedupService
from app.services.errors import NotAuthenticatedError
from app.services.fulltext import FulltextService
from app.services.imports import ImportService
from app.services.llm import LlmService
from app.services.members import MemberService
from app.services.projects import ProjectService
from app.services.ranking import RankingService
from app.services.records import RecordService
from app.services.screening import ScreeningService
from app.services.setup import SetupService
from app.services.two_factor import TwoFactorService
from app.storage import Storage


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_sessions(request: Request) -> SessionStore:
    store: SessionStore = request.app.state.sessions
    return store


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def get_passwords(request: Request) -> Passwords:
    passwords: Passwords = request.app.state.passwords
    return passwords


def get_actor(request: Request) -> Actor:
    return Actor(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionsDep = Annotated[SessionStore, Depends(get_sessions)]
LimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
PasswordsDep = Annotated[Passwords, Depends(get_passwords)]
ActorDep = Annotated[Actor, Depends(get_actor)]


def get_accounts(
    request: Request,
    db: SessionDep,
    settings: SettingsDep,
    passwords: PasswordsDep,
    sessions: SessionsDep,
) -> AccountService:
    mailer: Mailer = request.app.state.mailer
    http: httpx.AsyncClient = request.app.state.http
    return AccountService(db, settings, passwords, mailer, http, sessions)


def get_two_factor(db: SessionDep, settings: SettingsDep) -> TwoFactorService:
    return TwoFactorService(db, settings)


AccountsDep = Annotated[AccountService, Depends(get_accounts)]
TwoFactorDep = Annotated[TwoFactorService, Depends(get_two_factor)]


def _wait_phrase(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} seconds"
    return f"{-(-seconds // 60)} minutes"


async def enforce_limit(
    limiter: RateLimiter, limit: Limit, subject: str, *, record: bool = True
) -> None:
    """Count one hit against `limit` (or only look, with record=False); over it, answer
    429 with Retry-After (guide 12.6)."""
    retry_after = await (limiter.hit if record else limiter.check)(limit, subject)
    if retry_after is not None:
        raise ProblemError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts. Try again in {_wait_phrase(retry_after)}.",
            code="rate_limited",
            headers={"Retry-After": str(retry_after)},
        )


@dataclass(frozen=True, slots=True)
class Authenticated:
    user: User
    session: Session


async def get_authenticated(
    request: Request, db: SessionDep, sessions: SessionsDep, limiter: LimiterDep
) -> Authenticated:
    """The signed-in user, or 401. Also applies the per-user API rate limit."""
    raw = request.cookies.get(SESSION_COOKIE)
    session = await sessions.get(raw) if raw else None
    if session is None:
        raise NotAuthenticatedError
    user = await db.get(User, session.user_id)
    if user is None or user.deleted_at is not None:
        await sessions.delete(session.key, session.user_id)
        raise NotAuthenticatedError
    await enforce_limit(limiter, API_PER_USER, str(user.id))
    return Authenticated(user=user, session=session)


AuthDep = Annotated[Authenticated, Depends(get_authenticated)]


def require_project_role(
    min_role: ProjectRole, *, flag: MemberFlag | None = None
) -> Callable[..., Awaitable[ProjectAccess]]:
    """The dependency on every /projects/{pid} route (guide 7): signed in (401), a member
    of a live project (404 otherwise, whether or not it exists), with at least `min_role`
    or the member flag (403). Routes and services take the project from the result,
    never from the URL."""

    async def dependency(
        pid: Annotated[str, Path(description="Project id")], auth: AuthDep, db: SessionDep
    ) -> ProjectAccess:
        return await check_project_role(db, auth.user, parse_project_id(pid), min_role, flag=flag)

    dependency.__name__ = f"require_project_{min_role.value}"
    return dependency


ViewerAccess = Annotated[ProjectAccess, Depends(require_project_role(ProjectRole.VIEWER))]
ReviewerAccess = Annotated[ProjectAccess, Depends(require_project_role(ProjectRole.REVIEWER))]
AdminAccess = Annotated[ProjectAccess, Depends(require_project_role(ProjectRole.ADMIN))]
OwnerAccess = Annotated[ProjectAccess, Depends(require_project_role(ProjectRole.OWNER))]
# Guide 7: owners and admins resolve conflicts, and so do reviewers trusted with it.
ResolverAccess = Annotated[
    ProjectAccess,
    Depends(require_project_role(ProjectRole.ADMIN, flag="can_resolve_conflicts")),
]


def get_projects(db: SessionDep, settings: SettingsDep) -> ProjectService:
    return ProjectService(db, settings)


def get_members(request: Request, db: SessionDep, settings: SettingsDep) -> MemberService:
    mailer: Mailer = request.app.state.mailer
    return MemberService(db, settings, mailer)


def get_setup(db: SessionDep) -> SetupService:
    return SetupService(db)


def get_imports(request: Request, db: SessionDep, settings: SettingsDep) -> ImportService:
    storage: Storage = request.app.state.storage
    queue: ArqRedis = request.app.state.queue
    return ImportService(db, settings, storage, queue)


ProjectsDep = Annotated[ProjectService, Depends(get_projects)]
MembersDep = Annotated[MemberService, Depends(get_members)]
SetupDep = Annotated[SetupService, Depends(get_setup)]
ImportsDep = Annotated[ImportService, Depends(get_imports)]


def get_records(db: SessionDep, redis: RedisDep) -> RecordService:
    return RecordService(db, redis)


RecordsDep = Annotated[RecordService, Depends(get_records)]


def get_dedup(request: Request, db: SessionDep) -> DedupService:
    queue: ArqRedis = request.app.state.queue
    return DedupService(db, queue)


DedupDep = Annotated[DedupService, Depends(get_dedup)]


def get_screening(request: Request, db: SessionDep) -> ScreeningService:
    queue: ArqRedis = request.app.state.queue
    return ScreeningService(db, queue)


def get_conflicts(request: Request, db: SessionDep) -> ConflictService:
    queue: ArqRedis = request.app.state.queue
    return ConflictService(db, queue)


def get_llm(request: Request, db: SessionDep) -> LlmService:
    provider: Provider | None = request.app.state.llm
    return LlmService(db, provider)


def get_ranking(request: Request, db: SessionDep) -> RankingService:
    queue: ArqRedis = request.app.state.queue
    redis: Redis = request.app.state.redis
    return RankingService(db, queue, redis)


def get_fulltext(request: Request, db: SessionDep, settings: SettingsDep) -> FulltextService:
    state = request.app.state
    return FulltextService(db, settings, state.storage, state.queue, state.redis, state.http)


def get_mailer(request: Request) -> Mailer:
    mailer: Mailer = request.app.state.mailer
    return mailer


ScreeningDep = Annotated[ScreeningService, Depends(get_screening)]
RankingDep = Annotated[RankingService, Depends(get_ranking)]
LlmDep = Annotated[LlmService, Depends(get_llm)]
ConflictsDep = Annotated[ConflictService, Depends(get_conflicts)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]
FulltextDep = Annotated[FulltextService, Depends(get_fulltext)]


def _origin(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


async def verify_csrf(request: Request) -> None:
    """Every write must come from our own origin and carry a valid CSRF token (guide 12.1)."""
    if request.method in csrf.SAFE_METHODS:
        return
    settings: Settings = request.app.state.settings
    origin = request.headers.get("origin") or _origin(request.headers.get("referer", ""))
    if origin != settings.public_origin:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN, "This request did not come from Winnow.", code="csrf_origin"
        )
    raw_session = request.cookies.get(SESSION_COOKIE)
    if not csrf.token_is_valid(
        settings.secret_key.get_secret_value().encode(),
        request.cookies.get(csrf.CSRF_COOKIE),
        session_key(raw_session) if raw_session else None,
        request.headers.get(csrf.CSRF_HEADER),
    ):
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "Your security token is missing or out of date. Reload the page and try again.",
            code="csrf_invalid",
        )
