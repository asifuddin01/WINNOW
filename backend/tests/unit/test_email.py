import smtplib
from unittest import mock

import pytest
from pydantic import SecretStr

from app.email import mailer, messages
from app.email.messages import Email
from tests.conftest import make_settings


def test_messages_carry_their_links() -> None:
    assert (
        "https://w/verify/abc" in messages.verify_email("a@b.c", "Ada", "https://w/verify/abc").body
    )
    assert (
        "https://w/reset/xyz" in messages.reset_password("a@b.c", "Ada", "https://w/reset/xyz").body
    )
    assert "15 minutes" in messages.account_locked("a@b.c", "Ada", 15, "https://w/forgot").body
    assert "turned off" in messages.two_factor_changed("a@b.c", "Ada", enabled=False).subject
    assert "already has one" in messages.account_exists("a@b.c", "Ada", "https://w/forgot").body
    assert "changed" in messages.password_changed("a@b.c", "Ada").body


@pytest.mark.parametrize(
    ("tls", "smtp_class"), [("starttls", "SMTP"), ("none", "SMTP"), ("ssl", "SMTP_SSL")]
)
def test_deliver_speaks_smtp(tls: str, smtp_class: str) -> None:
    settings = make_settings(
        smtp_host="mail.example.org",
        smtp_port=2525,
        smtp_tls=tls,
        smtp_user="winnow",
        smtp_password=SecretStr("pw"),
    )
    with mock.patch.object(smtplib, smtp_class) as smtp:
        mailer.deliver(settings, Email("ada@example.org", "Hello", "Body"))
    connection = smtp.return_value
    assert connection.starttls.called is (tls == "starttls")
    connection.login.assert_called_once_with("winnow", "pw")
    sent = connection.send_message.call_args.args[0]
    assert sent["To"] == "ada@example.org"
    assert sent["Subject"] == "Hello"


def test_deliver_without_smtp_drops_the_message(caplog: pytest.LogCaptureFixture) -> None:
    with mock.patch.object(smtplib, "SMTP") as smtp:
        mailer.deliver(make_settings(), Email("ada@example.org", "Hello", "secret-link"))
    smtp.assert_not_called()
    assert "secret-link" not in caplog.text


async def test_unconfigured_mailer_never_logs_the_body(caplog: pytest.LogCaptureFixture) -> None:
    await mailer.UnconfiguredMailer().send(
        Email("ada@example.org", "Reset", "https://w/reset/secret")
    )
    assert "secret" not in caplog.text


async def test_queue_mailer_enqueues_the_job() -> None:
    queue = mock.AsyncMock()
    await mailer.QueueMailer(queue).send(Email("ada@example.org", "Hi", "Body"))
    queue.enqueue_job.assert_awaited_once_with("send_email", "ada@example.org", "Hi", "Body")
