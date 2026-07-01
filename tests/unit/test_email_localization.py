import json
import re
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from bot.middlewares.i18n import JsonI18n
from bot.services import email_templates as email_templates_module
from bot.services.email_templates import (
    EmailContent,
    render_account_merged,
    render_login_code,
    render_payment_success,
    render_subscription_expiring,
    render_subscription_lifecycle_notification,
    render_support_admin_reply_user,
    render_support_new_ticket_admin,
    render_support_ticket_closed_user,
    render_support_user_reply_admin,
    render_user_notification,
)
from config.webapp_themes_config import WebappThemesConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
EMAIL_KEY_RE = re.compile(r"""["'](?P<key>email_[a-z0-9_]+)["']""")
EMAIL_KEY_ASSIGNMENT_HINTS = (
    "subject_key",
    "heading_key",
    "intro_key",
    "cta_label_key",
)


def _settings(
    default_language: str = "ru",
    *,
    webapp_themes_catalog: WebappThemesConfig | None = None,
    primary_color: str = "#00fe7a",
):
    return SimpleNamespace(
        DEFAULT_LANGUAGE=default_language,
        EMAIL_CODE_TTL_SECONDS=600,
        WEBAPP_LOGO_URL="",
        WEBAPP_PRIMARY_COLOR=primary_color,
        WEBAPP_TITLE="Mini Shop",
        webapp_themes_catalog=webapp_themes_catalog,
    )


def _i18n(default_language: str = "ru"):
    return JsonI18n(str(REPO_ROOT / "locales"), default=default_language)


def _image_bytes(image: Image.Image, image_format: str, **kwargs) -> bytes:
    raw = BytesIO()
    image.save(raw, format=image_format, **kwargs)
    return raw.getvalue()


def _locale_keys(language: str) -> set[str]:
    return set(json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8")))


def _email_locale_keys_from(path: Path) -> set[str]:
    text = path.read_text("utf-8")
    keys: set[str] = set()
    for match in EMAIL_KEY_RE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start : line_end if line_end != -1 else len(text)]
        if "template_prefix" in line:
            continue
        if path.name == "email_templates.py" or any(
            hint in line for hint in EMAIL_KEY_ASSIGNMENT_HINTS
        ):
            keys.add(match.group("key"))
    return keys


def _email_preview_locale_keys() -> set[str]:
    paths = (
        REPO_ROOT / "docs-site" / "src" / "lib" / "emailPreviews.mjs",
        REPO_ROOT / "docs-site" / "scripts" / "generate-email-previews.py",
    )
    keys: set[str] = set()
    for path in paths:
        keys.update(match.group("key") for match in EMAIL_KEY_RE.finditer(path.read_text("utf-8")))
    return keys


def _used_email_locale_keys() -> set[str]:
    keys = _email_preview_locale_keys()
    for path in (REPO_ROOT / "backend" / "bot").rglob("*.py"):
        keys.update(_email_locale_keys_from(path))
    return keys


def _assert_content_is_localized(content: EmailContent, language: str):
    assert content.subject
    assert content.text
    assert content.html
    assert f'<html lang="{language}"' in content.html
    assert "email_" not in content.subject
    assert "email_" not in content.text
    assert "email_" not in content.html


