"""Operator commands: `create-admin` (guide 16.3) and `seed` (make seed)."""

import argparse
import asyncio
import getpass
import sys

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.email.mailer import UnconfiguredMailer
from app.models import CriterionKind, KeywordKind, Project, ProjectMember, ReviewType, User
from app.redis_client import create_redis
from app.schemas.common import Color
from app.schemas.projects import Pico, ProjectCreate
from app.schemas.setup import CriterionCreate, KeywordGroupCreate, KeywordsCreate, LabelCreate
from app.security.passwords import Passwords
from app.security.permissions import ProjectAccess
from app.security.sessions import SessionStore
from app.services.accounts import AccountService
from app.services.audit import Actor
from app.services.errors import DomainError, NotFoundError
from app.services.projects import ProjectService
from app.services.setup import SetupService


async def create_admin(name: str, email: str, password: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    redis = create_redis(settings)
    try:
        async with create_sessionmaker(engine)() as db, httpx.AsyncClient() as http:
            accounts = AccountService(
                db,
                settings,
                Passwords(settings),
                UnconfiguredMailer(),
                http,
                SessionStore(redis, settings),
            )
            user = await accounts.create_admin(
                name=name,
                email=email,
                password=password,
                actor=Actor(user_agent="cli"),
                only_if_first=False,
            )
            print(f"Created administrator {user.email}.")
    finally:
        await redis.aclose()
        await engine.dispose()


DEMO = ProjectCreate(
    title="Night shifts and sleep quality in nurses",
    review_type=ReviewType.SYSTEMATIC,
    description="A worked example to look around in. Records arrive with the import phase.",
    research_question="Do rotating night shifts affect sleep quality in hospital nurses?",
    pico=Pico(
        population="Hospital nurses",
        intervention="Rotating night shifts",
        comparator="Day shifts only",
        outcome="Sleep quality (PSQI or similar)",
    ),
)
DEMO_CRITERIA: list[tuple[CriterionKind, str]] = [
    (CriterionKind.INCLUSION, "Adults working rotating night shifts"),
    (CriterionKind.INCLUSION, "Measures sleep quality with a validated scale"),
    (CriterionKind.INCLUSION, "Randomised or controlled study design"),
    (CriterionKind.EXCLUSION, "Shift work outside healthcare"),
    (CriterionKind.EXCLUSION, "Case reports, editorials and conference abstracts"),
]
DEMO_KEYWORDS: list[tuple[str, Color, list[str]]] = [
    ("Population", "teal", ["nurses", "nursing staff", "RN"]),
    ("Outcome", "violet", ["sleep quality", "PSQI", "insomnia"]),
]


async def add_demo_review(db: AsyncSession, settings: Settings, user: User) -> Project:
    """The worked example `make seed` installs: a review with criteria, keywords and a label."""
    actor = Actor(user_agent="cli")
    projects = ProjectService(db, settings)
    created = await projects.create(user, DEMO, actor)
    project = await db.get_one(Project, created.id)
    access = ProjectAccess(
        user=user,
        project=project,
        member=await db.get_one(ProjectMember, (project.id, user.id)),
    )
    setup = SetupService(db)
    for kind, text in DEMO_CRITERIA:
        await setup.add_criterion(access, CriterionCreate(kind=kind, text=text), actor)
    for name, color, terms in DEMO_KEYWORDS:
        group = await setup.add_keyword_group(
            access, KeywordGroupCreate(name=name, color=color, kind=KeywordKind.INCLUDE), actor
        )
        await setup.add_keywords(access, KeywordsCreate(group_id=group.id, terms=terms), actor)
    await setup.add_label(access, LabelCreate(name="Key paper", color="green"), actor)
    return project


async def seed(email: str) -> None:
    """A demo review in an existing account, to look around in (guide 16.2)."""
    settings = get_settings()
    if settings.is_production:
        raise DomainError("Seeding is for development instances only.")
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as db:
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                raise NotFoundError(
                    f"No account uses {email}. Create it first (make create-admin)."
                )
            project = await add_demo_review(db, settings, user)
            print(f"Added “{project.title}” to {email}.")
            print(f"{settings.public_origin}/p/{project.id}")
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="create a verified instance administrator")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    demo = commands.add_parser("seed", help="add a demo review to an existing account")
    demo.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    if args.command == "seed":
        try:
            asyncio.run(seed(args.email))
        except DomainError as exc:
            print(exc.detail, file=sys.stderr)
            return 1
        return 0

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Password (12+ characters): ")
        if password != getpass.getpass("Repeat password: "):
            print("The passwords did not match.", file=sys.stderr)
            return 1
    try:
        asyncio.run(create_admin(args.name, args.email, password))
    except DomainError as exc:
        print(exc.detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
