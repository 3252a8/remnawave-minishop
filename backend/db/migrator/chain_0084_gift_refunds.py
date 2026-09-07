"""Ledger support for administrator-initiated paid gift refunds."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0084_add_gift_refund_ledger_kind(connection: Connection) -> None:
    connection.execute(
        text(
            "ALTER TABLE user_balance_ledger_entries DROP CONSTRAINT IF EXISTS ck_user_balance_ledger_kind"
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE user_balance_ledger_entries
            ADD CONSTRAINT ck_user_balance_ledger_kind CHECK (
                kind IN ('payment_topup', 'payment_topup_reversal', 'admin_adjustment',
                'checkout_spend', 'checkout_spend_release', 'gift_refund',
                'partner_conversion_in', 'partner_conversion_out')
            )
            """
        )
    )


CHAIN_0084_GIFT_REFUNDS: list[Migration] = [
    Migration(
        id="0084_add_gift_refund_ledger_kind",
        description="Allow paid gift refunds in the user balance ledger",
        upgrade=_migration_0084_add_gift_refund_ledger_kind,
    )
]
