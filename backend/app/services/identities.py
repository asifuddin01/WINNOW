"""Outside accounts linked to a Winnow account: Google, and ORCID iDs.

Google links itself by its verified email (app.services.google_accounts). ORCID shares no
email, so only the signed-in owner of an account links an iD to it, and a sign-in with an
iD nobody linked goes no further (docs/decisions.md).
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserIdentity
from app.security.orcid import PROVIDER as ORCID
from app.services import audit
from app.services.audit import Actor


class OrcidTakenError(Exception):
    """The iD is already linked to another Winnow account."""


async def linked(db: AsyncSession, user: User) -> dict[str, str]:
    """Provider → the person's id there, for every outside account linked to `user`."""
    rows = await db.execute(
        select(UserIdentity.provider, UserIdentity.subject).where(UserIdentity.user_id == user.id)
    )
    return dict(rows.tuples().all())


async def user_for_orcid(db: AsyncSession, orcid: str) -> User | None:
    user: User | None = await db.scalar(
        select(User)
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(
            UserIdentity.provider == ORCID,
            UserIdentity.subject == orcid,
            User.deleted_at.is_(None),
        )
    )
    return user


async def link_orcid(db: AsyncSession, user: User, orcid: str, actor: Actor) -> None:
    """Link `orcid` to `user`, in place of any iD linked before."""
    owner = await db.scalar(
        select(UserIdentity.user_id).where(
            UserIdentity.provider == ORCID, UserIdentity.subject == orcid
        )
    )
    if owner == user.id:
        return
    if owner is not None:
        raise OrcidTakenError
    await db.execute(
        delete(UserIdentity).where(UserIdentity.user_id == user.id, UserIdentity.provider == ORCID)
    )
    # ORCID shares no email address; the column holds the provider's, so it stays empty.
    db.add(UserIdentity(user_id=user.id, provider=ORCID, subject=orcid, email=""))
    audit.record(
        db,
        "auth.identity.linked",
        actor,
        user_id=user.id,
        after={"provider": ORCID, "orcid": orcid},
    )
    await db.flush()


async def unlink_orcid(db: AsyncSession, user: User, actor: Actor) -> None:
    orcid = await db.scalar(
        delete(UserIdentity)
        .where(UserIdentity.user_id == user.id, UserIdentity.provider == ORCID)
        .returning(UserIdentity.subject)
    )
    if orcid is not None:
        audit.record(
            db,
            "auth.identity.unlinked",
            actor,
            user_id=user.id,
            before={"provider": ORCID, "orcid": orcid},
        )
