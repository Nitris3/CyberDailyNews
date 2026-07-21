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
