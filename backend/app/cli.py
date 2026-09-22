"""Operator commands: `create-admin` (guide 16.3) and `seed` (make seed)."""

import argparse
import asyncio
import getpass
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.email.mailer import UnconfiguredMailer
from app.models import CriterionKind, KeywordKind, Project, ProjectMember, ReviewType, User
from app.parsers import ParsedRecord
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
from app.workers.imports import copy_records, record_row


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
LARGE_BATCH = 5_000
TITLES = [
    "Rotating night shifts and sleep quality in hospital nurses",
    "Napping strategies for shift workers: a randomised trial",
    "Fatigue, alertness and error rates on long rotations",
    "Melatonin for circadian misalignment in rotating staff",
    "Sleep hygiene education in emergency departments",
]
JOURNALS = [
    "Journal of Advanced Nursing",
    "Sleep Health",
    "Occupational and Environmental Medicine",
    "BMJ Open",
    "Chronobiology International",
]
AUTHORS = ["Smith, Jane A", "Chowdhury, Sara", "Müller, Jürgen", "Okafor, N", "Rahman, M"]
KEYWORDS = [
    ["nurses", "shift work", "sleep quality"],
    ["naps", "alertness", "fatigue"],
    ["circadian rhythm", "melatonin"],
]
ABSTRACT = (
    "Background: rotating night shifts are common in hospitals and may disturb sleep. "
    "Methods: we followed {n} staff for twelve months and measured sleep quality with the "
    "Pittsburgh Sleep Quality Index. Results: cohort {index} showed a small but consistent "
    "difference between day and night rotas. Conclusions: scheduling matters."
)
DEMO_KEYWORDS: list[tuple[str, Color, list[str]]] = [
    ("Population", "teal", ["nurses", "nursing staff", "RN"]),
    ("Outcome", "violet", ["sleep quality", "PSQI", "insomnia"]),
]


def _now() -> datetime:
    return datetime.now(UTC)


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


async def seed_large(email: str, count: int) -> None:
    """A project with `count` generated records, for the budgets in guide 2.2 and 13."""
    settings = get_settings()
    if settings.is_production:
        raise DomainError("Seeding is for development instances only.")
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as db:
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                raise NotFoundError(
                    f"No account uses {email}. Create it first (make create-admin)."
                )
            projects = ProjectService(db, settings)
            created = await projects.create(
                user,
                ProjectCreate(
                    title=f"Performance test ({count:,} records)",
                    review_type=ReviewType.SYSTEMATIC,
                    description="Generated by make seed-large. Delete it when you are done.",
                ),
                Actor(user_agent="cli"),
            )
            project_id = created.id
        started = time.monotonic()
        for batch in range(0, count, LARGE_BATCH):
            size = min(LARGE_BATCH, count - batch)
            await copy_records(
                sessionmaker,
                [_fake_row(project_id, batch + index) for index in range(size)],
            )
            print(f"  {batch + size:,} of {count:,}", end="\r", flush=True)
        print(f"\nSeeded {count:,} records in {time.monotonic() - started:.1f}s.")
        print(f"{settings.public_origin}/p/{project_id}/records")
    finally:
        await engine.dispose()


def _fake_row(project_id: uuid.UUID, index: int) -> tuple[Any, ...]:
    """One believable record: enough words for the search index to have work to do."""
    title = f"{TITLES[index % len(TITLES)]} ({index})"
    record = ParsedRecord(
        title=title,
        abstract=ABSTRACT.format(index=index, n=1000 + index % 900),
        authors=[AUTHORS[index % len(AUTHORS)], AUTHORS[(index + 3) % len(AUTHORS)]],
        year=1990 + index % 35,
        journal=JOURNALS[index % len(JOURNALS)],
        volume=str(10 + index % 60),
        issue=str(1 + index % 4),
        pages=f"{index % 900 + 1}-{index % 900 + 9}",
        doi=f"10.1000/winnow.{index}",
        pmid=str(30000000 + index),
        keywords=KEYWORDS[index % len(KEYWORDS)],
        language="eng",
        publication_type=["Journal Article"],
        raw={},
    )
    return record_row(record, project_id, None, _now())


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
    large = commands.add_parser("seed-large", help="a project with many generated records")
    large.add_argument("--email", required=True)
    large.add_argument("--records", type=int, default=100_000)
    args = parser.parse_args(argv)

    if args.command in {"seed", "seed-large"}:
        try:
            if args.command == "seed":
                asyncio.run(seed(args.email))
            else:
                asyncio.run(seed_large(args.email, args.records))
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
