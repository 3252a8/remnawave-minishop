import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from bot.services import account_roles


@pytest.mark.parametrize(
    "actor,target,roles,others,allowed",
    [
        (1, 1, [], 2, False),
        (1, 2, [False], 0, True),
        (1, 2, [True, False], 2, False),
        (1, 2, [True, True], 0, False),
        (1, 2, [True, True], 1, True),
    ],
)
def test_owner_ban_policy(
    actor: int, target: int, roles: list[bool], others: int, allowed: bool
) -> None:
    session = AsyncMock()
    session.scalar.return_value = others
    with patch.object(account_roles, "has_role", AsyncMock(side_effect=roles)):
        assert asyncio.run(account_roles.can_ban_account(session, actor, target)) is allowed
    assert "pg_advisory_xact_lock" in str(session.execute.call_args.args[0])
