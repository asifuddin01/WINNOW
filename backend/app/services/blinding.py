"""Blind mode, decided in one place (guide 8.6).

Every service that could show one reviewer what another decided asks `sees_others`
first. The frontend is told the answer so it can hide controls, but the rule is enforced
here: a blinded caller is never sent another person's decision, reasons or decision
notes, nor a status computed from them.
"""

from app.models import ProjectRole
from app.schemas.projects import ProjectSettings
from app.security.permissions import Capability, ProjectAccess


def settings_of(access: ProjectAccess) -> ProjectSettings:
    return ProjectSettings.model_validate(access.project.settings or {})


def sees_others(access: ProjectAccess) -> bool:
    """Whether this member may see other people's decisions anywhere in the review.

    With blind mode off, everyone may. With it on, only owners and admins may (guide 7),
    and only if they have switched off "Keep me blind too", which is on by default: an
    owner who also screens should not be unblinded by accident.
    """
    if not settings_of(access).blind_mode:
        return True
    return access.can(Capability.SEE_OTHERS_WHILE_BLIND) and not access.member.keep_blind


def can_resolve(access: ProjectAccess) -> bool:
    """Guide 7: owners and admins, and reviewers trusted with `can_resolve_conflicts`."""
    return access.can(Capability.RESOLVE_CONFLICTS)


def screens(access: ProjectAccess, stage: str) -> bool:
    """Whether this member takes part in screening at `stage`."""
    return access.role is not ProjectRole.VIEWER and stage in (access.member.stages or [])
