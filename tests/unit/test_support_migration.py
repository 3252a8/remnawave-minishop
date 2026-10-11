from sqlalchemy import create_engine, inspect, text

from db.migrator import MIGRATIONS
from db.migrator.chain_0106_support_connector import CHAIN_0106_SUPPORT_CONNECTOR
from db.models import (
    LegacyImportMapping,
    LegacyReferralCode,
    SupportTicket,
    SupportTicketMessage,
    User,
)


def test_support_migration_is_registered_after_existing_revisions():
    ids = [migration.id for migration in MIGRATIONS]

    assert "0024_add_support_tickets" in ids
    assert ids.index("0024_add_support_tickets") > ids.index("0023_add_email_password_auth_fields")
    assert "0025_add_support_notification_timestamps" in ids
    assert ids.index("0025_add_support_notification_timestamps") > ids.index(
        "0024_add_support_tickets"
    )
    assert "0026_add_lifetime_traffic_synced_at" in ids
    assert ids.index("0026_add_lifetime_traffic_synced_at") > ids.index(
        "0025_add_support_notification_timestamps"
    )


def test_support_models_expose_expected_tables():
    assert SupportTicket.__tablename__ == "support_tickets"
    assert SupportTicketMessage.__tablename__ == "support_ticket_messages"
    assert "admin_last_notified_at" in SupportTicket.__table__.columns
    assert "admin_last_emailed_at" in SupportTicket.__table__.columns
    assert "ix_support_tickets_status_last_msg" in {
        index.name for index in SupportTicket.__table__.indexes
    }


def test_connector_migration_upgrades_existing_support_schema_idempotently():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE support_tickets (ticket_id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE support_ticket_messages "
                    "(message_id INTEGER PRIMARY KEY, ticket_id INTEGER)"
                )
            )
            connection.execute(text("INSERT INTO support_tickets (ticket_id) VALUES (1)"))
            migration = CHAIN_0106_SUPPORT_CONNECTOR[0]
            migration.upgrade(connection)
            migration.upgrade(connection)
            assert connection.execute(
                text("SELECT revision, change_cursor FROM support_tickets WHERE ticket_id = 1")
            ).one() == (1, 0)
            assert (
                connection.execute(
                    text("SELECT cursor FROM support_change_clock WHERE id = 1")
                ).scalar_one()
                == 0
            )
            assert {"connector_source", "author_label", "idempotency_key"} <= {
                column["name"]
                for column in inspect(connection).get_columns("support_ticket_messages")
            }
    finally:
        engine.dispose()


def test_user_model_tracks_lifetime_traffic_sync_timestamp():
    assert "lifetime_used_traffic_synced_at" in User.__table__.columns


def test_trial_eligibility_reset_migration_and_model_are_registered():
    ids = [migration.id for migration in MIGRATIONS]

    assert "0033_add_trial_eligibility_reset_marker" in ids
    assert ids.index("0033_add_trial_eligibility_reset_marker") > ids.index(
        "0032_add_telegram_notification_status"
    )
    assert "trial_eligibility_reset_at" in User.__table__.columns


def test_legacy_import_compatibility_migration_and_models_are_registered():
    ids = [migration.id for migration in MIGRATIONS]

    assert "0034_add_legacy_import_compatibility" in ids
    assert ids.index("0034_add_legacy_import_compatibility") > ids.index(
        "0033_add_trial_eligibility_reset_marker"
    )
    assert User.__table__.columns["referral_code"].type.length == 64
    assert LegacyReferralCode.__tablename__ == "legacy_referral_codes"
    assert LegacyImportMapping.__tablename__ == "legacy_import_mappings"
    assert "uq_legacy_referral_source_code" in {
        constraint.name for constraint in LegacyReferralCode.__table__.constraints
    }
