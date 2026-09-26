#!/usr/bin/env python3
"""Instance backups (guide 16.4): encrypted, rotated, and restorable. Python 3 standard
library, `docker compose` and `age` on the host; nothing else.

    python3 ops/backups.py create              # make backup / make prod-backup
    python3 ops/backups.py restore FILE [--yes] # make restore BACKUP=FILE
    python3 ops/backups.py test                 # the restore test CI runs monthly

A backup is one `age`-encrypted tar holding the database (`pg_dump`, custom format), the
uploaded files, the server's env file (secrets included, which is why it is encrypted)
and a manifest. `create` keeps 7 daily, 4 weekly and 6 monthly backups in BACKUP_DIR and
records the newest in Redis, where the admin health page shows it.

Settings, from the environment or the server's env file:
  AGE_RECIPIENT   the public key backups are encrypted to (`age-keygen -y key.txt`)
  AGE_IDENTITY    the private key file, for `restore` only; keep it off the server
  BACKUP_DIR      where backups go (default ./backups)
  COMPOSE_FILE    docker-compose.prod.yml in production (the Makefile sets it)
  AGE, AGE_KEYGEN the age commands, if they are not `age` and `age-keygen` on the PATH

Off-site copies: sync BACKUP_DIR anywhere (rclone, rsync, `aws s3 sync`); every file
in it is encrypted.
"""

import argparse
import contextlib
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "winnow-"
SUFFIX = ".tar.age"
STAMP = "%Y-%m-%dT%H%M%SZ"
LAST_BACKUP_KEY = "winnow:last-backup"  # read by app.services.admin
KEEP = {"daily": 7, "weekly": 4, "monthly": 6}
# The role row-level security runs as (see the RLS migration): roles belong to the whole
# server, so a fresh one must have it before the dump's grants to it can be restored.
APP_ROLE_SQL = (
    "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'winnow_app') THEN "
    "CREATE ROLE winnow_app NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$; "
    "GRANT winnow_app TO CURRENT_USER;"
)


# --- Rotation -----------------------------------------------------------------------------


def stamp_of(path: Path) -> dt.datetime | None:
    name = path.name
    if not (name.startswith(PREFIX) and name.endswith(SUFFIX)):
        return None
    try:
        return dt.datetime.strptime(name[len(PREFIX) : -len(SUFFIX)], STAMP).replace(
            tzinfo=dt.UTC
        )
    except ValueError:
        return None


def to_keep(stamps: Iterable[dt.datetime]) -> set[dt.datetime]:
    """Grandfather-father-son: the newest backup of each of the last 7 days that have
    one, of the last 4 ISO weeks and of the last 6 months."""
    newest_first = sorted(stamps, reverse=True)
    periods = {
        "daily": lambda s: s.date(),
        "weekly": lambda s: s.isocalendar()[:2],
        "monthly": lambda s: (s.year, s.month),
    }
    kept: set[dt.datetime] = set()
    for rule, period in periods.items():
        seen: list[object] = []
        for stamp in newest_first:
            key = period(stamp)
            if key in seen:
                continue
            if len(seen) == KEEP[rule]:
                break
            seen.append(key)
            kept.add(stamp)
    return kept


# --- Plumbing -----------------------------------------------------------------------------


def run(*args: str, stdin: object = None, stdout: object = None) -> str:
    """Run a command in the repository; stop with its message if it fails."""
    done = subprocess.run(
        args, cwd=ROOT, stdin=stdin, stdout=stdout or subprocess.PIPE, check=False
    )
    if done.returncode != 0:
        sys.exit(f"Failed ({done.returncode}): {shlex.join(args)}")
    return done.stdout.decode() if isinstance(done.stdout, bytes) else ""


def compose(*args: str, **kwargs: object) -> str:
    return run("docker", "compose", *args, **kwargs)  # type: ignore[arg-type]


def sql(statement: str) -> str:
    """One statement as the database owner, inside the db container."""
    return compose(
        "exec", "-T", "db", "sh", "-c",
        f'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc {shlex.quote(statement)}',
    ).strip()


