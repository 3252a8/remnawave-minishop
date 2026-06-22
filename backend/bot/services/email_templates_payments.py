from __future__ import annotations

import html
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings

from .email_templates_common import (
    _TEXT_DIM,
    EmailContent,
    _brand_title,
    _cta_button_html,
    _email_content,
    _format_amount,
    _format_traffic,
    _info_rows_html,
    _layout,
    _normalize_lang,
    _resolve_i18n,
    _t_html,
    _t_text,
    _theme_accent,
)


def render_payment_success(
    settings: Settings,
    *,
    language_code: Optional[str],
    sale_mode: str,
    months: int,
    traffic_gb: Optional[float],
    amount: float,
    currency: str,
    end_date_text: str,
    dashboard_url: Optional[str],
    provider_label: Optional[str] = None,
    i18n: Optional[JsonI18n] = None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language_code, settings)
    accent = _theme_accent(settings)
    brand = _brand_title(settings)
    sale_base = (sale_mode or "").split("@", 1)[0].split("|", 1)[0]
    is_traffic = sale_base in {
        "traffic",
        "traffic_package",
        "topup",
        "premium_topup",
    }
    is_hwid = sale_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}
    is_tariff_upgrade = sale_base == "tariff_upgrade"
    amount_text = _format_amount(amount, currency)
    safe_dashboard_url = (dashboard_url or "").strip()
    end_date = end_date_text or "—"
    traffic_label = _format_traffic(traffic_gb)

    subject = _t_text(i18n, lang, "email_payment_success_subject")
    preheader = _t_text(i18n, lang, "email_payment_success_preheader")
    heading = _t_text(i18n, lang, "email_payment_success_heading")
    footer_note = _t_text(i18n, lang, "email_payment_success_footer_note")
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    cta_label = _t_text(i18n, lang, "email_payment_success_cta")

    if is_traffic:
        intro_key = (
            "email_payment_success_intro_premium_topup"
            if sale_base == "premium_topup"
            else "email_payment_success_intro_traffic"
        )
        intro = _t_text(i18n, lang, intro_key, traffic_gb=traffic_label)
        period_label = _t_text(i18n, lang, "email_payment_success_row_traffic")
        period_value = _t_text(
            i18n, lang, "email_payment_success_traffic_value", traffic_gb=traffic_label
        )
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_traffic",
            amount=amount_text,
            traffic_gb=traffic_label,
            end_date=end_date,
        )
    elif is_hwid:
        devices_count = max(0, int(months or 0))
        intro = _t_text(i18n, lang, "email_payment_success_intro_hwid", count=devices_count)
        period_label = _t_text(i18n, lang, "email_payment_success_row_hwid")
        period_value = _t_text(i18n, lang, "email_payment_success_hwid_value", count=devices_count)
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_hwid",
            amount=amount_text,
            count=devices_count,
            end_date=end_date,
        )
    elif is_tariff_upgrade:
        intro = _t_text(i18n, lang, "email_payment_success_intro_tariff_upgrade")
        period_label = _t_text(i18n, lang, "email_payment_success_row_operation")
        period_value = _t_text(i18n, lang, "email_payment_success_tariff_upgrade_value")
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_tariff_upgrade",
            amount=amount_text,
            end_date=end_date,
        )
    else:
        months_int = int(months or 0)
        intro = _t_text(i18n, lang, "email_payment_success_intro_subscription", months=months_int)
        period_label = _t_text(i18n, lang, "email_payment_success_row_period")
        period_value = _t_text(
            i18n,
            lang,
            "email_payment_success_period_value",
            months=months_int,
        )
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_subscription",
            amount=amount_text,
            months=months_int,
            end_date=end_date,
        )

    rows: list[Tuple[str, str]] = [
        (period_label, period_value),
        (_t_text(i18n, lang, "email_payment_success_row_amount"), amount_text),
        (_t_text(i18n, lang, "email_payment_success_row_end_date"), end_date),
    ]
    if provider_label:
        rows.append((_t_text(i18n, lang, "email_payment_success_row_method"), provider_label))

    text_lines = [text]
    if safe_dashboard_url:
        text_lines.append(
            _t_text(i18n, lang, "email_payment_success_text_dashboard", url=safe_dashboard_url)
        )

    body_parts = [_info_rows_html(rows)]
    if safe_dashboard_url:
        body_parts.append(_cta_button_html(label=cta_label, url=safe_dashboard_url, accent=accent))
    body_parts.append(
        f'<p style="margin:6px 0 0 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(footer_note)}</p>'  # noqa: E501
    )

    rendered = _layout(
        settings=settings,
        language_code=lang,
        preheader=preheader,
        heading=heading,
        intro_html=html.escape(intro),
        body_html="".join(body_parts),
        footer_html=footer,
        accent=accent,
    )
    return _email_content(subject=subject, text="\n".join(text_lines), layout=rendered)
