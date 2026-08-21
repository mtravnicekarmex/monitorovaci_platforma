from __future__ import annotations

from datetime import datetime, timedelta, timezone
import smtplib

from monitoring_agent.client import CURRENT_ENDPOINT_KEYS
from monitoring_agent.delivery import (
    DELIVERY_ERROR_DELIVERY_DISABLED,
    DELIVERY_ERROR_RECIPIENT_NOT_ALLOWLISTED,
    DELIVERY_ERROR_REPORT_MISSING,
    DELIVERY_ERROR_TRANSPORT_FAILED,
    DELIVERY_STATUS_CONFIGURATION_ERROR,
    DELIVERY_STATUS_DISABLED,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_NO_DUE_ITEMS,
    DELIVERY_STATUS_SENT,
    OutlookEmailTransport,
    TestDeliveryPolicy as DeliveryPolicy,
    build_test_delivery_envelope,
    deliver_due_test_delivery_intents,
    hash_delivery_recipient,
    send_email_outlook,
)
from monitoring_agent.incident_store import IncidentStateStore, IncidentStoreLimits
from monitoring_agent.incidents import (
    CycleSnapshot,
    EndpointObservationFact,
    evaluate_incident_lifecycle,
)


BASE_TIME = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
TEST_RECIPIENT = "monitoring-test@unit.local"


class RecordingTransport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.envelopes = []

    def send(self, envelope) -> None:
        self.envelopes.append(envelope)
        if self.fail:
            raise RuntimeError(
                r"password=SHOULD_NOT_LEAK Bearer SHOULD_NOT_LEAK C:\Users\tra\.env"
            )


def _cycle(
    sequence: int,
    *,
    payload_status: dict[str, str] | None = None,
) -> CycleSnapshot:
    payload_status = payload_status or {}
    return CycleSnapshot(
        cycle_sequence=sequence,
        observed_at=BASE_TIME + timedelta(seconds=60 * sequence),
        endpoint_observations=tuple(
            EndpointObservationFact(
                endpoint_key=endpoint_key,
                transport_status="success",
                http_status=200,
                payload_status=payload_status.get(endpoint_key, "ok"),
            )
            for endpoint_key in CURRENT_ENDPOINT_KEYS
        ),
    )


def _opened_evaluation():
    return evaluate_incident_lifecycle(
        [
            _cycle(1, payload_status={"system_database": "degraded"}),
            _cycle(2, payload_status={"system_database": "degraded"}),
        ]
    )


def _store_with_pending_outbox(tmp_path) -> IncidentStateStore:
    store = IncidentStateStore(
        tmp_path,
        limits=IncidentStoreLimits(max_delivery_attempts=2, retry_backoff_seconds=30),
    )
    store.apply_evaluation(_opened_evaluation(), now=BASE_TIME)
    return store


def _enabled_policy(recipient: str = TEST_RECIPIENT) -> DeliveryPolicy:
    return DeliveryPolicy(
        enabled=True,
        mode="test",
        test_recipient=recipient,
        allowed_recipient_hashes=(hash_delivery_recipient(recipient),),
    )


def test_disabled_delivery_does_not_claim_or_send(tmp_path):
    store = _store_with_pending_outbox(tmp_path)
    transport = RecordingTransport()

    results = deliver_due_test_delivery_intents(
        store=store,
        reports_by_reference={},
        policy=DeliveryPolicy(),
        transport=transport,
        claim_id="worker-1",
        now=BASE_TIME,
    )

    assert [item.status for item in results] == [DELIVERY_STATUS_DISABLED]
    assert results[0].error_code == DELIVERY_ERROR_DELIVERY_DISABLED
    assert transport.envelopes == []
    outbox_item = store.load().outbox_items[0]
    assert outbox_item.status == "pending"
    assert outbox_item.claim_id is None
    assert outbox_item.attempt_count == 0


def test_enabled_delivery_requires_recipient_allowlist_without_claiming(tmp_path):
    store = _store_with_pending_outbox(tmp_path)
    transport = RecordingTransport()
    policy = DeliveryPolicy(
        enabled=True,
        mode="test",
        test_recipient=TEST_RECIPIENT,
        allowed_recipient_hashes=(hash_delivery_recipient("other@unit.local"),),
    )

    results = deliver_due_test_delivery_intents(
        store=store,
        reports_by_reference={},
        policy=policy,
        transport=transport,
        claim_id="worker-1",
        now=BASE_TIME,
    )

    assert [item.status for item in results] == [DELIVERY_STATUS_CONFIGURATION_ERROR]
    assert results[0].error_code == DELIVERY_ERROR_RECIPIENT_NOT_ALLOWLISTED
    assert transport.envelopes == []
    assert store.load().outbox_items[0].status == "pending"


