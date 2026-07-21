from sqlalchemy import select

from ccip.db import CURRENT_SCHEMA_VERSION, Database, SchemaVersionRecord, build_engine


def test_database_records_current_schema_version() -> None:
    database = Database(build_engine("sqlite:///:memory:"))

    database.create_schema()

    with database.session() as session:
        version = session.scalar(select(SchemaVersionRecord.version))
    assert version == CURRENT_SCHEMA_VERSION
