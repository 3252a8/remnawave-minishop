import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.middlewares.i18n import JsonI18n
from bot.payment_providers.base import WebAppPaymentContext
from bot.payment_providers.stars import service as stars
from config.settings import Settings


@pytest.fixture
def device_description() -> str:
    return str(JsonI18n("locales").gettext("ru", "payment_description_hwid_devices", count=1))


def test_stars_chat_invoice_uses_a_short_title(monkeypatch, device_description):
    bot = SimpleNamespace(send_invoice=AsyncMock())
    service = stars.StarsService(
        bot=bot,
        settings=SimpleNamespace(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
    )
    create_record = AsyncMock(return_value=SimpleNamespace(payment_id=7))
    monkeypatch.setattr(stars.payment_dal, "create_payment_record", create_record)

    payment_id = asyncio.run(
        service.create_invoice(
            session=AsyncMock(),
            user_id=42,
            chat_id=123,
            months=1,
            stars_price=150,
            description=device_description,
            sale_mode="hwid_devices@standard",
        )
    )

    assert payment_id == 7
    bot.send_invoice.assert_awaited_once()
    invoice = bot.send_invoice.await_args.kwargs
    assert invoice["chat_id"] == 123
    assert 1 <= len(invoice["title"]) <= 32
    assert invoice["description"] == device_description


@pytest.mark.parametrize(("units", "rub_price", "expected_stars"), [(0.5, 100, 106), (1.0, 0, 80)])
def test_stars_traffic_callback_uses_the_current_price(
    monkeypatch, tmp_path, units, rub_price, expected_stars
):
    settings = Settings(
        TARIFFS_CONFIG_PATH=str(tmp_path / "missing.json"),
        DEFAULT_CURRENCY_SYMBOL="RUB",
        STARS_ENABLED=True,
        STARS_RUB_PER_STAR=0.95,
        TRAFFIC_PACKAGES=f"{units}:{rub_price}",
        STARS_TRAFFIC_PACKAGES=f"{units}:80",
    )
    bot = SimpleNamespace(send_invoice=AsyncMock())
    i18n = JsonI18n("locales")
    service = stars.StarsService(bot, settings, i18n, SimpleNamespace(), SimpleNamespace())
    create_record = AsyncMock(return_value=SimpleNamespace(payment_id=7))
    monkeypatch.setattr(stars.payment_dal, "create_payment_record", create_record)
    monkeypatch.setattr(stars, "require_telegram_account_id", AsyncMock(return_value=42))
    callback = SimpleNamespace(
        data=f"pay_stars:{units}:80:traffic",
        from_user=SimpleNamespace(id=123),
        message=AsyncMock(),
        answer=AsyncMock(),
    )

    asyncio.run(
        stars.pay_stars_callback_handler(
            callback, settings, {"i18n_instance": i18n}, AsyncMock(), service
        )
    )

    bot.send_invoice.assert_awaited_once()
    invoice = bot.send_invoice.await_args.kwargs
    assert invoice["prices"][0].amount == expected_stars
    assert invoice["payload"] == f"7:{units:g}:traffic"
    assert create_record.await_args.args[1]["purchased_gb"] == units


@pytest.mark.parametrize("use_invoice_link", [True, False])
def test_stars_mini_app_invoice_title_limit(monkeypatch, device_description, use_invoice_link):
    bot = SimpleNamespace(send_invoice=AsyncMock())
    if use_invoice_link:
        bot.create_invoice_link = AsyncMock(return_value="https://t.me/$test_invoice")
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={"bot": bot}),
        session=AsyncMock(),
        user_id=42,
        method="stars",
        months=1,
        price=150,
        stars_price=150,
        description=device_description,
        sale_mode="hwid_devices@standard",
    )
    monkeypatch.setattr(
        stars, "create_webapp_payment_record", AsyncMock(return_value=SimpleNamespace(payment_id=7))
    )

    response = asyncio.run(stars.create_webapp_payment(context))

    assert response.status == 200
    action = "open_invoice" if use_invoice_link else "invoice_sent"
    assert response.text is not None
    assert json.loads(response.text)["action"] == action
    method = bot.create_invoice_link if use_invoice_link else bot.send_invoice
    method.assert_awaited_once()
    invoice = method.await_args.kwargs
    assert 1 <= len(invoice["title"]) <= 32
    assert invoice["description"] == device_description
