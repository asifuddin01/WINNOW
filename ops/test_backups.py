"""Checks for ops/backups.py's rotation: python3 ops/test_backups.py (CI runs it)."""

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backups import setting, stamp_of, to_keep  # noqa: E402


def nightly(days: int) -> list[dt.datetime]:
    end = dt.datetime(2026, 9, 26, 2, 0, tzinfo=dt.UTC)  # a Saturday
    return [end - dt.timedelta(days=n) for n in range(days)]


def test_a_year_of_nightly_backups_keeps_7_daily_4_weekly_6_monthly() -> None:
    stamps = nightly(365)
    kept = sorted(to_keep(stamps), reverse=True)
    assert kept[:7] == stamps[:7]  # the last seven nights
    weeks = {s.isocalendar()[:2] for s in kept}
    months = {(s.year, s.month) for s in kept}
    assert {s.isocalendar()[:2] for s in stamps[:22]} <= weeks
    assert len(months) == 6 and (2026, 4) in months and (2026, 3) not in months
    # The month's newest backup is its last night: 2026-04-30.
    assert dt.datetime(2026, 4, 30, 2, 0, tzinfo=dt.UTC) in kept
    # The last seven nights (20-26 September) already cover weeks 39 and 38; weeks 37 and
    # 36 add 13 and 6 September; the months add the last night of August back to April.
    assert len(kept) == 7 + 2 + 5


def test_two_backups_in_a_day_keep_the_newer() -> None:
    morning = dt.datetime(2026, 9, 26, 2, 0, tzinfo=dt.UTC)
    evening = morning.replace(hour=20)
    assert to_keep([morning, evening]) == {evening}


def test_only_winnow_backups_are_rotated() -> None:
    assert stamp_of(Path("winnow-2026-09-26T020000Z.tar.age")) == dt.datetime(
        2026, 9, 26, 2, 0, tzinfo=dt.UTC
    )
    assert stamp_of(Path("notes.txt")) is None
    assert stamp_of(Path("winnow-yesterday.tar.age")) is None


def test_settings_come_from_the_environment_or_the_env_file() -> None:
    with tempfile.TemporaryDirectory() as folder:
        env = Path(folder) / "server.env"
        env.write_text("AGE_RECIPIENT=age1abc   # the public key\nBACKUP_DIR='/srv/backups'\n")
        os.environ["WINNOW_ENV_FILE"] = str(env)  # absolute, so ROOT does not matter
        try:
            assert setting("AGE_RECIPIENT") == "age1abc"
            assert setting("BACKUP_DIR", "backups") == "/srv/backups"
            assert setting("NOT_SET", "fallback") == "fallback"
            os.environ["AGE_RECIPIENT"] = "age1env"
            assert setting("AGE_RECIPIENT") == "age1env"  # the environment wins
        finally:
            os.environ.pop("WINNOW_ENV_FILE")
            os.environ.pop("AGE_RECIPIENT", None)


if __name__ == "__main__":
    for name, check in list(globals().items()):
        if name.startswith("test_"):
            check()
    print("Rotation checks passed.")
