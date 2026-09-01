"""Every file the bundler emits must be reachable through the router.

A chunk the router cannot address is close to invisible: the bundle asks for
it, the request 404s, and the screen that needed it simply never appears. This
happened once already, when a chunk built from a ``*.svelte.ts`` module grew a
second dot and stopped matching the admin chunk pattern.
"""

from aiohttp import web

from bot.app.web.webapp.routes import setup_subscription_webapp_routes


def _resolve(path: str) -> str | None:
    """Name of the handler the router picks for ``path``, if any."""

    app = web.Application()
    setup_subscription_webapp_routes(app)
    for resource in app.router.resources():
        for route in resource:
            if route.method not in {"GET", "*"}:
                continue
            info = resource.get_info()
            pattern = info.get("pattern")
            if pattern is not None:
                if pattern.fullmatch(path):
                    return route.handler.__name__
            elif info.get("path") == path:
                return route.handler.__name__
    return None


def test_bundle_entries_keep_their_own_handlers():
    assert _resolve("/subscription_webapp.js") == "js_asset_route"
    assert _resolve("/subscription_webapp.min.a1b2c3d4.js") == "js_asset_route"
    assert _resolve("/subscription_webapp_admin.js") == "admin_js_asset_route"
    assert _resolve("/subscription_webapp_admin.min.a1b2c3d4.js") == "admin_js_asset_route"


def test_code_split_chunks_resolve_for_both_bundles():
    assert _resolve("/subscription_webapp.SupportScreen.BDvmkllB.js") == "js_chunk_asset_route"
    assert _resolve("/subscription_webapp.richtext.BlVa-C7Q.js") == "js_chunk_asset_route"
    assert (
        _resolve("/subscription_webapp_admin.AdsSection.BxzxRxnB.js")
        == "admin_js_chunk_asset_route"
    )


def test_a_chunk_named_after_a_dotted_module_still_resolves():
    # `broadcastStore.svelte.ts` produces this name, and a pattern that allowed
    # exactly one segment before the hash used to 404 it.
    assert (
        _resolve("/subscription_webapp_admin.broadcastStore.svelte.AzLJH7JK.js")
        == "admin_js_chunk_asset_route"
    )
    assert _resolve("/subscription_webapp.lazyScreen.svelte.AzLJH7JK.js") == "js_chunk_asset_route"


def test_stylesheets_are_not_captured_by_the_chunk_patterns():
    assert _resolve("/subscription_webapp.css") == "css_asset_route"
    assert _resolve("/subscription_webapp.a1b2c3d4.css") == "css_asset_route"
    assert _resolve("/subscription_webapp_admin.css") == "admin_css_asset_route"


def test_flag_font_has_a_dedicated_static_route():
    assert _resolve("/fonts/TwemojiCountryFlags.woff2") == "flag_font_asset_route"
