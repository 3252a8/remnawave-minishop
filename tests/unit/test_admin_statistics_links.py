from bot.handlers.admin.statistics import _format_rating_user_label
from config.settings import Settings


def _settings(mini_app_url: str | None = "https://app.example.test/app") -> Settings:
    return Settings(
        _env_file=None,
        BOT_TOKEN="x",
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        SUBSCRIPTION_MINI_APP_URL=mini_app_url,
    )


def test_rating_user_link_opens_public_card_in_mini_app() -> None:
    public_id = "ms_" + "a" * 32
    row: dict[str, object] = {"user_id": 42, "minishop_id": public_id, "username": "alice"}

    label = _format_rating_user_label(row, _settings(), "@shop_bot")

    assert f'href="https://t.me/shop_bot?startapp=admin_user_{public_id}"' in label
    assert f"(ID {public_id})" not in label


def test_rating_user_link_uses_numeric_id_when_public_id_is_missing() -> None:
    row: dict[str, object] = {"user_id": 42, "minishop_id": None}

    label = _format_rating_user_label(row, _settings(), "shop_bot")

    assert 'href="https://t.me/shop_bot?startapp=admin_user_42"' in label


def test_rating_user_link_omits_invalid_destination() -> None:
    row: dict[str, object] = {"user_id": 42, "minishop_id": "ms_" + "a" * 32}

    assert "href=" not in _format_rating_user_label(row, _settings(), "YOUR_BOT_USERNAME")
    assert "href=" not in _format_rating_user_label(row, _settings(None), "shop_bot")
