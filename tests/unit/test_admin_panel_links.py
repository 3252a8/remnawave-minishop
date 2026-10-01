import pytest

from bot.app.web.admin_api_impl.panel_links import build_panel_user_admin_url


@pytest.mark.parametrize(
    ("public_url", "expected"),
    [
        ("https://panel.example.com", "https://panel.example.com/dashboard/open/user/158"),
        (
            " https://panel.example.com/prefix/API/?access=hidden#fragment ",
            "https://panel.example.com/prefix/dashboard/open/user/158",
        ),
        ("http://localhost:3000/api", "http://localhost:3000/dashboard/open/user/158"),
    ],
)
def test_public_panel_url_overrides_internal_api_url(public_url: str, expected: str) -> None:
    assert build_panel_user_admin_url("http://remnawave:3000/api", 158, public_url) == expected


@pytest.mark.parametrize("public_url", [None, "", "  "])
def test_empty_public_panel_url_preserves_existing_links(public_url: str | None) -> None:
    assert build_panel_user_admin_url("https://panel.example.com/api", 42, public_url) == (
        "https://panel.example.com/dashboard/open/user/42"
    )


@pytest.mark.parametrize(
    "public_url",
    ["javascript:alert(1)", "https://admin:secret@panel.example.com", "https://panel:invalid"],
)
def test_invalid_public_panel_url_does_not_fall_back_to_internal_api(public_url: str) -> None:
    assert build_panel_user_admin_url("http://remnawave:3000/api", 158, public_url) is None


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
