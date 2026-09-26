"""Public persistence contract for extension-owned Core resources."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Connection


def bind_promo_code_owners(
    connection: Connection, *, owner_plugin_id: str, assignments: Iterable[tuple[int, int]]
) -> int:
    """Bind existing personal codes to an owner without changing the recipient.

    A plugin migration supplies its own code/recipient pairs. No plugin table
    name or proprietary schema leaks into Core, and mismatches stop migration.
    """
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", owner_plugin_id):
        raise ValueError("invalid_plugin_id")
    count = 0
    for promo_code_id, recipient_user_id in assignments:
        result = connection.execute(
            text(
                """
                UPDATE promo_codes SET owner_plugin_id = :owner
                WHERE promo_code_id = :id AND user_id = :recipient
                  AND (owner_plugin_id IS NULL OR owner_plugin_id = :owner)
                RETURNING promo_code_id
                """
            ),
            {
                "owner": owner_plugin_id,
                "id": int(promo_code_id),
                "recipient": int(recipient_user_id),
            },
        )
        if result.scalar_one_or_none() is None:
            raise ValueError(f"promo_owner_binding_conflict:{promo_code_id}")
        count += 1
    return count
