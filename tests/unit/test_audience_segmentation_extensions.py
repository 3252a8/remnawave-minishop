import unittest
from typing import cast
from unittest.mock import AsyncMock, patch

from sqlalchemy.orm import sessionmaker

from bot.services.audience_segmentation import (
    AudienceDefinition,
    AudienceNotFoundError,
    AudienceProvider,
    AudienceSegmentationService,
    AudienceUnavailableError,
)


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


class _SessionFactory:
    def __call__(self) -> _SessionContext:
        return _SessionContext()


class AudienceSegmentationExtensionsTest(unittest.IsolatedAsyncioTestCase):
    def service(self) -> AudienceSegmentationService:
        return AudienceSegmentationService(cast(sessionmaker, _SessionFactory()))

    async def test_registered_provider_is_discoverable_and_resolves_unique_ids(self) -> None:
        resolve = AsyncMock(return_value=[30, 20, 30])
        service = self.service()
        service.register_provider(
            AudienceProvider(
                target="segment:priority",
                label_key="broadcast_target_priority",
                fallback_label="Priority users",
                resolve_user_ids=resolve,
                order=25,
            )
        )

        self.assertTrue(service.has_target("SEGMENT:PRIORITY"))
        self.assertTrue(service.is_target_available("segment:priority"))
        self.assertEqual(await service.resolve_user_ids("segment:priority"), [30, 20])
        self.assertEqual(
            service.audiences(),
            [
                AudienceDefinition(
                    target="segment:priority",
                    label_key="broadcast_target_priority",
                    fallback_label="Priority users",
                    order=25,
                )
            ],
        )

    async def test_unavailable_provider_is_hidden_and_rejected(self) -> None:
        service = self.service()
        service.register_provider(
            AudienceProvider(
                target="segment:paused",
                label_key="broadcast_target_paused",
                fallback_label="Paused segment",
                resolve_user_ids=AsyncMock(return_value=[1]),
                is_available=lambda: False,
            )
        )

        self.assertTrue(service.has_target("segment:paused"))
        self.assertFalse(service.is_target_available("segment:paused"))
        self.assertEqual(service.audiences(), [])
        with self.assertRaises(AudienceUnavailableError):
            await service.resolve_user_ids("segment:paused")

    async def test_provider_can_remain_discoverable_while_unavailable(self) -> None:
        service = self.service()
        service.register_provider(
            AudienceProvider(
                target="segment:licensed",
                label_key="broadcast_target_licensed",
                fallback_label="Licensed audience",
                resolve_user_ids=AsyncMock(return_value=[1]),
                is_available=lambda: False,
                visible_when_unavailable=True,
                group_label_key="broadcast_audience_group_extensions",
                group_fallback_label="Extensions",
            )
        )

        self.assertEqual(
            service.audiences(),
            [
                AudienceDefinition(
                    target="segment:licensed",
                    label_key="broadcast_target_licensed",
                    fallback_label="Licensed audience",
                    order=100,
                    available=False,
                    group_label_key="broadcast_audience_group_extensions",
                    group_fallback_label="Extensions",
                )
            ],
        )
        with self.assertRaises(AudienceUnavailableError):
            await service.resolve_user_ids("segment:licensed")

    async def test_unknown_provider_does_not_fall_back_to_all_users(self) -> None:
        with self.assertRaises(AudienceNotFoundError):
            await self.service().resolve_user_ids("segment:missing")

    def test_reserved_and_duplicate_targets_are_rejected(self) -> None:
        provider = AudienceProvider(
            target="segment:priority",
            label_key="broadcast_target_priority",
            fallback_label="Priority users",
            resolve_user_ids=AsyncMock(return_value=[]),
        )
        service = self.service()
        service.register_provider(provider)
        with self.assertRaises(ValueError):
            service.register_provider(provider)
        with self.assertRaises(ValueError):
            service.register_provider(
                AudienceProvider(
                    target="all",
                    label_key="broadcast_target_override",
                    fallback_label="Override",
                    resolve_user_ids=AsyncMock(return_value=[]),
                )
            )

    async def test_provider_count_is_added_without_resolving_ids(self) -> None:
        resolve = AsyncMock(return_value=[1, 2])
        count = AsyncMock(return_value=7)
        service = self.service()
        service.register_provider(
            AudienceProvider(
                target="segment:priority",
                label_key="broadcast_target_priority",
                fallback_label="Priority users",
                resolve_user_ids=resolve,
                count=count,
            )
        )

        with (
            patch(
                "bot.services.audience_segmentation.user_dal.count_all_active_users_for_broadcast",
                AsyncMock(return_value=10),
            ),
            patch(
                "bot.services.audience_segmentation.user_dal.count_users_with_active_subscription_for_broadcast",
                AsyncMock(return_value=8),
            ),
            patch(
                "bot.services.audience_segmentation.user_dal.count_users_without_active_subscription_for_broadcast",
                AsyncMock(return_value=2),
            ),
            patch(
                "bot.services.audience_segmentation.user_dal.count_users_with_expired_subscription_for_broadcast",
                AsyncMock(return_value=1),
            ),
            patch(
                "bot.services.audience_segmentation.user_dal.count_users_without_any_subscription_for_broadcast",
                AsyncMock(return_value=1),
            ),
        ):
            counts = await service.counts()

        self.assertEqual(counts["segment:priority"], 7)
        count.assert_awaited_once()
        resolve.assert_not_awaited()