def test_test_delivery_sends_once_and_marks_outbox_sent(tmp_path):
    store = _store_with_pending_outbox(tmp_path)
    pending = store.load().outbox_items[0]
    transport = RecordingTransport()
    policy = _enabled_policy()

    first = deliver_due_test_delivery_intents(
        store=store,
        reports_by_reference={pending.report_reference: "healthy report body"},
        policy=policy,
        transport=transport,
        claim_id="worker-1",
        now=BASE_TIME,
    )
    second = deliver_due_test_delivery_intents(
        store=store,
        reports_by_reference={pending.report_reference: "healthy report body"},
        policy=policy,
        transport=transport,
        claim_id="worker-1",
        now=BASE_TIME + timedelta(seconds=1),
    )

    assert [item.status for item in first] == [DELIVERY_STATUS_SENT]
    assert first[0].recipient_hash == hash_delivery_recipient(TEST_RECIPIENT)
    assert first[0].attempt_count == 1
    assert [item.status for item in second] == [DELIVERY_STATUS_NO_DUE_ITEMS]
    assert len(transport.envelopes) == 1
    assert store.load().outbox_items[0].status == "sent"
    assert TEST_RECIPIENT not in str(first[0].to_dict())


def test_transport_failure_records_sanitized_retry_state(tmp_path):
    store = _store_with_pending_outbox(tmp_path)
    pending = store.load().outbox_items[0]
    policy = _enabled_policy()

    results = deliver_due_test_delivery_intents(
        store=store,
        reports_by_reference={pending.report_reference: "body"},
        policy=policy,
        transport=RecordingTransport(fail=True),
        claim_id="worker-1",
        now=BASE_TIME,
    )

    assert [item.status for item in results] == [DELIVERY_STATUS_FAILED]
    assert results[0].error_code == DELIVERY_ERROR_TRANSPORT_FAILED
    assert "SHOULD_NOT_LEAK" not in str(results[0].to_dict())
    outbox_item = store.load().outbox_items[0]
    assert outbox_item.status == "pending"
    assert outbox_item.attempt_count == 1
    assert outbox_item.last_error_code == DELIVERY_ERROR_TRANSPORT_FAILED
    assert outbox_item.next_attempt_at == BASE_TIME + timedelta(seconds=30)


def test_missing_report_reference_records_failure_without_sending(tmp_path):
    store = _store_with_pending_outbox(tmp_path)
    transport = RecordingTransport()

    results = deliver_due_test_delivery_intents(
        store=store,
        reports_by_reference={},
        policy=_enabled_policy(),
        transport=transport,
        claim_id="worker-1",
        now=BASE_TIME,
    )

    assert [item.status for item in results] == [DELIVERY_STATUS_FAILED]
    assert results[0].error_code == DELIVERY_ERROR_REPORT_MISSING
    assert transport.envelopes == []
    outbox_item = store.load().outbox_items[0]
    assert outbox_item.status == "pending"
    assert outbox_item.attempt_count == 1
    assert outbox_item.last_error_code == DELIVERY_ERROR_REPORT_MISSING


def test_repeated_failures_reach_dead_letter_by_store_limits(tmp_path):
    store = _store_with_pending_outbox(tmp_path)
    pending = store.load().outbox_items[0]
    policy = _enabled_policy()

    deliver_due_test_delivery_intents(
        store=store,
        reports_by_reference={pending.report_reference: "body"},
        policy=policy,
        transport=RecordingTransport(fail=True),
        claim_id="worker-1",
        now=BASE_TIME,
    )
    second = deliver_due_test_delivery_intents(
        store=store,
        reports_by_reference={pending.report_reference: "body"},
        policy=policy,
        transport=RecordingTransport(fail=True),
        claim_id="worker-1",
        now=BASE_TIME + timedelta(seconds=31),
    )

    assert [item.status for item in second] == [DELIVERY_STATUS_FAILED]
    outbox_item = store.load().outbox_items[0]
    assert outbox_item.status == "dead_letter"
    assert outbox_item.attempt_count == 2


