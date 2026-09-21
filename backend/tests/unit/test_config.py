import base64

import pytest
from pydantic import SecretStr, ValidationError

from app.config import PLACEHOLDER_SECRET_KEY, Settings, get_settings
from tests.conftest import make_settings


def test_valid_settings_load() -> None:
    settings = make_settings()
    assert settings.winnow_env == "development"
    assert settings.docs_enabled
    assert len(settings.encryption_key_bytes) == 32


def test_placeholder_secret_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        make_settings(secret_key=PLACEHOLDER_SECRET_KEY)


def test_short_secret_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        make_settings(secret_key="x" * 31)


def test_secret_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="secret_key"):
        Settings(encryption_key=SecretStr(base64.b64encode(bytes(32)).decode()))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("not base64!", "must be base64"),
        (base64.b64encode(bytes(16)).decode(), "exactly 32 bytes"),
        ("base64-32-bytes", "must be base64"),
    ],
)
def test_bad_encryption_key_is_rejected(value: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make_settings(encryption_key=value)


def test_database_url_must_be_async_postgres() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        make_settings(database_url="postgresql://winnow:winnow@db:5432/winnow")


def test_redis_url_scheme_is_checked() -> None:
    with pytest.raises(ValidationError, match="redis://"):
        make_settings(redis_url="http://redis:6379")


def test_production_requires_https_public_url() -> None:
    with pytest.raises(ValidationError, match="https in production"):
        make_settings(winnow_env="production", public_url="http://winnow.example.org")


def test_production_disables_docs() -> None:
    settings = make_settings(winnow_env="production", public_url="https://winnow.example.org")
    assert settings.is_production
    assert not settings.docs_enabled


def test_empty_environment_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_BUCKET", "")
    monkeypatch.setenv("MAX_UPLOAD_MB", "")
    settings = make_settings()
    assert settings.s3_bucket is None
    assert settings.max_upload_mb == 200


def test_values_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WINNOW_SINGLE_USER", "true")
    monkeypatch.setenv("REGISTRATION", "invite_only")
    settings = make_settings()
    assert settings.winnow_single_user
    assert settings.registration == "invite_only"


def test_secrets_are_masked_in_repr() -> None:
    settings = make_settings()
    assert settings.secret_key.get_secret_value() not in repr(settings)
    assert settings.encryption_key.get_secret_value() not in repr(settings)


def test_get_settings_reads_environment_once() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