def env_file() -> Path:
    return ROOT / os.environ.get("WINNOW_ENV_FILE", ".env")


def setting(name: str, default: str = "") -> str:
    """From the environment, else from the server's env file (so a cron job needs no more
    than `make prod-backup`)."""
    if name in os.environ:
        return os.environ[name]
    if env_file().exists():
        for line in env_file().read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.split(" #")[0].strip().strip("'\"") or default
    return default


def age(*args: str) -> list[str]:
    return [*shlex.split(setting("AGE", "age")), *args]


@contextlib.contextmanager
def workdir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="winnow-backup-") as name:
        path = Path(name)
        path.chmod(0o700)
        yield path


# --- create -------------------------------------------------------------------------------


def create() -> Path:
    recipient = setting("AGE_RECIPIENT")
    if not recipient:
        sys.exit("Set AGE_RECIPIENT to the public key backups are encrypted to (docs/deploy.md).")
    out_dir = (ROOT / setting("BACKUP_DIR", "backups")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.UTC)
    target = out_dir / f"{PREFIX}{now.strftime(STAMP)}{SUFFIX}"

    with workdir() as work:
        with (work / "db.dump").open("wb") as dump:
            compose(
                "exec", "-T", "db", "sh", "-c",
                'pg_dump --format=custom -U "$POSTGRES_USER" "$POSTGRES_DB"',
                stdout=dump,
            )
        with (work / "uploads.tar").open("wb") as files:
            compose(
                "run", "--rm", "--no-deps", "-T", "--entrypoint", "tar", "api",
                "-C", "/data/uploads", "-cf", "-", ".",
                stdout=files,
            )
        manifest = {
            "created_at": now.isoformat(),
            "migration": sql("SELECT version_num FROM alembic_version"),
            "records": int(sql("SELECT count(*) FROM records")),
            "users": int(sql("SELECT count(*) FROM users")),
        }
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
        parts = ["manifest.json", "db.dump", "uploads.tar"]
        if env_file().exists():
            (work / "env").write_bytes(env_file().read_bytes())
            parts.append("env")
        with tarfile.open(work / "backup.tar", "w") as bundle:
            for part in parts:
                bundle.add(work / part, arcname=part)
        run(*age("-r", recipient, "-o", str(target), str(work / "backup.tar")))

    backups = {stamp: path for path in out_dir.iterdir() if (stamp := stamp_of(path))}
    kept = to_keep(backups)
    for stamp, path in backups.items():
        if stamp not in kept:
            path.unlink()
    record = {"at": now.isoformat(), "file": target.name, "size_bytes": target.stat().st_size}
    compose("exec", "-T", "redis", "redis-cli", "SET", LAST_BACKUP_KEY, json.dumps(record))
    print(f"Backed up {manifest['records']:,} records and {manifest['users']:,} people to {target}")
    return target


# --- restore ------------------------------------------------------------------------------


