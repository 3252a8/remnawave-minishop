import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import security_dal
from db.models import EmailVerificationCode

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class SmtpAttempt:
    port: int
    use_ssl: bool
    starttls: bool


@dataclass(frozen=True)
class EmailCodeRequestResult:
    ok: bool
    error: Optional[str] = None
    retry_after: Optional[int] = None


@dataclass(frozen=True)
class EmailCodeVerifyResult:
    ok: bool
    error: Optional[str] = None
    retry_after: Optional[int] = None


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    email = normalize_email(value)
    return bool(email and len(email) <= 254 and EMAIL_RE.match(email))


def _email_throttle_identifier(email: str, purpose: str, target_user_id: Optional[int]) -> str:
    target_part = "none" if target_user_id is None else str(target_user_id)
    return f"{purpose}:{target_part}:{email}"


class EmailAuthService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _smtp_attempts(self) -> list[SmtpAttempt]:
        attempts: list[SmtpAttempt] = []
        primary_port = int(self.settings.SMTP_PORT)

        for port in self.settings.smtp_ports_to_try:
            if port == primary_port:
                use_ssl = bool(self.settings.SMTP_USE_SSL or port == 465)
                starttls = bool(self.settings.SMTP_STARTTLS and not use_ssl)
            else:
                use_ssl = port == 465
                starttls = bool(self.settings.SMTP_STARTTLS and not use_ssl)
            attempts.append(SmtpAttempt(port=port, use_ssl=use_ssl, starttls=starttls))

        return attempts or [
            SmtpAttempt(
                port=primary_port,
                use_ssl=bool(self.settings.SMTP_USE_SSL or primary_port == 465),
                starttls=bool(
                    self.settings.SMTP_STARTTLS
                    and not self.settings.SMTP_USE_SSL
                    and primary_port != 465
                ),
            )
        ]

    def _hash_code(self, email: str, purpose: str, code: str) -> str:
        secret = hmac.new(
            self.settings.BOT_TOKEN.encode("utf-8"),
            b"remnawave-tg-shop-email-code",
            hashlib.sha256,
        ).digest()
        payload = f"{purpose}:{email}:{code}".encode("utf-8")
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    async def request_code(
        self,
        session: AsyncSession,
        *,
        email: str,
        purpose: str,
        language_code: str,
        target_user_id: Optional[int] = None,
    ) -> EmailCodeRequestResult:
        normalized_email = normalize_email(email)
        if not self.settings.email_auth_configured:
            return EmailCodeRequestResult(ok=False, error="email_auth_not_configured")
        if not is_valid_email(normalized_email):
            return EmailCodeRequestResult(ok=False, error="invalid_email")

        now = datetime.now(timezone.utc)
        throttle = await security_dal.check_throttle(
            session,
            scope=security_dal.EMAIL_CODE_VERIFY_SCOPE,
            identifier=_email_throttle_identifier(normalized_email, purpose, target_user_id),
            now=now,
        )
        if throttle.locked:
            return EmailCodeRequestResult(
                ok=False,
                error="rate_limited",
                retry_after=throttle.retry_after,
            )

        latest_code = await self._get_latest_code(
            session,
            email=normalized_email,
            purpose=purpose,
            target_user_id=target_user_id,
        )
        if latest_code and latest_code.created_at:
            created_at = latest_code.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            resend_after = max(1, int(self.settings.EMAIL_CODE_RESEND_SECONDS))
            elapsed = int((now - created_at).total_seconds())
            if elapsed < resend_after and latest_code.consumed_at is None:
                return EmailCodeRequestResult(
                    ok=False,
                    error="rate_limited",
                    retry_after=resend_after - elapsed,
                )

        await session.execute(
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == normalized_email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.target_user_id == target_user_id,
                EmailVerificationCode.status == "active",
                EmailVerificationCode.consumed_at.is_(None),
            )
            .values(status="superseded")
        )

        code = f"{secrets.randbelow(1_000_000):06d}"
        code_model = EmailVerificationCode(
            email=normalized_email,
            code_hash=self._hash_code(normalized_email, purpose, code),
            purpose=purpose,
            target_user_id=target_user_id,
            expires_at=now + timedelta(seconds=max(60, int(self.settings.EMAIL_CODE_TTL_SECONDS))),
            status="active",
        )
        session.add(code_model)
        await session.flush()

        await self._send_code_email(
            email=normalized_email,
            code=code,
            language_code=language_code,
        )
        return EmailCodeRequestResult(ok=True)

    async def verify_code(
        self,
        session: AsyncSession,
        *,
        email: str,
        purpose: str,
        code: str,
        target_user_id: Optional[int] = None,
    ) -> EmailCodeVerifyResult:
        normalized_email = normalize_email(email)
        normalized_code = re.sub(r"\D", "", code or "")
        if not is_valid_email(normalized_email):
            return EmailCodeVerifyResult(ok=False, error="invalid_code")

        now = datetime.now(timezone.utc)
        throttle_identifier = _email_throttle_identifier(
            normalized_email,
            purpose,
            target_user_id,
        )
        throttle = await security_dal.check_throttle(
            session,
            scope=security_dal.EMAIL_CODE_VERIFY_SCOPE,
            identifier=throttle_identifier,
            now=now,
        )
        if throttle.locked:
            return EmailCodeVerifyResult(
                ok=False,
                error="rate_limited",
                retry_after=throttle.retry_after,
            )

        latest_code = await self._get_latest_code(
            session,
            email=normalized_email,
            purpose=purpose,
            target_user_id=target_user_id,
        )
        if not latest_code or latest_code.consumed_at is not None:
            return EmailCodeVerifyResult(ok=False, error="invalid_code")

        expires_at = latest_code.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            return EmailCodeVerifyResult(ok=False, error="expired_code")

        max_attempts = max(1, int(self.settings.EMAIL_CODE_MAX_ATTEMPTS))
        if int(latest_code.attempts or 0) >= max_attempts:
            return EmailCodeVerifyResult(ok=False, error="too_many_attempts")

        if len(normalized_code) != 6:
            latest_code.attempts = int(latest_code.attempts or 0) + 1
            throttle_result = await security_dal.record_throttle_failure(
                session,
                scope=security_dal.EMAIL_CODE_VERIFY_SCOPE,
                identifier=throttle_identifier,
                max_failures=self.settings.BRUTE_FORCE_MAX_FAILURES,
                window_seconds=self.settings.BRUTE_FORCE_WINDOW_SECONDS,
                lock_seconds=self.settings.BRUTE_FORCE_LOCK_SECONDS,
                now=now,
            )
            await session.flush()
            if throttle_result.locked:
                return EmailCodeVerifyResult(
                    ok=False,
                    error="rate_limited",
                    retry_after=throttle_result.retry_after,
                )
            if int(latest_code.attempts or 0) >= max_attempts:
                return EmailCodeVerifyResult(ok=False, error="too_many_attempts")
            return EmailCodeVerifyResult(ok=False, error="invalid_code")

        expected_hash = self._hash_code(normalized_email, purpose, normalized_code)
        if not hmac.compare_digest(expected_hash, latest_code.code_hash):
            latest_code.attempts = int(latest_code.attempts or 0) + 1
            throttle_result = await security_dal.record_throttle_failure(
                session,
                scope=security_dal.EMAIL_CODE_VERIFY_SCOPE,
                identifier=throttle_identifier,
                max_failures=self.settings.BRUTE_FORCE_MAX_FAILURES,
                window_seconds=self.settings.BRUTE_FORCE_WINDOW_SECONDS,
                lock_seconds=self.settings.BRUTE_FORCE_LOCK_SECONDS,
                now=now,
            )
            await session.flush()
            if throttle_result.locked:
                return EmailCodeVerifyResult(
                    ok=False,
                    error="rate_limited",
                    retry_after=throttle_result.retry_after,
                )
            return EmailCodeVerifyResult(ok=False, error="invalid_code")

        latest_code.consumed_at = now
        await security_dal.clear_throttle_state(
            session,
            scope=security_dal.EMAIL_CODE_VERIFY_SCOPE,
            identifier=throttle_identifier,
        )
        await session.flush()
        return EmailCodeVerifyResult(ok=True)

    async def _get_latest_code(
        self,
        session: AsyncSession,
        *,
        email: str,
        purpose: str,
        target_user_id: Optional[int],
    ) -> Optional[EmailVerificationCode]:
        stmt = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.target_user_id == target_user_id,
                EmailVerificationCode.status == "active",
                EmailVerificationCode.consumed_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _send_code_email(
        self,
        *,
        email: str,
        code: str,
        language_code: str,
    ) -> None:
        await asyncio.to_thread(
            self._send_code_email_sync,
            email=email,
            code=code,
            language_code=language_code,
        )

    async def send_custom_email(
        self,
        *,
        email: str,
        subject: str,
        body: str,
    ) -> None:
        await asyncio.to_thread(
            self._send_custom_email_sync,
            email=email,
            subject=subject,
            body=body,
        )

    def _send_code_email_sync(
        self,
        *,
        email: str,
        code: str,
        language_code: str,
    ) -> None:
        lang = (language_code or self.settings.DEFAULT_LANGUAGE or "ru").split("-")[0]
        if lang == "en":
            subject = "Your login code"
            body = (
                f"Your verification code: {code}\n\n"
                f"The code expires in {max(1, int(self.settings.EMAIL_CODE_TTL_SECONDS) // 60)} minutes."
            )
        else:
            subject = "Код подтверждения"
            body = (
                f"Ваш код подтверждения: {code}\n\n"
                f"Код действует {max(1, int(self.settings.EMAIL_CODE_TTL_SECONDS) // 60)} мин."
            )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr(
            (
                self.settings.SMTP_FROM_NAME or self.settings.WEBAPP_TITLE,
                self.settings.SMTP_FROM_EMAIL or "",
            )
        )
        message["To"] = email
        message.set_content(body)

        context = ssl.create_default_context()
        smtp_host = self.settings.SMTP_HOST
        timeout = max(5, int(self.settings.SMTP_TIMEOUT_SECONDS))
        attempts = self._smtp_attempts()
        last_error: Optional[BaseException] = None

        for attempt_number, attempt in enumerate(attempts, start=1):
            try:
                self._send_message_via_smtp(
                    message=message,
                    smtp_host=smtp_host,
                    smtp_port=attempt.port,
                    timeout=timeout,
                    context=context,
                    use_ssl=attempt.use_ssl,
                    starttls=attempt.starttls,
                )
                logger.info(
                    "Email verification code sent to %s via %s:%s",
                    email,
                    smtp_host,
                    attempt.port,
                )
                return
            except (OSError, smtplib.SMTPException, TimeoutError) as exc:
                last_error = exc
                log_level = logging.WARNING if attempt_number < len(attempts) else logging.ERROR
                logger.log(
                    log_level,
                    "SMTP send attempt %s/%s failed via %s:%s (ssl=%s, starttls=%s): %s",
                    attempt_number,
                    len(attempts),
                    smtp_host,
                    attempt.port,
                    attempt.use_ssl,
                    attempt.starttls,
                    exc,
                )

        if last_error:
            raise last_error

    def _send_custom_email_sync(
        self,
        *,
        email: str,
        subject: str,
        body: str,
    ) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr(
            (
                self.settings.SMTP_FROM_NAME or self.settings.WEBAPP_TITLE,
                self.settings.SMTP_FROM_EMAIL or "",
            )
        )
        message["To"] = email
        message.set_content(body)

        context = ssl.create_default_context()
        smtp_host = self.settings.SMTP_HOST
        timeout = max(5, int(self.settings.SMTP_TIMEOUT_SECONDS))
        attempts = self._smtp_attempts()
        last_error: Optional[BaseException] = None

        for attempt_number, attempt in enumerate(attempts, start=1):
            try:
                self._send_message_via_smtp(
                    message=message,
                    smtp_host=smtp_host,
                    smtp_port=attempt.port,
                    timeout=timeout,
                    context=context,
                    use_ssl=attempt.use_ssl,
                    starttls=attempt.starttls,
                )
                logger.info(
                    "Custom email sent to %s via %s:%s",
                    email,
                    smtp_host,
                    attempt.port,
                )
                return
            except (OSError, smtplib.SMTPException, TimeoutError) as exc:
                last_error = exc
                log_level = logging.WARNING if attempt_number < len(attempts) else logging.ERROR
                logger.log(
                    log_level,
                    "SMTP send attempt %s/%s failed for custom email via %s:%s (ssl=%s, starttls=%s): %s",
                    attempt_number,
                    len(attempts),
                    smtp_host,
                    attempt.port,
                    attempt.use_ssl,
                    attempt.starttls,
                    exc,
                )

        if last_error:
            raise last_error

    def _send_message_via_smtp(
        self,
        *,
        message: EmailMessage,
        smtp_host: str,
        smtp_port: int,
        timeout: int,
        context: ssl.SSLContext,
        use_ssl: bool,
        starttls: bool,
    ) -> None:
        if use_ssl:
            with smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                context=context,
                timeout=timeout,
            ) as smtp:
                smtp.ehlo()
                smtp.login(self.settings.SMTP_USERNAME, self.settings.SMTP_PASSWORD)
                smtp.send_message(message)
            return

        with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as smtp:
            smtp.ehlo()
            if starttls:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(self.settings.SMTP_USERNAME, self.settings.SMTP_PASSWORD)
            smtp.send_message(message)
