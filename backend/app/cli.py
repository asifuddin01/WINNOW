"""Operator commands: `python -m app.cli create-admin` (make create-admin, guide 16.3)."""

import argparse
import asyncio
import getpass
import sys

import httpx

from app.config import get_settings
from app.db import create_engine, create_sessionmaker
from app.email.mailer import UnconfiguredMailer
from app.redis_client import create_redis
from app.security.passwords import Passwords
from app.security.sessions import SessionStore
from app.services.accounts import AccountService
from app.services.audit import Actor
from app.services.errors import DomainError


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="create a verified instance administrator")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    args = parser.parse_args(argv)

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