def restore(backup: Path, *, yes: bool) -> dict[str, object]:
    identity = setting("AGE_IDENTITY")
    if not identity:
        sys.exit("Set AGE_IDENTITY to the private key file the backup was encrypted to.")
    with workdir() as work:
        run(*age("-d", "-i", identity, "-o", str(work / "backup.tar"), str(backup)))
        with tarfile.open(work / "backup.tar") as bundle:
            bundle.extractall(work, filter="data")
        manifest = json.loads((work / "manifest.json").read_text())
        print(
            f"Backup of {manifest['created_at']}: {manifest['records']:,} records, "
            f"{manifest['users']:,} people, migration {manifest['migration']}."
        )
        if not yes and input("This replaces the database and files here. Type 'restore': ") != "restore":
            sys.exit("Nothing changed.")

        compose("stop", "api", "worker")
        sql(APP_ROLE_SQL)
        with (work / "db.dump").open("rb") as dump:
            compose(
                "exec", "-T", "db", "sh", "-c",
                'pg_restore --clean --if-exists --no-owner --single-transaction --exit-on-error '
                '-U "$POSTGRES_USER" -d "$POSTGRES_DB"',
                stdin=dump,
            )
        with (work / "uploads.tar").open("rb") as files:
            compose(
                "run", "--rm", "--no-deps", "-T", "--entrypoint", "sh", "api", "-c",
                "find /data/uploads -mindepth 1 -delete && tar -C /data/uploads -xf -",
                stdin=files,
            )
        if (work / "env").exists():
            kept = backup.with_suffix(".env")
            kept.write_bytes((work / "env").read_bytes())
            kept.chmod(0o600)
            print(f"The backed-up env file is in {kept}; compare it with yours, then delete it.")
    # Back up again, and any newer migrations run before the API starts. Only what was
    # stopped: the database and Redis are running, and nothing else needs starting.
    compose("up", "-d", "--wait", "--no-deps", "migrate", "api", "worker")
    records = int(sql("SELECT count(*) FROM records"))
    if records != manifest["records"]:
        sys.exit(f"Restored {records:,} records, but the backup had {manifest['records']:,}.")
    print(f"Restored {records:,} records; the API is up.")
    return manifest


# --- test ---------------------------------------------------------------------------------


def test() -> None:
    """Back up a small review, destroy the stack's data, restore, and check it all came back
    (guide 16.4). Runs as its own compose project, so no other data is touched."""
    os.environ["COMPOSE_PROJECT_NAME"] = "winnow-restoretest"
    os.environ.pop("COMPOSE_FILE", None)
    services = ("db", "redis", "migrate", "api")
    seed = (
        "import asyncio, datetime as d\n"
        "from app.cli import seed_large\n"
        "from app.config import get_settings\n"
        "from app.db import create_engine, create_sessionmaker\n"
        "from app.models import User\n"
        "async def main():\n"
        "    engine = create_engine(get_settings())\n"
        "    async with create_sessionmaker(engine)() as db:\n"
        "        db.add(User(email='restore@example.com', name='Restore test', password_hash='x',"
        " email_verified_at=d.datetime.now(d.UTC)))\n"
        "        await db.commit()\n"
        "    await engine.dispose()\n"
        "    await seed_large('restore@example.com', 2000)\n"
        "asyncio.run(main())\n"
        "open('/data/uploads/restore-test.txt', 'w').write('kept across a restore')\n"
    )
    try:
        compose("up", "-d", "--wait", *services)
        compose("run", "--rm", "--no-deps", "-T", "api", "python", "-c", seed)
        with workdir() as work:
            keygen = shlex.split(os.environ.get("AGE_KEYGEN", "age-keygen"))
            key = work / "key.txt"
            run(*keygen, "-o", str(key))
            recipient = run(*keygen, "-y", str(key)).strip()
            os.environ.update(AGE_RECIPIENT=recipient, AGE_IDENTITY=str(key), BACKUP_DIR=str(work / "out"))
            backup = create()

            compose("down", "--volumes")  # everything gone, as after losing the server
            compose("up", "-d", "--wait", *services)
            manifest = restore(backup, yes=True)

        restored = compose(
            "run", "--rm", "--no-deps", "-T", "--entrypoint", "cat", "api",
            "/data/uploads/restore-test.txt",
        )
        assert restored == "kept across a restore", restored
        assert int(sql("SELECT count(*) FROM users")) == manifest["users"]
        assert sql("SELECT version_num FROM alembic_version") == manifest["migration"]
        print("Restore test passed.")
    finally:
        compose("down", "--volumes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="an encrypted backup of the database and files")
    restore_parser = commands.add_parser("restore", help="replace everything with a backup")
    restore_parser.add_argument("backup", type=Path)
    restore_parser.add_argument("--yes", action="store_true", help="do not ask first")
    commands.add_parser("test", help="back up, destroy, restore and check (CI)")
    args = parser.parse_args()
    if args.command == "create":
        create()
    elif args.command == "restore":
        restore(args.backup.resolve(), yes=args.yes)
    else:
        test()


if __name__ == "__main__":
    main()
