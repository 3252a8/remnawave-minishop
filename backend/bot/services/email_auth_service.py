import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.email_templates import EmailContent, EmailInlineImage, render_login_code
from bot.services.message_audit import log_user_message_delivery
from config.settings import Settings
from db.dal import security_dal, user_dal
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


@dataclass(frozen=True)
class EmailMagicVerifyResult:
    ok: bool
    error: Optional[str] = None
    email: Optional[str] = None
    purpose: Optional[str] = None
    target_user_id: Optional[int] = None


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def email_domain(value: Optional[str]) -> str:
    email = normalize_email(value or "")
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower().rstrip(".")


def is_valid_email(value: str) -> bool:
    email = normalize_email(value)
    return bool(email and len(email) <= 254 and EMAIL_RE.match(email))


def _split_disposable_domain_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\s]+", value or "") if item.strip()]


def is_disposable_email(value: Optional[str], settings: Settings) -> bool:
    domain = email_domain(value)
    if not domain:
        return False
    blocked_domains = getattr(settings, "disposable_email_domains", None)
    if blocked_domains is None:
        blocked_domains = _split_disposable_domain_values(
            str(getattr(settings, "DISPOSABLE_EMAIL_DOMAINS", "") or "")
        )
    blocked_domains = blocked_domains or []
    for blocked in blocked_domains:
        normalized = str(blocked or "").strip().lower().lstrip("@.")
        if normalized and (domain == normalized or domain.endswith(f".{normalized}")):
            return True
    return False


def _email_throttle_identifier(email: str, purpose: str, target_user_id: Optional[int]) -> str:
    target_part = "none" if target_user_id is None else str(target_user_id)
    return f"{purpose}:{target_part}:{email}"


