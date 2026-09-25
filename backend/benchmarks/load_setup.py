"""Accounts and a review for the k6 load test (guide 13): many reviewers screening at once.

    python -m benchmarks.load_setup make [--reviewers 50] [--records 20000]
    python -m benchmarks.load_setup clear

`make` creates throwaway accounts (e2e-load-…@example.com) and a review of generated
records (as `make seed-large` makes them) that they all screen, signs each one in, and
writes their sessions to benchmarks/data/load.json for `load/decide.js`. `clear` deletes
the review and the file. The sessions belong to throwaway accounts on a development
instance, and the folder is git-ignored; `make load` runs both around k6.
"""

import argparse
import asyncio
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select

from app.cli import seed_large
from app.config import get_settings
from app.db import create_engine, create_sessionmaker
from app.models import Project, ProjectMember, ProjectRole, User
from app.security.passwords import Passwords
from benchmarks.budgets import Client, settle

OUT = Path(__file__).parent / "data" / "load.json"
PREFIX = "e2e-load-"


async def make(reviewers: int, records: int) -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("The load test runs on development instances only.")
    engine = create_engine(settings)
    sessions = create_sessionmaker(engine)
    passwords = Passwords(settings)
    run = secrets.token_hex(3)
    # Made here, used once to sign in, never shown or kept.
    people = {
        f"{PREFIX}{run}-{n}@example.com": secrets.token_urlsafe(24) for n in range(reviewers + 1)
    }
    owner = next(iter(people))
    try:
        async with sessions() as db:
            for email, password in people.items():
                db.add(
                    User(
                        email=email,
                        name=f"Load reviewer {email.split('-')[-1].split('@')[0]}",
                        password_hash=await passwords.hash(password),
                        email_verified_at=datetime.now(UTC),
                    )
                )
            await db.commit()
        await seed_large(owner, records)
        await settle(engine, "ANALYZE records")
        async with sessions() as db:
            ids = dict(
                (await db.execute(select(User.email, User.id).where(User.email.in_(people))))
                .tuples()
                .all()
            )
            pid = await db.scalar(select(Project.id).where(Project.owner_id == ids[owner]))
            db.add_all(
                ProjectMember(project_id=pid, user_id=ids[email], role=ProjectRole.REVIEWER)
                for email in people
                if email != owner
            )
            await db.commit()

        sessions_out = []
        for email, password in people.items():
            if email == owner:
                continue
            client = Client(settings.public_origin)
            await client.refresh_csrf()
            await client.call("POST", "/auth/login", json={"email": email, "password": password})
            await client.refresh_csrf()
            sessions_out.append(
                {
                    "cookie": client.http.headers["Cookie"],
                    "csrf": client.http.headers["X-CSRF-Token"],
                }
            )
            await client.aclose()
        OUT.write_text(
            json.dumps(
                {"project": str(pid), "origin": settings.public_origin, "reviewers": sessions_out}
            ),
            encoding="utf-8",
        )
        print(f"{reviewers} reviewers and {records:,} records ready in review {pid}.")
    finally:
        await engine.dispose()


async def clear() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    sessions = create_sessionmaker(engine)
    try:
        async with sessions() as db:
            owners = select(User.id).where(User.email.startswith(PREFIX))
            await db.execute(delete(Project).where(Project.owner_id.in_(owners)))
            await db.commit()
        OUT.unlink(missing_ok=True)
        await settle(engine)
        print("Load-test review and sessions removed.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["make", "clear"])
    parser.add_argument("--reviewers", type=int, default=50)
    parser.add_argument("--records", type=int, default=20_000)
    args = parser.parse_args()
    if args.action == "make":
        asyncio.run(make(args.reviewers, args.records))
    else:
        asyncio.run(clear())
