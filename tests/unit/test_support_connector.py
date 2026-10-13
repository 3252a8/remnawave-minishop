"""Persistent connector behavior, including retry after a committed send."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.support_connector_contracts import SupportConnectorConflict
from bot.services.support_service import SupportService, TicketNotFound
from db.activity_models import SupportChangeClock
from db.dal import support_dal
from db.models import Base, Payment, Subscription, SupportTicket, SupportTicketMessage, User
from tests.support.settings_stub import settings_stub


def scenario(run: Callable[[Any, SupportService, int], Awaitable[None]]) -> None:
    async def execute() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            async with factory() as session:
                session.add_all([User(user_id=1, email="private@example.test"), User(user_id=2)])
                session.add(SupportChangeClock(id=1, cursor=0))
                await session.flush()
                ticket = await support_dal.create_ticket(
                    session, 1, "Help", "other", "normal", "Question"
                )
                await session.commit()
            service = SupportService(
                factory, settings_stub(SUPPORT_TICKETS_ENABLED=True), None, None
            )
            service.notification_service.notify_support_admin_reply = AsyncMock()
            service._schedule_notification = lambda coroutine, *_args: coroutine.close()
            await run(factory, service, int(ticket.ticket_id))
        finally:
            await engine.dispose()

    asyncio.run(execute())


async def send(service: SupportService, ticket_id: int, revision: int = 1):
    return await service.reply_from_connector(
        ticket_id,
        "Approved answer",
        expected_user_id=1,
        expected_revision=revision,
        idempotency_key="job-1",
        source="example.connector",
        author_label="Automated support",
    )


def test_context_is_owner_scoped_and_excludes_notes_contacts_and_admin_read_side_effects() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            await support_dal.add_message(
                session, ticket_id, "admin", 2, "Private note", is_internal_note=True
            )
            await session.commit()
        context = await service.get_ticket_context(ticket_id, expected_user_id=1)
        assert [message.body for message in context.messages] == ["Question"]
        assert context.revision == 2
        assert not {"user_id", "name", "email", "username", "telegram_id"} & context.facts.keys()
        async with factory() as session:
            ticket = await session.get(SupportTicket, ticket_id)
            assert ticket is not None and ticket.unread_admin_count == 1
        with pytest.raises(TicketNotFound):
            await service.get_ticket_context(ticket_id, expected_user_id=2)

    scenario(run)


def test_committed_retry_keeps_original_reply_and_operator_unread() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        first = await send(service, ticket_id)
        second = await send(service, ticket_id)
        assert first.message_id == second.message_id and second.duplicate
        assert not first.duplicate and first.revision == 2
        async with factory() as session:
            ticket = await session.get(SupportTicket, ticket_id)
            message = await session.get(SupportTicketMessage, first.message_id)
            assert ticket is not None and ticket.unread_admin_count == 1
            assert ticket.unread_user_count == 1
            assert message is not None and message.author_user_id is None
            assert message.author_role == "connector"
            assert message.connector_source == "example.connector"
            count = await session.scalar(select(func.count()).select_from(SupportTicketMessage))
            assert count == 2
        with pytest.raises(SupportConnectorConflict, match="idempotency_mismatch"):
            await service.reply_from_connector(
                ticket_id,
                "Different answer",
                expected_user_id=1,
                expected_revision=1,
                idempotency_key="job-1",
                source="example.connector",
                author_label="Automated support",
            )

    scenario(run)


@pytest.mark.parametrize(
    "mutation", ["user_message", "admin_message", "internal_note", "closed", "assigned"]
)
def test_every_competing_conversation_write_invalidates_pending_reply(mutation: str) -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            if mutation in {"closed", "assigned"}:
                await support_dal.update_ticket(
                    session,
                    ticket_id,
                    **({"status": "closed"} if mutation == "closed" else {"assigned_admin_id": 2}),
                )
            else:
                await support_dal.add_message(
                    session,
                    ticket_id,
                    "user" if mutation == "user_message" else "admin",
                    1 if mutation == "user_message" else 2,
                    "Changed",
                    is_internal_note=mutation == "internal_note",
                )
            await session.commit()
        with pytest.raises(SupportConnectorConflict, match="stale_revision"):
            await send(service, ticket_id)

    scenario(run)


def test_banned_owner_is_rejected_before_any_external_reply() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            user = await session.get(User, 1)
            assert user is not None
            user.is_banned = True
            await session.commit()
        with pytest.raises(SupportConnectorConflict, match="owner_unavailable"):
            await send(service, ticket_id)

    scenario(run)


def test_reconciliation_has_bounded_pages_and_rollback_does_not_advance_watermark() -> None:
    async def run(factory: Any, _service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            assert await support_dal.get_change_cursor(session) == 1
            await support_dal.add_message(session, ticket_id, "user", 1, "Rolled back")
            await session.rollback()
            assert await support_dal.get_change_cursor(session) == 1
            second = await support_dal.create_ticket(
                session, 2, "Help", "other", "normal", "Second"
            )
            await session.commit()
            page = await support_dal.list_changed_tickets(session, limit=1)
            assert len(page) == 1 and page[0].cursor == 1
            following = await support_dal.list_changed_tickets(session, after_cursor=page[0].cursor)
            assert len(following) == 1 and following[0].ticket_id == second.ticket_id
            assert following[0].last_message_id > 0
            with pytest.raises(ValueError):
                await support_dal.list_changed_tickets(session, limit=501)

    scenario(run)


def test_connector_buttons_are_stored_and_part_of_idempotent_payload() -> None:
    from bot.plugins.support_connector import MessageButtonInput
    from bot.services.support_message_buttons import support_buttons_payload

    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        options = {
            "expected_user_id": 1,
            "expected_revision": 1,
            "idempotency_key": "buttons-job",
            "source": "example.connector",
            "author_label": "Automated support",
        }
        buttons = [
            MessageButtonInput(kind="url", label="Instructions", url="https://example.test/help")
        ]
        first = await service.reply_from_connector(
            ticket_id, "Answer with instructions", buttons=buttons, **options
        )
        retry = await service.reply_from_connector(
            ticket_id, "Answer with instructions", buttons=buttons, **options
        )
        assert retry.duplicate and first.message_id == retry.message_id
        async with factory() as session:
            message = await session.get(SupportTicketMessage, first.message_id)
            assert message is not None
            assert support_buttons_payload(message.buttons)[0]["url"] == "https://example.test/help"
        with pytest.raises(SupportConnectorConflict, match="idempotency_mismatch"):
            await service.reply_from_connector(
                ticket_id, "Answer with instructions", buttons=[], **options
            )

    scenario(run)


def test_device_projection_keeps_hwid_and_does_not_invent_last_connection() -> None:
    from bot.services.support_connector_diagnostics import project_panel_diagnostics

    result = project_panel_diagnostics(
        {"status": "ACTIVE"},
        [
            {
                "hwid": "test-device",
                "deviceModel": "Phone",
                "platform": "iOS",
                "userAgent": "Example client",
                "updatedAt": "2026-10-13T11:00:00Z",
            }
        ],
    )
    assert result["last_connected_at"] is None
    assert result["last_server"] is None
    devices = result["devices"]
    assert isinstance(devices, list) and isinstance(devices[0], dict)
    assert devices[0]["hwid"] == "test-device"


def test_context_uses_current_panel_binding_and_only_owner_payment_statuses() -> None:
    from bot.services import support_connector_service

    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        async with factory() as session:
            user = await session.get(User, 1)
            assert user is not None
            user.panel_user_uuid = "current-panel-account"
            session.add(
                Subscription(
                    user_id=1,
                    panel_user_uuid="previous-panel-account",
                    install_share_token="a" * 32,
                    is_active=True,
                    end_date=datetime.now(UTC) + timedelta(days=30),
                )
            )
            session.add_all(
                [
                    Payment(user_id=1, amount=100, currency="RUB", status="pending"),
                    Payment(user_id=1, amount=200, currency="RUB", status="succeeded"),
                    Payment(user_id=2, amount=900, currency="RUB", status="succeeded"),
                ]
            )
            await session.commit()
        with patch.object(
            support_connector_service,
            "connection_diagnostics",
            AsyncMock(return_value={"panel_source": "unavailable"}),
        ):
            context = await service.get_ticket_context(ticket_id, expected_user_id=1)
        assert context.facts["installation_url"] is None
        assert context.facts["subscription_active"] is False
        assert context.facts["payment_status_counts"] == {"pending": 1, "succeeded": 1}
        payments = context.facts["payments"]
        assert isinstance(payments, list) and len(payments) == 2
        assert all(item["amount"] != 900 for item in payments)

    scenario(run)


def test_download_links_prefer_resolved_customer_configuration_to_stock_defaults() -> None:
    from bot.services import support_connector_diagnostics as diagnostics
    from config.subscription_guides_config import default_subscription_guides_config_text

    async def run() -> None:
        config = json.loads(default_subscription_guides_config_text())
        for platform in config["platforms"].values():
            for app in platform["apps"]:
                for block in app["blocks"]:
                    for button in block["buttons"]:
                        if button["type"] == "external":
                            button["link"] = "https://apps.example.test/configured-download"
        panel = MagicMock()
        panel.__aenter__ = AsyncMock(return_value=panel)
        panel.__aexit__ = AsyncMock()
        panel.get_user_by_uuid = AsyncMock(
            return_value={"uuid": "owner-panel", "shortUuid": "owner-short", "status": "ACTIVE"}
        )
        panel.get_user_devices = AsyncMock(return_value=[])
        panel.get_subscription_page_config_by_short_uuid = AsyncMock(
            return_value={"response": {"config": config}}
        )
        settings = settings_stub(
            PANEL_API_URL="https://panel.example.test",
            PANEL_API_KEY="synthetic",
            SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED=True,
            SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED=False,
        )
        with (
            patch.object(diagnostics, "PanelApiService", return_value=panel),
            patch.object(
                diagnostics,
                "subscription_guides_status",
                return_value={"config": json.loads(default_subscription_guides_config_text())},
            ),
        ):
            result = await diagnostics.connection_diagnostics(settings, "owner-panel", None)
        links = result["download_links"]
        assert isinstance(links, list) and links
        assert all(item["url"] == "https://apps.example.test/configured-download" for item in links)
        panel.get_subscription_page_config_by_short_uuid.assert_awaited_once_with("owner-short")

    asyncio.run(run())


@pytest.mark.parametrize("through_squad", [False, True])
@pytest.mark.parametrize("devices_failed", [False, True])
def test_assigned_panel_guides_use_live_short_id_and_survive_node_lookup_failure(
    through_squad: bool,
    devices_failed: bool,
) -> None:
    from bot.services import support_connector_diagnostics as diagnostics
    from config.subscription_guides_config import default_subscription_guides_config_text

    async def run() -> None:
        config = json.loads(default_subscription_guides_config_text())
        for platform in config["platforms"].values():
            for app in platform["apps"]:
                for block in app["blocks"]:
                    for button in block["buttons"]:
                        if button["type"] == "external":
                            button["link"] = "https://apps.example.test/assigned-download"
        panel = MagicMock()
        panel.__aenter__ = AsyncMock(return_value=panel)
        panel.__aexit__ = AsyncMock()
        panel.get_user_by_uuid = AsyncMock(
            return_value={
                "uuid": "owner-panel",
                "shortUuid": "live-short",
                "externalSquadUuid": "owner-squad",
                "userTraffic": {"lastConnectedNodeUuid": "owner-node"},
            }
        )
        panel.get_user_devices = AsyncMock(
            return_value=[],
            side_effect=RuntimeError("Private device error") if devices_failed else None,
        )
        panel.get_node_summary = AsyncMock(side_effect=RuntimeError("Private upstream detail"))
        panel.get_subscription_page_config_by_short_uuid = AsyncMock(
            return_value={
                "webpageAllowed": True,
                **({} if through_squad else {"subpageConfigUuid": "owner-config"}),
            }
        )
        panel.get_external_squad = AsyncMock(return_value={"subpageConfigUuid": "owner-config"})
        panel.get_subscription_page_config_by_uuid = AsyncMock(return_value={"config": config})
        settings = settings_stub(
            PANEL_API_URL="https://panel.example.test",
            PANEL_API_KEY="synthetic",
            SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED=True,
            SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED=False,
        )
        with (
            patch.object(diagnostics, "PanelApiService", return_value=panel),
            patch.object(diagnostics, "subscription_guides_status", return_value={"config": None}),
        ):
            result = await diagnostics.connection_diagnostics(
                settings, "owner-panel", "stale-short"
            )
        links = result["download_links"]
        assert isinstance(links, list) and links
        assert all(link["url"] == "https://apps.example.test/assigned-download" for link in links)
        assert result["last_server"] is None and result["last_server_uuid"] == "owner-node"
        assert "Private upstream detail" not in str(result)
        assert "Private device error" not in str(result)
        assert result["devices"] is None if devices_failed else result["devices"] == []
        panel.get_subscription_page_config_by_short_uuid.assert_awaited_once_with("live-short")
        panel.get_subscription_page_config_by_uuid.assert_awaited_once_with("owner-config")
        if through_squad:
            panel.get_external_squad.assert_awaited_once_with("owner-squad")
        else:
            panel.get_external_squad.assert_not_awaited()

    asyncio.run(run())


def test_node_directory_summary_excludes_addresses_and_other_nodes() -> None:
    from bot.services.panel_api_service import PanelApiService

    async def run() -> None:
        panel = PanelApiService(
            settings_stub(PANEL_API_URL="https://panel.example.test", PANEL_API_KEY="synthetic")
        )
        panel._request = AsyncMock(
            return_value={
                "response": {
                    "nodes": [
                        {"uuid": "another-node", "name": "Another node", "address": "10.0.0.2"},
                        {
                            "uuid": "owner-node",
                            "name": "Example node",
                            "countryCode": "NL",
                            "address": "10.0.0.1",
                            "apiKey": "PRIVATE-KEY",
                        },
                    ]
                }
            }
        )
        result = await panel.get_node_summary("owner-node")
        assert result == {"uuid": "owner-node", "name": "Example node", "countryCode": "NL"}
        assert "10.0.0" not in str(result) and "PRIVATE-KEY" not in str(result)
        assert await panel.get_node_summary("missing-node") is None

    asyncio.run(run())


def test_readonly_replay_and_account_rebinding_never_create_a_new_message() -> None:
    async def run(factory: Any, service: SupportService, ticket_id: int) -> None:
        context = await service.get_ticket_context(ticket_id, expected_user_id=1)
        binding = context.facts["account_binding"]
        assert isinstance(binding, str)
        with pytest.raises(SupportConnectorConflict, match="reply_not_committed"):
            await service.reply_from_connector(
                ticket_id,
                "Prepared answer",
                expected_user_id=1,
                expected_revision=1,
                idempotency_key="replay-key",
                source="example.connector",
                author_label="Automated support",
                replay_only=True,
            )
        async with factory() as session:
            user = await session.get(User, 1)
            assert user is not None
            user.panel_user_uuid = "rebound-account"
            await session.commit()
        with pytest.raises(SupportConnectorConflict, match="account_binding_changed"):
            await service.reply_from_connector(
                ticket_id,
                "Prepared answer",
                expected_user_id=1,
                expected_revision=1,
                idempotency_key="binding-key",
                source="example.connector",
                author_label="Automated support",
                expected_account_binding=binding,
            )
        first = await send(service, ticket_id)
        retry = await service.reply_from_connector(
            ticket_id,
            "Approved answer",
            expected_user_id=1,
            expected_revision=1,
            idempotency_key="job-1",
            source="example.connector",
            author_label="Automated support",
            replay_only=True,
        )
        assert retry.duplicate and first.message_id == retry.message_id

    scenario(run)
