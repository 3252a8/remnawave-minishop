import hashlib
import unittest
from unittest.mock import AsyncMock, patch

from bot.services import trial_captcha
from config.settings import Settings
from config.settings_trial import TrialSettings
from tests.support.settings_stub import settings_stub


class TrialCaptchaTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_captcha_does_not_require_redis(self) -> None:
        enabled = TrialSettings(_env_file=None).TRIAL_CAPTCHA_ENABLED
        self.assertFalse(enabled)
        with patch.object(trial_captcha, "get_redis", AsyncMock()) as get_redis:
            await trial_captcha.require_trial_captcha(self.settings(enabled), 42)
        get_redis.assert_not_awaited()

    def settings(self, enabled: bool = True) -> Settings:
        return settings_stub(TRIAL_CAPTCHA_ENABLED=enabled, REDIS_KEY_PREFIX="captcha-test")

    async def test_disabled_captcha_does_not_require_redis(self) -> None:
        with patch.object(trial_captcha, "get_redis", AsyncMock()) as get_redis:
            await trial_captcha.require_trial_captcha(self.settings(False), 42)
        get_redis.assert_not_awaited()

    async def test_missing_proof_blocks_direct_activation(self) -> None:
        client = AsyncMock()
        client.exists.return_value = 0
        with (
            patch.object(trial_captcha, "get_redis", AsyncMock(return_value=client)),
            self.assertRaises(trial_captcha.TrialCaptchaError) as raised,
        ):
            await trial_captcha.require_trial_captcha(self.settings(), 42)
        self.assertEqual(
            (raised.exception.status, raised.exception.code), (403, "trial_captcha_required")
        )

    async def test_redis_outage_fails_closed(self) -> None:
        with (
            patch.object(trial_captcha, "get_redis", AsyncMock(side_effect=ConnectionError)),
            self.assertRaises(trial_captcha.TrialCaptchaError) as raised,
        ):
            await trial_captcha.require_trial_captcha(self.settings(), 42)
        self.assertEqual(raised.exception.status, 503)

    async def test_correct_answer_grants_short_user_bound_proof(self) -> None:
        challenge_id = "a" * 32
        digest = hashlib.sha256(f"{challenge_id}:73146".encode()).hexdigest()
        client = AsyncMock()
        client.eval.side_effect = [1, f"{challenge_id}:{digest}"]
        with patch.object(trial_captcha, "get_redis", AsyncMock(return_value=client)):
            await trial_captcha.verify_trial_challenge(self.settings(), 42, challenge_id, "73146")
        client.set.assert_awaited_once_with("captcha-test:trial-captcha:42:proof", "1", ex=600)

    async def test_incorrect_answer_and_replay_never_grant_proof(self) -> None:
        client = AsyncMock()
        client.eval.side_effect = [1, "a" * 32 + ":incorrect", 2, None]
        with patch.object(trial_captcha, "get_redis", AsyncMock(return_value=client)):
            for code in ("trial_captcha_invalid", "trial_captcha_expired"):
                with self.assertRaises(trial_captcha.TrialCaptchaError) as raised:
                    await trial_captcha.verify_trial_challenge(
                        self.settings(), 42, "a" * 32, "73146"
                    )
                self.assertEqual(raised.exception.code, code)
        client.set.assert_not_awaited()

    async def test_rate_limit_stops_challenge_regeneration(self) -> None:
        client = AsyncMock()
        client.eval.return_value = 21
        with (
            patch.object(trial_captcha, "get_redis", AsyncMock(return_value=client)),
            self.assertRaises(trial_captcha.TrialCaptchaError) as raised,
        ):
            await trial_captcha.create_trial_challenge(self.settings(), 42)
        self.assertEqual(raised.exception.status, 429)
        client.set.assert_not_awaited()
