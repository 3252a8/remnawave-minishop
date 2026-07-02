"""
LKNPD API client for self-employed (NPD) tax receipts.
Custom implementation for lknpd.nalog.ru API.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PaymentType(StrEnum):
    """Payment type for income registration."""

    CASH = "CASH"
    WIRE = "WIRE"


class IncomeType(StrEnum):
    """Income source type."""

    FROM_INDIVIDUAL = "FROM_INDIVIDUAL"
    FROM_LEGAL_ENTITY = "FROM_LEGAL_ENTITY"
    FROM_FOREIGN_AGENCY = "FROM_FOREIGN_AGENCY"


class LknpdApiError(Exception):
    """Base exception for LKNPD API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class LknpdAuthError(LknpdApiError):
    """Authentication error (401)."""

    pass


class LknpdValidationError(LknpdApiError):
    """Validation error (400)."""

    pass


def _generate_device_id() -> str:
    """Generate device ID for API requests."""
    return str(uuid.uuid4()).replace("-", "")[:21].lower()


def _format_datetime(dt: datetime) -> str:
    """Format datetime to ISO/ATOM format with Z suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    elif dt.tzinfo != UTC:
        dt = dt.astimezone(UTC)
    return dt.isoformat().replace("+00:00", "Z")


class LknpdClient:
    """
    Async client for LKNPD (lknpd.nalog.ru) self-employed API.

    Supports:
    - INN + password authentication
    - Token refresh
    - Income registration with proper payment types (CASH/WIRE)
    """

    DEFAULT_HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referrer": "https://lknpd.nalog.ru/auth/login",
    }

    DEVICE_INFO_TEMPLATE = {
        "sourceType": "WEB",
        "appVersion": "1.0.0",
        "metaDetails": {
            "userAgent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_2_2) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/88.0.4324.192 Safari/537.36"
            )
        },
    }

    def __init__(
        self,
        base_url: str = "https://lknpd.nalog.ru/api",
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.device_id = _generate_device_id()
        self._token_data: dict[str, Any] | None = None
        self._refresh_lock = asyncio.Lock()

    def _get_device_info(self) -> dict[str, Any]:
        """Get device info with current device ID."""
        info = self.DEVICE_INFO_TEMPLATE.copy()
        info["sourceDeviceId"] = self.device_id
        return info

    async def authenticate(self, inn: str, password: str) -> bool:
        """
        Authenticate with INN and password.

        Returns True if authentication was successful.
        """
        request_data = {
            "username": inn,
            "password": password,
            "deviceInfo": self._get_device_info(),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/auth/lkfl",
                    json=request_data,
                    headers=self.DEFAULT_HEADERS,
                )

                if response.status_code == 401:
                    raise LknpdAuthError("Invalid credentials", 401)

                if response.status_code >= 400:
                    raise LknpdApiError(
                        f"Authentication failed: {response.text}",
                        response.status_code,
                    )

                self._token_data = response.json()
                logger.info("LKNPD authentication successful")
                return True

        except httpx.RequestError as e:
            logger.exception("Network error during authentication")
            raise LknpdApiError(f"Network error: {e}") from e

    async def _refresh_token(self) -> bool:
        """Refresh access token using refresh token."""
        async with self._refresh_lock:
            if not self._token_data or "refreshToken" not in self._token_data:
                return False

            request_data = {
                "deviceInfo": self._get_device_info(),
                "refreshToken": self._token_data["refreshToken"],
            }

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/v1/auth/token",
                        json=request_data,
                        headers=self.DEFAULT_HEADERS,
                    )

                    if response.status_code != 200:
                        return False

                    self._token_data = response.json()
                    logger.info("LKNPD token refreshed")
                    return True

            except Exception:
                logger.exception("Token refresh failed")
                return False

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers from current token."""
        if not self._token_data or "token" not in self._token_data:
            return {}
        return {"Authorization": f"Bearer {self._token_data['token']}"}

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> httpx.Response:
        """Make authenticated API request with auto-retry on 401."""
        headers = {**self.DEFAULT_HEADERS, **self._get_auth_headers()}
        url = f"{self.base_url}/v1{path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                url,
                json=json_data,
                headers=headers,
            )

            # Handle 401 with token refresh
            if response.status_code == 401 and retry_on_401 and await self._refresh_token():
                headers = {**self.DEFAULT_HEADERS, **self._get_auth_headers()}
                response = await client.request(
                    method,
                    url,
                    json=json_data,
                    headers=headers,
                )

            return response

    @property
    def is_authenticated(self) -> bool:
        """Check if client has valid token data."""
        return self._token_data is not None and "token" in self._token_data

    async def create_income(
        self,
        *,
        name: str,
        amount: Decimal | float,
        quantity: Decimal | float | int = 1,
        payment_type: PaymentType = PaymentType.WIRE,
        income_type: IncomeType = IncomeType.FROM_INDIVIDUAL,
        client_inn: str | None = None,
        client_name: str | None = None,
        client_phone: str | None = None,
        operation_time: datetime | None = None,
    ) -> str | None:
        """
        Register income and create receipt.

        Args:
            name: Service/item description
            amount: Price per unit
            quantity: Number of units
            payment_type: CASH or WIRE (for card/bank payments)
            income_type: Source type (individual, legal entity, foreign)
            client_inn: Client's INN (required for legal entities)
            client_name: Client's display name
            client_phone: Client's phone number
            operation_time: Time of operation (defaults to now)

        Returns:
            Receipt UUID if successful, None otherwise
        """
        if not self.is_authenticated:
            raise LknpdAuthError("Not authenticated")

        # Prepare times
        now = datetime.now(UTC)
        op_time = operation_time or now

        # Calculate total
        amount_decimal = Decimal(str(amount))
        qty_decimal = Decimal(str(quantity))
        total = amount_decimal * qty_decimal

        # API expects quantity as integer when it's a whole number
        qty_value: int | str
        if qty_decimal == qty_decimal.to_integral_value():
            qty_value = int(qty_decimal)
        else:
            qty_value = str(qty_decimal)

        # Build request
        request_data = {
            "operationTime": _format_datetime(op_time),
            "requestTime": _format_datetime(now),
            "services": [
                {
                    "name": name,
                    "amount": str(amount_decimal),
                    "quantity": qty_value,
                }
            ],
            "totalAmount": str(total),
            "client": {
                "contactPhone": client_phone,
                "displayName": client_name,
                "incomeType": income_type.value,
                "inn": client_inn,
            },
            "paymentType": payment_type.value,
            "ignoreMaxTotalIncomeRestriction": False,
        }

        try:
            response = await self._request("POST", "/income", json_data=request_data)

            if response.status_code == 400:
                logger.error("LKNPD validation error: %s", response.text)
                raise LknpdValidationError(response.text, 400)

            if response.status_code == 401:
                raise LknpdAuthError("Authentication expired", 401)

            if response.status_code >= 400:
                logger.error(
                    "LKNPD API error: status=%d body=%s",
                    response.status_code,
                    response.text,
                )
                raise LknpdApiError(response.text, response.status_code)

            payload = response.json()
            receipt_uuid = (
                payload.get("approvedReceiptUuid")
                or payload.get("receiptUuid")
                or payload.get("receipt_uuid")
            )

            if receipt_uuid:
                logger.info("LKNPD receipt created: %s", receipt_uuid)

            return receipt_uuid if isinstance(receipt_uuid, str) else None

        except httpx.RequestError as e:
            logger.exception("Network error creating income")
            raise LknpdApiError(f"Network error: {e}") from e
