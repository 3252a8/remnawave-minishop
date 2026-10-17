from typing import Literal

from aiohttp import web
from pydantic import Field

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.services.trial_captcha import (
    CHALLENGE_SECONDS,
    TrialCaptchaError,
    captcha_verified,
    create_trial_challenge,
    verify_trial_challenge,
)
from db.dal import user_dal

from .auth import _require_user_id
from .common import _json_error
from .response_helpers import json_response


class TrialCaptchaBody(HttpBodyModel):
    challenge_id: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]+$")
    answer: str = Field(min_length=1, max_length=32)


class TrialCaptchaResponse(HttpResponseModel):
    ok: Literal[True]
    required: bool
    challenge_id: str | None
    image: str | None
    expires_in_seconds: int


async def trial_captcha_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings = get_settings(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
    try:
        if await captcha_verified(settings, user_id):
            response = TrialCaptchaResponse(
                ok=True, required=False, challenge_id=None, image=None, expires_in_seconds=0
            )
        else:
            challenge = await create_trial_challenge(settings, user_id)
            response = TrialCaptchaResponse(
                ok=True,
                required=True,
                challenge_id=challenge.challenge_id,
                image=challenge.image,
                expires_in_seconds=CHALLENGE_SECONDS,
            )
        return json_response(response.model_dump(), headers={"Cache-Control": "no-store"})
    except TrialCaptchaError as exc:
        return _json_error(exc.status, exc.code, exc.code)


async def trial_captcha_verify_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payload = await parse_body_or_400(request, TrialCaptchaBody)
    settings = get_settings(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
    try:
        await verify_trial_challenge(settings, user_id, payload.challenge_id, payload.answer)
        return json_response({"ok": True}, headers={"Cache-Control": "no-store"})
    except TrialCaptchaError as exc:
        return _json_error(exc.status, exc.code, exc.code)
