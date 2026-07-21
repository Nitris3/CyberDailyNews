from datetime import date

from ccip.db import Database, build_engine
from ccip.repository import DeliveryRepository


def test_delivery_record_prevents_same_date_and_recipient_set() -> None:
    database = Database(build_engine("sqlite:///:memory:"))
    database.create_schema()
    recipients = ["Second@example.com", "first@example.com"]

    with database.session() as session:
        repository = DeliveryRepository(session)
        assert not repository.was_sent(date(2026, 7, 21), recipients)
        repository.record(date(2026, 7, 21), recipients)

    with database.session() as session:
        repository = DeliveryRepository(session)
        assert repository.was_sent(
            date(2026, 7, 21), ["FIRST@example.com", "second@example.com"]
        )
        assert not repository.was_sent(date(2026, 7, 22), recipients)
        assert not repository.was_sent(date(2026, 7, 21), ["other@example.com"])


def test_delivery_attempt_history_records_status_without_secrets() -> None:
    database = Database(build_engine("sqlite:///:memory:"))
    database.create_schema()

    with database.session() as session:
        DeliveryRepository(session).record_attempt(
            date(2026, 7, 21),
            ["recipient@example.com"],
            status="failed",
            item_count=5,
            detail="Authentication failed",
        )

    with database.session() as session:
        attempts = DeliveryRepository(session).recent_attempts()

    assert attempts[0].status == "failed"
    assert attempts[0].item_count == 5
    assert attempts[0].detail == "Authentication failed"
