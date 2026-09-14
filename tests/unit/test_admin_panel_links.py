import pytest

from bot.app.web.admin_api_impl.panel_links import build_panel_user_admin_url


@pytest.mark.parametrize(
    ("api_url", "expected"),
    [
        (
            "https://panel.example.com/api",
            "https://panel.example.com/dashboard/open/user/42",
        ),
        (
            "https://panel.example.com/prefix/API/?token=ignored#fragment",
            "https://panel.example.com/prefix/dashboard/open/user/42",
        ),
        (
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3000/dashboard/open/user/42",
        ),
    ],
)
def test_build_panel_user_admin_url_for_remnawave_3(
    api_url: str,
    expected: str,
) -> None:
    assert build_panel_user_admin_url(api_url, "42") == expected


@pytest.mark.parametrize(
    ("api_url", "user_reference"),
    [
        ("https://panel.example.com/api", "legacy-user-uuid"),
        ("https://panel.example.com/api", 0),
        ("https://panel.example.com/api", True),
        ("javascript:alert(1)", 42),
        ("https://admin:secret@panel.example.com/api", 42),
        ("https://panel.example.com:invalid/api", 42),
        (None, 42),
    ],
)
def test_build_panel_user_admin_url_rejects_unsupported_inputs(
    api_url: object,
    user_reference: object,
) -> None:
    assert build_panel_user_admin_url(api_url, user_reference) is None