class EmailAuthService:
    def __init__(self, settings: Settings, i18n: Optional[JsonI18n] = None):
        self.settings = settings
        self.i18n = i18n

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

    def _hash_magic_token(self, token: str) -> str:
        secret = hmac.new(
            self.settings.BOT_TOKEN.encode("utf-8"),
            b"remnawave-tg-shop-email-magic",
            hashlib.sha256,
        ).digest()
        return hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _build_magic_link(self, *, token: str, purpose: str) -> Optional[str]:
        base_url = (self.settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
        if not base_url:
            return None
        from urllib.parse import urlencode, urlsplit, urlunsplit

        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
        params = {"login_token": token}
        if purpose and purpose != "login":
            params["login_purpose"] = purpose
        existing_query = parsed.query
        new_query = urlencode(params)
        merged_query = f"{existing_query}&{new_query}" if existing_query else new_query
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, merged_query, parsed.fragment)
        )

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
        magic_token = secrets.token_urlsafe(32)
        magic_link = (
            self._build_magic_link(token=magic_token, purpose=purpose)
            if purpose == "login"
            else None
        )
        code_model = EmailVerificationCode(
            email=normalized_email,
            code_hash=self._hash_code(normalized_email, purpose, code),
            magic_token_hash=self._hash_magic_token(magic_token) if magic_link else None,
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
            magic_link=magic_link,
            purpose=purpose,
        )
        resolved_target_user_id = target_user_id
        if resolved_target_user_id is None:
            try:
                existing_user = await user_dal.get_user_by_email(session, normalized_email)
                resolved_target_user_id = (
                    int(existing_user.user_id) if existing_user is not None else None
                )
            except Exception:
                logger.exception(
                    "Failed to resolve email auth target user for audit log: %s",
                    normalized_email,
                )
        await log_user_message_delivery(
            session,
            target_user_id=resolved_target_user_id,
            event_type="email_login_code_sent"
            if purpose == "login"
            else "email_verification_code_sent",
            channel="email",
            recipient=normalized_email,
            content=f"purpose={purpose} magic_link={bool(magic_link)}",
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

    async def verify_magic_token(
        self,
        session: AsyncSession,
        *,
        token: str,
        purpose: str,
        target_user_id: Optional[int] = None,
    ) -> EmailMagicVerifyResult:
        if not token:
            return EmailMagicVerifyResult(ok=False, error="invalid_token")

        token_hash = self._hash_magic_token(token)
        now = datetime.now(timezone.utc)
        stmt = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.magic_token_hash == token_hash,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.target_user_id == target_user_id,
                EmailVerificationCode.status == "active",
                EmailVerificationCode.consumed_at.is_(None),
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return EmailMagicVerifyResult(ok=False, error="invalid_token")

        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            return EmailMagicVerifyResult(ok=False, error="expired_token")

        record.consumed_at = now
        throttle_identifier = _email_throttle_identifier(
            record.email,
            purpose,
            target_user_id,
        )
        await security_dal.clear_throttle_state(
            session,
            scope=security_dal.EMAIL_CODE_VERIFY_SCOPE,
            identifier=throttle_identifier,
        )
        await session.flush()
        return EmailMagicVerifyResult(
            ok=True,
            email=record.email,
            purpose=record.purpose,
            target_user_id=record.target_user_id,
        )

    async def _send_code_email(
        self,
        *,
        email: str,
        code: str,
        language_code: str,
        magic_link: Optional[str] = None,
        purpose: str = "login",
    ) -> None:
        await asyncio.to_thread(
            self._send_code_email_sync,
            email=email,
            code=code,
            language_code=language_code,
            magic_link=magic_link,
            purpose=purpose,
        )

    async def send_custom_email(
        self,
        *,
        email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        inline_images: Sequence[EmailInlineImage] = (),
    ) -> None:
        await asyncio.to_thread(
            self._send_custom_email_sync,
            email=email,
            subject=subject,
            body=body,
            html_body=html_body,
            inline_images=inline_images,
        )

    async def send_rendered_email(
        self,
        *,
        email: str,
        content: EmailContent,
    ) -> None:
        await self.send_custom_email(
            email=email,
            subject=content.subject,
            body=content.text,
            html_body=content.html,
            inline_images=content.inline_images,
        )

    def _send_code_email_sync(
        self,
        *,
        email: str,
        code: str,
        language_code: str,
        magic_link: Optional[str] = None,
        purpose: str = "login",
    ) -> None:
        content = render_login_code(
            self.settings,
            code=code,
            language_code=language_code,
            magic_link=magic_link,
            purpose=purpose,
            i18n=self.i18n,
        )

        message = self._build_email_message(
            email=email,
            subject=content.subject,
            body=content.text,
            html_body=content.html,
            inline_images=content.inline_images,
        )

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
        html_body: Optional[str] = None,
        inline_images: Sequence[EmailInlineImage] = (),
    ) -> None:
        message = self._build_email_message(
            email=email,
            subject=subject,
            body=body,
            html_body=html_body,
            inline_images=inline_images,
        )

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
                    "SMTP send attempt %s/%s failed for custom email via %s:%s (ssl=%s, starttls=%s): %s",  # noqa: E501
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

    def _build_email_message(
        self,
        *,
        email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        inline_images: Sequence[EmailInlineImage] = (),
    ) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=False, usegmt=True)
        message["From"] = formataddr(
            (
                self.settings.SMTP_FROM_NAME or self.settings.WEBAPP_TITLE,
                self.settings.SMTP_FROM_EMAIL or "",
            )
        )
        message["To"] = email
        from_email = self.settings.SMTP_FROM_EMAIL or ""
        from_domain = from_email.rsplit("@", 1)[-1].strip() if "@" in from_email else None
        message["Message-ID"] = make_msgid(domain=from_domain or None)
        message.set_content(body)
        if html_body:
            message.add_alternative(html_body, subtype="html")
            self._attach_inline_images(message, inline_images)
        return message

    @staticmethod
    def _attach_inline_images(
        message: EmailMessage,
        inline_images: Sequence[EmailInlineImage],
    ) -> None:
        if not inline_images:
            return
        html_part = message.get_body(("html",))
        if html_part is None:
            return

        for image in inline_images:
            content_type = (image.content_type or "").split(";", 1)[0].strip().lower()
            if "/" not in content_type:
                continue
            maintype, subtype = content_type.split("/", 1)
            if maintype != "image" or not subtype:
                continue

            body = bytes(image.data or b"")
            content_id = (image.content_id or "").strip()
            if not body or not content_id:
                continue

            cid_header = content_id
            if not (cid_header.startswith("<") and cid_header.endswith(">")):
                cid_header = f"<{cid_header}>"
            html_part.add_related(
                body,
                maintype=maintype,
                subtype=subtype,
                cid=cid_header,
                disposition="inline",
                filename=EmailAuthService._inline_image_filename(content_id, subtype),
            )

    @staticmethod
    def _inline_image_filename(content_id: str, subtype: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", content_id).strip(".-") or "image"
        safe_subtype = str(subtype or "").split("+", 1)[0].strip().lower()
        extension = {
            "jpeg": "jpg",
            "x-icon": "ico",
        }.get(safe_subtype, safe_subtype)
        if not re.fullmatch(r"[A-Za-z0-9]{1,12}", extension):
            extension = "bin"
        return f"{safe_name}.{extension}"

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