def _all_rendered_email_variants(language: str) -> list[EmailContent]:
    settings = _settings(default_language=language)
    i18n = _i18n(default_language=language)
    dashboard_url = "https://app.example.com/account"
    ticket_url = "https://app.example.com/support/42"

    contents: list[EmailContent] = [
        render_login_code(
            settings,
            code="123456",
            language_code=language,
            magic_link="https://app.example.com/magic",
            purpose="login",
            i18n=i18n,
        ),
        render_login_code(
            settings,
            code="123456",
            language_code=language,
            purpose="set_password",
            i18n=i18n,
        ),
        render_account_merged(
            settings,
            language_code=language,
            primary_user_id=100200300,
            removed_user_id=-42,
            final_end_date_text="2026-06-21 10:00",
            i18n=i18n,
        ),
        render_user_notification(
            settings,
            language_code=language,
            subject=i18n.gettext(language, "email_payment_failed_subject"),
            heading=i18n.gettext(language, "email_payment_failed_subject"),
            intro=i18n.gettext(language, "email_user_notification_intro"),
            cta_label=i18n.gettext(language, "email_user_notification_cta"),
            message_text="Payment status changed.",
            dashboard_url=dashboard_url,
            i18n=i18n,
        ),
    ]

    for sale_mode, months, traffic_gb in (
        ("subscription", 1, None),
        ("traffic", 0, 100),
        ("premium_topup", 0, 25),
        ("hwid_device", 2, None),
        ("tariff_upgrade", 0, None),
    ):
        contents.append(
            render_payment_success(
                settings,
                language_code=language,
                sale_mode=sale_mode,
                months=months,
                traffic_gb=traffic_gb,
                amount=390,
                currency="RUB",
                end_date_text="2026-06-21 10:00",
                dashboard_url=dashboard_url,
                provider_label="YooKassa",
                i18n=i18n,
            )
        )

    for days_left in (0, 1, 3):
        contents.append(
            render_subscription_expiring(
                settings,
                language_code=language,
                days_left=days_left,
                end_date_text="2026-06-21 10:00",
                dashboard_url=dashboard_url,
                i18n=i18n,
            )
        )

    lifecycle_variants = (
        {"notification_key": "before_2d_autorenew"},
        {"notification_key": "expired"},
        {"notification_key": "expired_24h_after"},
        {"notification_key": "expired_72h_after", "hours_after": 72},
        {"notification_key": "before_days", "days_left": 3},
        {"notification_key": "before_hours", "hours_before": 6},
    )
    for kwargs in lifecycle_variants:
        contents.append(
            render_subscription_lifecycle_notification(
                settings,
                language_code=language,
                message_text="Subscription lifecycle message.",
                end_date_text="2026-06-21 10:00",
                dashboard_url=dashboard_url,
                i18n=i18n,
                **kwargs,
            )
        )

    contents.extend(
        [
            render_support_new_ticket_admin(
                settings,
                i18n,
                language,
                ticket_id=42,
                user_display="user@example.com",
                subject="Connection issue",
                body_preview="Cannot connect.",
                snapshot_rows=[
                    ("email_support_row_tariff", "Premium"),
                    ("email_support_row_remaining", "3 d. 4 h."),
                ],
                ticket_url="https://app.example.com/admin/support/42",
            ),
            render_support_user_reply_admin(
                settings,
                i18n,
                language,
                ticket_id=42,
                user_display="user@example.com",
                subject="Connection issue",
                body_preview="Still cannot connect.",
                snapshot_rows=[
                    ("email_support_row_tariff", "Premium"),
                    ("email_support_row_remaining", "3 d. 4 h."),
                ],
                ticket_url="https://app.example.com/admin/support/42",
            ),
            render_support_admin_reply_user(
                settings,
                i18n,
                language,
                ticket_id=42,
                subject="Connection issue",
                body_preview="Please try again.",
                ticket_url=ticket_url,
            ),
            render_support_ticket_closed_user(
                settings,
                i18n,
                language,
                ticket_id=42,
                subject="Connection issue",
                ticket_url=ticket_url,
            ),
        ]
    )
    return contents


def test_email_locale_keys_used_by_mailers_exist_in_base_locales():
    used_keys = _used_email_locale_keys()

    assert sorted(used_keys - _locale_keys("en")) == []
    assert sorted(used_keys - _locale_keys("ru")) == []


def test_all_email_template_variants_render_without_raw_locale_keys():
    for language in ("en", "ru"):
        for content in _all_rendered_email_variants(language):
            _assert_content_is_localized(content, language)


def test_email_templates_use_default_webapp_theme_accent():
    catalog = WebappThemesConfig(
        default_theme="custom",
        themes=[
            {
                "key": "custom",
                "enabled": True,
                "default": True,
                "tokens": {"color_scheme": "dark", "accent": "#123abc"},
            }
        ],
    )
    settings = _settings("en", webapp_themes_catalog=catalog, primary_color="#00fe7a")

    content = render_login_code(
        settings,
        code="123456",
        language_code="en",
        magic_link="https://app.example.com/magic",
        purpose="login",
        i18n=_i18n("en"),
    )

    assert "color:#123abc" in content.html
    assert 'bgcolor="#123abc"' in content.html
    assert "#00fe7a" not in content.html


