"""Browser-safe links from Mini Shop admin to Remnawave Panel."""

from urllib.parse import urlsplit, urlunsplit

from bot.services.panel_api_compat import numeric_panel_user_id


def build_panel_user_admin_url(
    panel_api_url: object,
    panel_user_reference: object,
) -> str | None:
    """Build the Remnawave 3.x user-card URL when a numeric user id is known.

    Remnawave 2.x stores UUID user references and has no equivalent deep-link
    route. Returning ``None`` for those references keeps older installations
    from rendering a link that the panel cannot open.
    """

    user_id = numeric_panel_user_id(panel_user_reference)
    raw_url = str(panel_api_url or "").strip()
    if user_id is None or not raw_url:
        return None

    try:
        parsed = urlsplit(raw_url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None

    base_path = parsed.path.rstrip("/")
    if base_path.lower().endswith("/api"):
        base_path = base_path[:-4].rstrip("/")
    path = f"{base_path}/dashboard/open/user/{user_id}"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))
