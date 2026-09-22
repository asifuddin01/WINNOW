"""The permission table (guide 7), the keyword pattern subset (12.3) and page cursors."""

import pytest

from app.models import ProjectMember, ProjectRole
from app.security.patterns import PatternError, check_pattern
from app.security.permissions import Capability, allows, can
from app.services.errors import InvalidCursorError
from app.services.pagination import decode_cursor, encode_cursor

# Guide 7, as a table: who may do what.
MATRIX: dict[Capability, set[ProjectRole]] = {
    Capability.VIEW: {
        ProjectRole.VIEWER,
        ProjectRole.REVIEWER,
        ProjectRole.ADMIN,
        ProjectRole.OWNER,
    },
    Capability.SCREEN: {ProjectRole.REVIEWER, ProjectRole.ADMIN, ProjectRole.OWNER},
    Capability.SEE_OTHERS_WHILE_BLIND: {ProjectRole.ADMIN, ProjectRole.OWNER},
    Capability.RESOLVE_CONFLICTS: {ProjectRole.ADMIN, ProjectRole.OWNER},
    Capability.IMPORT: {ProjectRole.ADMIN, ProjectRole.OWNER},
    Capability.EDIT_SETUP: {ProjectRole.ADMIN, ProjectRole.OWNER},
    Capability.MANAGE_MEMBERS: {ProjectRole.ADMIN, ProjectRole.OWNER},
    Capability.EDIT_SETTINGS: {ProjectRole.ADMIN, ProjectRole.OWNER},
    Capability.EXPORT: {
        ProjectRole.VIEWER,
        ProjectRole.REVIEWER,
        ProjectRole.ADMIN,
        ProjectRole.OWNER,
    },
    Capability.DELETE_PROJECT: {ProjectRole.OWNER},
}


def member(role: ProjectRole, *, can_resolve_conflicts: bool = False) -> ProjectMember:
    return ProjectMember(role=role, can_resolve_conflicts=can_resolve_conflicts)


@pytest.mark.parametrize("capability", list(Capability))
@pytest.mark.parametrize("role", list(ProjectRole))
def test_the_table_matches_the_guide(capability: Capability, role: ProjectRole) -> None:
    assert can(member(role), capability) is (role in MATRIX[capability])


def test_every_capability_is_in_the_table() -> None:
    assert set(MATRIX) == set(Capability)


def test_a_trusted_reviewer_may_resolve_conflicts_but_nothing_more() -> None:
    trusted = member(ProjectRole.REVIEWER, can_resolve_conflicts=True)
    assert can(trusted, Capability.RESOLVE_CONFLICTS)
    assert not can(trusted, Capability.EDIT_SETUP)
    # The flag never lifts a viewer, who does not screen at all.
    assert not can(
        member(ProjectRole.VIEWER, can_resolve_conflicts=True), Capability.RESOLVE_CONFLICTS
    )


def test_allows_compares_ranks() -> None:
    assert allows(member(ProjectRole.OWNER), ProjectRole.ADMIN)
    assert allows(member(ProjectRole.ADMIN), ProjectRole.ADMIN)
    assert not allows(member(ProjectRole.REVIEWER), ProjectRole.ADMIN)
    assert allows(member(ProjectRole.REVIEWER), ProjectRole.VIEWER)


@pytest.mark.parametrize(
    "pattern",
    [
        "randomi[sz]ed",
        "colou?r",
        r"\bRCTs?\b",
        "rand(om|omi[sz]ed)",
        "(?:cat|dog)s?",
        "meta-?analys[ie]s",
        r"\(pilot\)",
        "a{2,5}",
        r"[A-Z]\d+",
    ],
)
def test_useful_patterns_are_allowed(pattern: str) -> None:
    check_pattern(pattern)


@pytest.mark.parametrize(
    "pattern",
    [
        "(a+)+",  # catastrophic backtracking
        r"(\w+\s?)*",
        "(cat|dog)+",
        "(?=lookahead)",
        "(?i)case",
        r"\1",  # backreference
        r"\p{L}",
        r"\x41",
        "a{1000}",
        "a*",  # matches empty text
        "[",
        "[]",
        "x]",
        "(unclosed",
        "**",
        "x\\",
    ],
)
def test_risky_or_unsupported_patterns_are_refused(pattern: str) -> None:
    with pytest.raises(PatternError):
        check_pattern(pattern)


def test_cursors_round_trip_and_reject_rubbish() -> None:
    cursor = encode_cursor("2026-09-22T10:00:00+00:00", "0192f0c1-0000-7000-8000-000000000001")
    assert decode_cursor(cursor, 2) == [
        "2026-09-22T10:00:00+00:00",
        "0192f0c1-0000-7000-8000-000000000001",
    ]
    for bad in ("not-base64!", encode_cursor("only-one"), ""):
        with pytest.raises(InvalidCursorError):
            decode_cursor(bad, 2)