def test_uploaded_webapp_logo_is_embedded_inline(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    filename = "logo-1111111111111111.png"
    source = Image.new("RGBA", (24, 16), (0, 0, 0, 0))
    for x in range(6, 18):
        for y in range(4, 12):
            source.putpixel((x, y), (255, 0, 0, 255))
    logo_body = _image_bytes(source, "PNG")
    (uploads_dir / filename).write_bytes(logo_body)
    monkeypatch.setattr(email_templates_module, "_WEBAPP_UPLOADED_LOGO_DIR", uploads_dir)

    settings = _settings()
    settings.WEBAPP_LOGO_URL = f"/webapp-uploaded-logo/{filename}"

    content = render_login_code(
        settings,
        code="123456",
        language_code="en",
        purpose="login",
        i18n=_i18n("en"),
    )

    assert 'src="cid:webapp-logo@remnawave-minishop"' in content.html
    assert len(content.inline_images) == 1
    inline_logo = content.inline_images[0]
    assert inline_logo.content_id == "webapp-logo@remnawave-minishop"
    assert inline_logo.content_type == "image/png"
    assert inline_logo.data != logo_body

    with Image.open(BytesIO(inline_logo.data)) as converted:
        assert converted.mode == "RGB"
        assert converted.size == (128, 128)
        assert converted.getpixel((0, 0)) == (14, 17, 22)
        assert converted.getpixel((64, 64)) == (255, 0, 0)


def test_uploaded_webp_logo_is_embedded_as_email_safe_png(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    filename = "logo-2222222222222222.webp"
    source = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
    source.putpixel((1, 1), (255, 0, 0, 255))
    second_frame = Image.new("RGBA", (3, 3), (0, 0, 255, 255))
    (uploads_dir / filename).write_bytes(
        _image_bytes(
            source,
            "WEBP",
            save_all=True,
            append_images=[second_frame],
            duration=100,
            loop=0,
            lossless=True,
        )
    )
    monkeypatch.setattr(email_templates_module, "_WEBAPP_UPLOADED_LOGO_DIR", uploads_dir)

    settings = _settings()
    settings.WEBAPP_LOGO_URL = f"/webapp-uploaded-logo/{filename}"

    content = render_login_code(
        settings,
        code="123456",
        language_code="en",
        purpose="login",
        i18n=_i18n("en"),
    )

    assert 'src="cid:webapp-logo@remnawave-minishop"' in content.html
    assert len(content.inline_images) == 1
    inline_logo = content.inline_images[0]
    assert inline_logo.content_type == "image/png"

    with Image.open(BytesIO(inline_logo.data)) as converted:
        assert converted.mode == "RGB"
        assert converted.size == (128, 128)
        assert converted.getpixel((0, 0)) == (14, 17, 22)
        assert converted.getpixel((64, 64))[:2] == (255, 0)


def test_uploaded_svg_logo_is_not_embedded_as_email_image(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    filename = "logo-3333333333333333.svg"
    (uploads_dir / filename).write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
        '<rect width="24" height="24" fill="#00fe7a"/></svg>',
        encoding="utf-8",
    )
    monkeypatch.setattr(email_templates_module, "_WEBAPP_UPLOADED_LOGO_DIR", uploads_dir)

    settings = _settings()
    settings.WEBAPP_LOGO_URL = f"/webapp-uploaded-logo/{filename}"

    content = render_login_code(
        settings,
        code="123456",
        language_code="en",
        purpose="login",
        i18n=_i18n("en"),
    )

    assert "cid:webapp-logo" not in content.html
    assert content.inline_images == ()


def test_public_https_webapp_logo_remains_external():
    settings = _settings()
    settings.WEBAPP_LOGO_URL = "https://cdn.example.com/logo.png"

    content = render_login_code(
        settings,
        code="123456",
        language_code="en",
        purpose="login",
        i18n=_i18n("en"),
    )

    assert 'src="https://cdn.example.com/logo.png"' in content.html
    assert content.inline_images == ()


def test_support_email_templates_use_russian_copy_for_russian_recipients():
    subjects = [content.subject for content in _all_rendered_email_variants("ru")[-4:]]

    assert subjects == [
        "Новый тикет поддержки #42",
        "Новый ответ пользователя в тикете #42",
        "Новый ответ по тикету #42",
        "Тикет #42 закрыт",
    ]


def test_docs_email_preview_generator_renders_real_template_html():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "docs-site" / "scripts" / "generate-email-previews.py")],
        cwd=REPO_ROOT,
        check=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    previews = json.loads(result.stdout)

    assert len(previews) >= 20
    assert all(preview["html"].lstrip().startswith("<!DOCTYPE html>") for preview in previews)
    assert all('<html lang="ru"' in preview["html"] for preview in previews)
    assert all('role="presentation"' in preview["html"] for preview in previews)
    assert all('src="data:image/png;base64,' in preview["html"] for preview in previews)
    assert all("cid:webapp-logo" not in preview["html"] for preview in previews)
    assert all("mail-card" not in preview["html"] for preview in previews)
    assert all("email_" not in preview["subject"] + preview["html"] for preview in previews)
