"""Passwords, TOTP, recovery codes, encryption, tokens, CSRF tokens and UUIDv7."""

import time
import uuid

import pyotp
import pytest
from cryptography.exceptions import InvalidTag

from app.models.base import uuid7
from app.security import crypto, csrf, totp
from app.security.passwords import Passwords
from app.security.tokens import hash_token, new_token
from tests.conftest import PRODUCTION_ARGON2, make_settings

KEY = bytes(range(32))


async def test_production_hashes_are_argon2id_with_guide_parameters() -> None:
    passwords = Passwords(make_settings(**PRODUCTION_ARGON2))
    hashed = await passwords.hash("correct horse battery staple")
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=1$")
    assert await passwords.verify(hashed, "correct horse battery staple")
    assert not await passwords.verify(hashed, "wrong horse battery staple")


async def test_weaker_hashes_are_flagged_for_rehash() -> None:
    weak = await Passwords(make_settings()).hash("correct horse battery staple")
    assert Passwords(make_settings(**PRODUCTION_ARGON2)).needs_rehash(weak)
    assert not Passwords(make_settings()).needs_rehash(weak)


async def test_garbage_hash_fails_closed() -> None:
    passwords = Passwords(make_settings())
    assert not await passwords.verify("not-a-hash", "anything")
    await passwords.burn_time("anything")  # never raises


def test_totp_accepts_the_current_code_and_its_neighbours() -> None:
    secret = totp.new_secret()
    now = 1_800_000_000
    otp = pyotp.TOTP(secret)
    current = int(now // 30)
    assert totp.matching_step(secret, otp.at(now), None, now) == current
    assert totp.matching_step(secret, otp.at(now - 30), None, now) == current - 1
    assert totp.matching_step(secret, otp.at(now + 30), None, now) == current + 1
    assert totp.matching_step(secret, otp.at(now - 90), None, now) is None


def test_totp_rejects_replay_and_malformed_codes() -> None:
    secret = totp.new_secret()
    now = 1_800_000_000
    code = pyotp.TOTP(secret).at(now)
    step = totp.matching_step(secret, code, None, now)
    assert step is not None
    assert totp.matching_step(secret, code, step, now) is None  # same code, same window
    assert totp.matching_step(secret, "12345", None, now) is None
    assert totp.matching_step(secret, "abcdef", None, now) is None
    assert totp.matching_step(secret, f"{code[:3]} {code[3:]}", None, now) == step


def test_provisioning_uri_and_qr_code() -> None:
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXP", "ada@example.org")
    assert uri.startswith("otpauth://totp/Winnow:ada%40example.org?")
    assert "issuer=Winnow" in uri
    assert totp.qr_data_uri(uri).startswith("data:image/svg+xml;base64,")


def test_recovery_codes() -> None:
    codes = totp.new_recovery_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    for code in codes:
        assert len(code) == 11
        assert code[5] == "-"
        assert set(code.replace("-", "")) <= set(totp.RECOVERY_ALPHABET)
    code = codes[0]
    assert totp.hash_recovery_code(KEY, code) == totp.hash_recovery_code(
        KEY, code.upper().replace("-", " ")
    )
    assert totp.hash_recovery_code(KEY, code) != totp.hash_recovery_code(bytes(32), code)
    assert totp.looks_like_recovery_code(code)
    assert not totp.looks_like_recovery_code("123456")


def test_encryption_round_trip_and_binding() -> None:
    owner = uuid.uuid4().bytes
    blob = crypto.encrypt(KEY, b"JBSWY3DPEHPK3PXP", owner)
    assert b"JBSWY3DPEHPK3PXP" not in blob
    assert crypto.decrypt(KEY, blob, owner) == b"JBSWY3DPEHPK3PXP"
    with pytest.raises(InvalidTag):
        crypto.decrypt(KEY, blob, uuid.uuid4().bytes)  # copied onto another user's row
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(InvalidTag):
        crypto.decrypt(KEY, tampered, owner)


def test_tokens_are_long_and_stored_hashed() -> None:
    token = new_token()
    assert len(token) >= 43
    assert hash_token(token) != token
    assert len(hash_token(token)) == 64
    assert new_token() != token


def test_csrf_tokens_are_bound_to_nonce_and_session() -> None:
    nonce = csrf.new_nonce()
    token = csrf.csrf_token(KEY, nonce, "session-a")
    assert csrf.token_is_valid(KEY, nonce, "session-a", token)
    assert not csrf.token_is_valid(KEY, nonce, "session-b", token)
    assert not csrf.token_is_valid(KEY, csrf.new_nonce(), "session-a", token)
    assert not csrf.token_is_valid(bytes(32), nonce, "session-a", token)
    assert not csrf.token_is_valid(KEY, None, "session-a", token)
    assert not csrf.token_is_valid(KEY, nonce, "session-a", None)


def test_uuid7_is_version_7_and_time_ordered() -> None:
    first = uuid7()
    time.sleep(0.002)
    second = uuid7()
    assert first.version == 7
    assert first.variant == uuid.RFC_4122
    assert first < second
    assert abs((first.int >> 80) - time.time_ns() // 1_000_000) < 5_000
