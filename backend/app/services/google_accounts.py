"""Which Winnow account a Google sign-in belongs to."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import NO_PASSWORD, User, UserIdentity
from app.security.google import PROVIDER, GoogleProfile
from app.services import audit
from app.services.audit import Actor
from app.services.errors import RegistrationClosedError
from app.services.instance import registration_mode


async def user_for_google(
    db: AsyncSession, settings: Settings, profile: GoogleProfile, actor: Actor
) -> User:
    """The account for a verified Google identity, linking or creating one as needed.

    1. An identity already linked: its user.
    2. A Winnow account with the same email: link it. Google has verified the address,
       which proves control of the inbox just as a password-reset link would.
    3. Otherwise a new, already-verified account, if registration is open. It has no
       password until its owner sets one through "forgot password".
    """
    linked = await db.scalar(
        select(User)
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(
            UserIdentity.provider == PROVIDER,
            UserIdentity.subject == profile.subject,
            User.deleted_at.is_(None),
        )
    )
    if linked is not None:
        return linked

    user = await db.scalar(
        select(User).where(User.email == profile.email, User.deleted_at.is_(None))
    )
    if user is None:
        if settings.winnow_single_user or await registration_mode(db, settings) != "open":
            raise RegistrationClosedError
        user = User(
            name=profile.name[:200],
            email=profile.email,
            password_hash=NO_PASSWORD,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        audit.record(db, "auth.register", actor, user_id=user.id, after={"method": PROVIDER})
    elif user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)

    db.add(
        UserIdentity(
            user_id=user.id, provider=PROVIDER, subject=profile.subject, email=profile.email
        )
    )
    audit.record(db, "auth.identity.linked", actor, user_id=user.id, after={"provider": PROVIDER})
    await db.flush()
    return user


async def google_linked(db: AsyncSession, user: User) -> bool:
    found = await db.scalar(
        select(UserIdentity.id).where(
            UserIdentity.user_id == user.id, UserIdentity.provider == PROVIDER
        )
    )
    return found is not None
