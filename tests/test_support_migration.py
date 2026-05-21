from db.migrator import MIGRATIONS
from db.models import SupportTicket, SupportTicketMessage, User


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


def test_user_model_tracks_lifetime_traffic_sync_timestamp():
    assert "lifetime_used_traffic_synced_at" in User.__table__.columns
