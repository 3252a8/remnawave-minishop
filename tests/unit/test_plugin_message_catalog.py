import asyncio
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.plugins import message_catalog
from bot.plugins.extensions import (
    ExtensionContributions,
    ExtensionError,
    MessageShortcode,
    MessageShortcodeContext,
)
from bot.plugins.extensions.registry import ExtensionRegistry, get_registry, set_registry
from bot.services.broadcast_personalization import (
    BroadcastUserContext,
    known_shortcodes,
    render_broadcast_text,
    unknown_shortcodes,
)
from bot.services.message_composition import (
    MessageButtonInput,
    MessageValidationError,
    resolve_message_buttons,
)
from bot.services.plugin_shortcodes import load_plugin_shortcodes
from config.extension_targets import extension_start_parameter
from config.menu_buttons import MenuButton
from config.settings import Settings


@pytest.fixture
def registry(monkeypatch):
    previous = get_registry()
    value = ExtensionRegistry()
    set_registry(value)
    monkeypatch.setattr("bot.services.plugin_shortcodes.generation_is_current", lambda: True)
    yield value
    set_registry(previous)


def test_registration_is_namespaced_and_rejects_duplicate_ids_atomically(registry) -> None:
    resolver = AsyncMock(return_value={})
    spec = MessageShortcode("quota", "plugin_quota", resolver)
    registry.register("sample-plugin", "1", ExtensionContributions(message_shortcodes=(spec,)))
    assert known_shortcodes("{sample-plugin.quota} {first_name}") == {
        "sample-plugin.quota",
        "first_name",
    }
    assert unknown_shortcodes("{other.quota}") == {"other.quota"}
    with pytest.raises(ExtensionError, match="duplicate"):
        registry.register("other", "1", ExtensionContributions(message_shortcodes=(spec, spec)))
    assert "other" not in registry.owners()


def test_bulk_values_are_recipient_scoped_and_html_escaped(registry) -> None:
    resolver = AsyncMock(return_value={42: '<a href="bad">private & value</a>', 43: "other"})
    registry.register(
        "sample",
        "1",
        ExtensionContributions(message_shortcodes=(MessageShortcode("quota", "key", resolver),)),
    )
    mock_session = MagicMock()
    mock_session.begin_nested.return_value = AsyncMock()
    settings = cast(Settings, MagicMock())
    contexts = {uid: BroadcastUserContext(uid) for uid in (42, 43)}
    context = MessageShortcodeContext(cast(AsyncSession, mock_session), settings, (42, 43), {})
    asyncio.run(load_plugin_shortcodes(context, contexts, {"sample.quota"}))
    resolver.assert_awaited_once_with(context)
    rendered = render_broadcast_text(
        "{sample.quota} {unknown}", contexts[42], lang="en", i18n=None, settings=settings
    )
    assert rendered == "&lt;a href=&quot;bad&quot;&gt;private &amp; value&lt;/a&gt; {unknown}"
    assert (
        render_broadcast_text(
            "{sample.quota}", contexts[43], lang="en", i18n=None, settings=settings, escape=False
        )
        == "other"
    )


@pytest.mark.parametrize("result", [RuntimeError("failure"), {99: "foreign"}, {42: object()}])
def test_bad_provider_does_not_abort_or_leak_other_users(registry, result) -> None:
    resolver = (
        AsyncMock(side_effect=result)
        if isinstance(result, Exception)
        else AsyncMock(return_value=result)
    )
    registry.register(
        "sample",
        "1",
        ExtensionContributions(message_shortcodes=(MessageShortcode("quota", "key", resolver),)),
    )
    mock_session = MagicMock()
    mock_session.begin_nested.return_value = AsyncMock()
    settings = cast(Settings, MagicMock())
    contexts = {42: BroadcastUserContext(42)}
    asyncio.run(
        load_plugin_shortcodes(
            MessageShortcodeContext(cast(AsyncSession, mock_session), settings, (42,), {}),
            contexts,
            {"sample.quota"},
        )
    )
    assert contexts[42].plugin_values == {}
    assert (
        render_broadcast_text(
            "{sample.quota}", contexts[42], lang="en", i18n=None, settings=settings
        )
        == "—"
    )


def test_active_page_targets_preserve_query_and_have_valid_telegram_payloads(
    registry, monkeypatch, tmp_path: Path
) -> None:
    owner = "sample__plugin"
    registry.register(owner, "1", ExtensionContributions())
    release = tmp_path / "releases" / owner / "digest"
    release.mkdir(parents=True)
    (release / "plugin.json").write_text(
        json.dumps(
            {
                "frontend": {
                    "user": {"entry": "user.js", "pages": [{"id": "rewards", "label": "Rewards"}]}
                }
            }
        ),
        encoding="utf-8",
    )
    state: dict[str, Any] = {
        "generation": 2,
        "installations": {owner: {"enabled": True, "digest": "digest"}},
        "observations": {
            role: {"generation": 2, "status": "active"} for role in ("backend", "worker")
        },
    }
    monkeypatch.setattr(message_catalog, "package_root", lambda: tmp_path)
    monkeypatch.setattr(message_catalog, "read_state", lambda root: state)
    monkeypatch.setattr(message_catalog, "generation_is_current", lambda: True)
    path = f"/extensions/{owner}/rewards"
    assert extension_start_parameter(path) == "ext_sample__plugin__rewards"
    button = MessageButtonInput(kind="webapp_section", section=path, label="Rewards")
    resolved = resolve_message_buttons(
        [button], mini_app_url="https://shop.example/app?ref=value", bot_username="shop_bot"
    )[0]
    assert "ref=value" in resolved.url
    assert "startapp=ext_sample__plugin__rewards" in resolved.url
    assert resolved.telegram_web_app_url == resolved.url
    fallback = resolve_message_buttons([button], mini_app_url=None, bot_username="shop_bot")[0]
    assert fallback.url == "https://t.me/shop_bot?startapp=ext_sample__plugin__rewards"
    assert (
        MenuButton(id="rewards", kind="webapp", target=path, labels={"en": "Rewards"}).target
        == path
    )
    state["installations"][owner]["enabled"] = False
    with pytest.raises(MessageValidationError) as caught:
        resolve_message_buttons([button], mini_app_url=None, bot_username="shop_bot")
    assert caught.value.code == "button_section_invalid"


@pytest.mark.parametrize(
    "path", ["/extensions/owner/../admin", "/admin/plugins", "/extensions/x/page?foo=1"]
)
def test_invalid_plugin_target_cannot_be_saved(path: str) -> None:
    with pytest.raises(ValueError):
        MenuButton(id="bad", kind="webapp", target=path, labels={"en": "Bad"})
