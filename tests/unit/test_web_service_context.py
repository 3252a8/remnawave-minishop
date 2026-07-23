from __future__ import annotations

from typing import cast

from aiogram import Bot
from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.web_server import _inject_shared_instances
from bot.services.audience_segmentation import AudienceSegmentationService
from tests.support.settings_stub import settings_stub


def test_web_app_receives_shared_audience_segmentation_service() -> None:
    app = web.Application()
    audience_service = AudienceSegmentationService(cast(sessionmaker, None))

    _inject_shared_instances(
        app,
        {"audience_segmentation_service": audience_service},
        cast(Bot, None),
        settings_stub(),
        cast(sessionmaker, None),
    )

    assert app["audience_segmentation_service"] is audience_service
