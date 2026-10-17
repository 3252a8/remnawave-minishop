"""Short-lived, user-bound trial challenges shared by bot and WebApp processes."""

import base64
import hashlib
import io
import secrets
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from bot.infra.redis import get_redis, redis_key
from config.settings import Settings

CHALLENGE_SECONDS = 180
PROOF_SECONDS = 600


class TrialCaptchaError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass(frozen=True)
class TrialChallenge:
    challenge_id: str
    image: str


def render_challenge(answer: str) -> bytes:
    # Render above display resolution so rotated glyphs retain clean edges.
    scale = 2
    image = Image.new("RGB", (320 * scale, 112 * scale), "#f2f5f0")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=52 * scale)
    for _ in range(90):
        x, y = secrets.randbelow(320 * scale), secrets.randbelow(112 * scale)
        draw.ellipse((x, y, x + scale, y + scale), fill="#c1cdc0")
    for _ in range(7):
        draw.line(
            [(secrets.randbelow(320 * scale), secrets.randbelow(112 * scale)) for _ in range(2)],
            fill="#b3c4b2",
            width=scale,
        )
    for index, character in enumerate(answer):
        glyph = Image.new("RGBA", (80 * scale, 90 * scale))
        ImageDraw.Draw(glyph).text(
            (40 * scale, 45 * scale), character, anchor="mm", font=font, fill="#213c35"
        )
        glyph = glyph.rotate(secrets.randbelow(25) - 12, resample=Image.Resampling.BICUBIC)
        image.paste(
            glyph,
            ((15 + index * 53 + secrets.randbelow(5)) * scale, (6 + secrets.randbelow(11)) * scale),
            glyph,
        )
    # Interference passes through the characters without obscuring their shapes.
    for _ in range(2):
        y = (25 + secrets.randbelow(45)) * scale
        draw.arc(
            (-40 * scale, y - 105 * scale, 360 * scale, y + 35 * scale),
            start=5,
            end=175,
            fill="#8fa88f",
            width=scale,
        )
    image = image.resize((320, 112), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def _client(settings: Settings):
    client = await get_redis(settings)
    if client is None:
        raise TrialCaptchaError("trial_captcha_unavailable", 503)
    return client


async def captcha_verified(settings: Settings, user_id: int) -> bool:
    if not settings.TRIAL_CAPTCHA_ENABLED:
        return True
    try:
        client = await _client(settings)
        return bool(await client.exists(redis_key(settings, "trial-captcha", user_id, "proof")))
    except TrialCaptchaError:
        raise
    except Exception as exc:
        raise TrialCaptchaError("trial_captcha_unavailable", 503) from exc


async def require_trial_captcha(settings: Settings, user_id: int) -> None:
    if not await captcha_verified(settings, user_id):
        raise TrialCaptchaError("trial_captcha_required", 403)


async def _budget(settings: Settings, user_id: int, kind: str, limit: int) -> None:
    client = await _client(settings)
    # INCR and expiry are one operation: crashes cannot leave an immortal counter.
    count = await client.eval(
        "local n=redis.call('INCR',KEYS[1]); "
        "if n==1 then redis.call('EXPIRE',KEYS[1],600) end; return n",
        1,
        redis_key(settings, "trial-captcha", user_id, kind),
    )
    if int(count) > limit:
        raise TrialCaptchaError("trial_captcha_rate_limited", 429)


async def create_trial_challenge(settings: Settings, user_id: int) -> TrialChallenge:
    try:
        await _budget(settings, user_id, "issued", 20)
        client = await _client(settings)
        answer = "".join(str(secrets.randbelow(10)) for _ in range(5))
        challenge_id = secrets.token_hex(16)
        digest = hashlib.sha256(f"{challenge_id}:{answer}".encode()).hexdigest()
        await client.set(
            redis_key(settings, "trial-captcha", user_id, "challenge"),
            f"{challenge_id}:{digest}",
            ex=CHALLENGE_SECONDS,
        )
        image = base64.b64encode(render_challenge(answer)).decode("ascii")
        return TrialChallenge(challenge_id, f"data:image/png;base64,{image}")
    except TrialCaptchaError:
        raise
    except Exception as exc:
        raise TrialCaptchaError("trial_captcha_unavailable", 503) from exc


async def verify_trial_challenge(
    settings: Settings, user_id: int, challenge_id: str, answer: str
) -> None:
    try:
        await _budget(settings, user_id, "attempts", 5)
        client = await _client(settings)
        key = redis_key(settings, "trial-captcha", user_id, "challenge")
        # Compare ID before deleting, so an old tab cannot consume a newer challenge.
        raw = await client.eval(
            "local v=redis.call('GET',KEYS[1]); "
            "if v and string.sub(v,1,32)==ARGV[1] then "
            "redis.call('DEL',KEYS[1]); return v end; return false",
            1,
            key,
            challenge_id,
        )
        if not raw:
            raise TrialCaptchaError("trial_captcha_expired")
        digest = hashlib.sha256(f"{challenge_id}:{answer.strip()}".encode()).hexdigest()
        if not secrets.compare_digest(str(raw), f"{challenge_id}:{digest}"):
            raise TrialCaptchaError("trial_captcha_invalid")
        await client.set(
            redis_key(settings, "trial-captcha", user_id, "proof"), "1", ex=PROOF_SECONDS
        )
    except TrialCaptchaError:
        raise
    except Exception as exc:
        raise TrialCaptchaError("trial_captcha_unavailable", 503) from exc