def test_delivery_envelope_redacts_body_and_bounds_subject(tmp_path):
    store = _store_with_pending_outbox(tmp_path)
    pending = store.load().outbox_items[0]
    policy = DeliveryPolicy(
        enabled=True,
        mode="test",
        test_recipient=TEST_RECIPIENT,
        allowed_recipient_hashes=(hash_delivery_recipient(TEST_RECIPIENT),),
        max_subject_chars=40,
        max_body_chars=1_000,
    )

    envelope = build_test_delivery_envelope(
        outbox_item=pending,
        report_text=(
            r"token=SHOULD_NOT_LEAK https://platform.example/path?token=SHOULD_NOT_LEAK "
            r"C:\Users\tra\secret.env private-run-1"
        ),
        policy=policy,
    )

    assert len(envelope.subject) <= 40
    assert len(envelope.body_text) <= 1_000
    assert "SHOULD_NOT_LEAK" not in envelope.body_text
    assert r"C:\Users\tra" not in envelope.body_text
    assert "private-run-1" not in envelope.body_text
    assert "[redacted]" in envelope.body_text
    assert "[redacted-query]" in envelope.body_text
    assert "[redacted-windows-user-path]" in envelope.body_text
    assert "[redacted-private-id]" in envelope.body_text

    truncated = build_test_delivery_envelope(
        outbox_item=pending,
        report_text="body " * 100,
        policy=DeliveryPolicy(
            enabled=True,
            mode="test",
            test_recipient=TEST_RECIPIENT,
            allowed_recipient_hashes=(hash_delivery_recipient(TEST_RECIPIENT),),
            max_body_chars=120,
        ),
    )

    assert len(truncated.body_text) <= 120
    assert (
        "[truncated: monitoring delivery content exceeded configured character limit]"
        in truncated.body_text
    )


def test_send_email_outlook_uses_o_email_o_app_starttls_without_real_network():
    calls = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            calls.append(("enter",))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("exit",))

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self, *, context):
            calls.append(("starttls", bool(context)))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(
                (
                    "send_message",
                    message["From"],
                    message["To"],
                    message["Subject"],
                    message.get_content().strip(),
                )
            )

    send_email_outlook(
        email_receiver=TEST_RECIPIENT,
        subject="Monitoring test",
        body="Sanitized body",
        env={"O_EMAIL": "sender@unit.local", "O_APP": "placeholder-password"},
        smtp_factory=FakeSmtp,
        sleep_func=lambda _: None,
    )

    assert calls[:5] == [
        ("connect", "smtp.office365.com", 587, 30.0),
        ("enter",),
        ("ehlo",),
        ("starttls", True),
        ("ehlo",),
    ]
    assert ("login", "sender@unit.local", "placeholder-password") in calls
    assert (
        "send_message",
        "sender@unit.local",
        TEST_RECIPIENT,
        "Monitoring test",
        "Sanitized body",
    ) in calls


def test_send_email_outlook_keeps_email_app_as_compatibility_fallback():
    calls = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def ehlo(self):
            pass

        def starttls(self, *, context):
            pass

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send_message", message["From"], message["To"]))

    send_email_outlook(
        email_receiver=TEST_RECIPIENT,
        subject="Monitoring test",
        body="Sanitized body",
        env={"EMAIL": "fallback@unit.local", "APP": "fallback-password"},
        smtp_factory=FakeSmtp,
        sleep_func=lambda _: None,
    )

    assert ("login", "fallback@unit.local", "fallback-password") in calls
    assert ("send_message", "fallback@unit.local", TEST_RECIPIENT) in calls


def test_outlook_email_transport_calls_send_email_outlook(monkeypatch, tmp_path):
    sent = []
    envelope = build_test_delivery_envelope(
        outbox_item=_store_with_pending_outbox(tmp_path).load().outbox_items[0],
        report_text="body",
        policy=_enabled_policy(),
    )

    monkeypatch.setattr(
        "monitoring_agent.delivery.send_email_outlook",
        lambda **kwargs: sent.append(kwargs),
    )

    OutlookEmailTransport(sender_alias="Alarm").send(envelope)

    assert sent == [
        {
            "email_receiver": TEST_RECIPIENT,
            "subject": envelope.subject,
            "body": envelope.body_text,
            "sender_alias": "Alarm",
            "is_html": False,
        }
    ]


def test_send_email_outlook_retries_transient_errors():
    attempts = {"count": 0}
    slept = []

    class FlakySmtp:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def ehlo(self):
            pass

        def starttls(self, *, context):
            pass

        def login(self, username, password):
            pass

        def send_message(self, message):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise smtplib.SMTPResponseException(421, b"try later")

    send_email_outlook(
        email_receiver=TEST_RECIPIENT,
        subject="Monitoring test",
        body="Sanitized body",
        env={"O_EMAIL": "sender@unit.local", "O_APP": "placeholder-password"},
        smtp_factory=FlakySmtp,
        sleep_func=lambda delay: slept.append(delay),
    )

    assert attempts["count"] == 2
    assert slept == [5.0]
