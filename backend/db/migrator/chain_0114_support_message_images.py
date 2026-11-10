"""Associate additional photos with one support message."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS support_message_images (
                message_id INTEGER NOT NULL
                    REFERENCES support_ticket_messages(message_id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                image_id VARCHAR(32) NOT NULL REFERENCES message_images(image_id) ON DELETE CASCADE,
                PRIMARY KEY (message_id, position)
            )
            """
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_support_message_images_image_id "
            "ON support_message_images (image_id)"
        )
    )


CHAIN_0114_SUPPORT_MESSAGE_IMAGES = [
    Migration("0114_support_message_images", "Attach multiple photos to support messages", _upgrade)
]
