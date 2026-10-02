"""Public, read-only advertising audience and customer-context contract.

Filters apply to one selected evidence row, never to different visits. SQL is
compiled by Core so extensions do not depend on advertising table layouts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, cast, exists, func, literal, select, union_all
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import CTE

from db.advertising_models import AdLink, AdPurchaseAttribution, AdTouchpoint
from db.models import AdAttribution, AdCampaign

AUDIENCE_CONTRACT_VERSION = 1
MODELS = ("first_touch", "last_touch", "last_purchase")
FILTER_KEYS = (
    "ad_model",
    "ad_campaign_id",
    "ad_link_id",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
)


@dataclass(frozen=True)
class AdvertisingAudienceQuery:
    sql: str
    params: dict[str, Any]


def normalize_filters(values: Mapping[str, Any]) -> dict[str, str]:
    """Validate exact, case-sensitive UTM values and positive entity IDs."""
    result: dict[str, str] = {}
    for key, raw in values.items():
        if key not in FILTER_KEYS:
            raise ValueError("advertising_filter_invalid")
        if not isinstance(raw, (str, int)) or isinstance(raw, bool):
            raise ValueError("advertising_filter_invalid")
        value = str(raw).strip()
        if not value:
            continue
        if key == "ad_model" and value not in MODELS:
            raise ValueError("advertising_model_invalid")
        if key in {"ad_campaign_id", "ad_link_id"}:
            if not value.isascii() or not value.isdecimal() or not 0 < int(value) < 2**31:
                raise ValueError("advertising_id_invalid")
            value = str(int(value))
        elif key.startswith("utm_") and (len(value) > 256 or any(ord(c) < 32 for c in value)):
            raise ValueError("advertising_utm_invalid")
        result[key] = value
    if result:
        result.setdefault("ad_model", "first_touch")
    return result


def _context_rows(model: str, now: datetime) -> CTE:
    if model == "last_purchase":
        rows = (
            select(
                AdPurchaseAttribution.user_id,
                AdPurchaseAttribution.campaign_id,
                AdPurchaseAttribution.link_id,
                func.coalesce(AdTouchpoint.observed_utm_json, "{}").label("utm_json"),
                func.coalesce(AdTouchpoint.channel, "checkout").label("channel"),
                AdPurchaseAttribution.evidence,
                AdPurchaseAttribution.succeeded_at.label("occurred_at"),
                AdPurchaseAttribution.payment_id.label("row_id"),
                AdPurchaseAttribution.payment_id,
                AdPurchaseAttribution.policy_version,
            )
            .outerjoin(AdTouchpoint, AdTouchpoint.id == AdPurchaseAttribution.touchpoint_id)
            .where(
                AdPurchaseAttribution.succeeded_at.is_not(None),
                AdPurchaseAttribution.succeeded_at <= now,
                AdPurchaseAttribution.product_order.is_(True),
            )
            .cte("advertising_evidence")
        )
    else:
        touches = select(
            AdTouchpoint.user_id,
            AdTouchpoint.campaign_id,
            AdTouchpoint.link_id,
            AdTouchpoint.observed_utm_json.label("utm_json"),
            AdTouchpoint.channel,
            AdTouchpoint.evidence,
            AdTouchpoint.occurred_at,
            AdTouchpoint.id.label("row_id"),
            cast(literal(None), String).label("payment_id"),
            cast(literal(None), String).label("policy_version"),
        ).where(
            AdTouchpoint.user_id.is_not(None),
            AdTouchpoint.occurred_at <= now,
            AdTouchpoint.evidence != "unassigned_bot_start",
        )
        # A legacy projection must survive even when a user later acquires a
        # different source. Skip only its exact modern evidence counterpart.
        legacy = select(
            AdAttribution.user_id,
            AdAttribution.ad_campaign_id.label("campaign_id"),
            literal(None).label("link_id"),
            literal("{}").label("utm_json"),
            literal("bot").label("channel"),
            literal("legacy_first_start").label("evidence"),
            AdAttribution.first_start_at.label("occurred_at"),
            literal(0).label("row_id"),
            cast(literal(None), String).label("payment_id"),
            cast(literal(None), String).label("policy_version"),
        ).where(
            AdAttribution.first_start_at <= now,
            ~exists(
                select(AdTouchpoint.id).where(
                    AdTouchpoint.user_id == AdAttribution.user_id,
                    AdTouchpoint.campaign_id == AdAttribution.ad_campaign_id,
                    AdTouchpoint.occurred_at == AdAttribution.first_start_at,
                )
            ),
        )
        rows = union_all(touches, legacy).cte("advertising_evidence")
    order: list[ColumnElement[Any]] = [rows.c.occurred_at, rows.c.row_id]
    if model != "first_touch":
        order = [column.desc() for column in order]
    ranked = select(
        rows, func.row_number().over(partition_by=rows.c.user_id, order_by=order).label("rank")
    ).cte("advertising_ranked")
    return select(ranked).where(ranked.c.rank == 1).cte("advertising_context")


def audience_query(
    values: Mapping[str, Any], *, now: datetime | None = None, namespace: str = "advertising"
) -> AdvertisingAudienceQuery:
    """Return a parameterized user-ID query suitable for an audience subquery."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", namespace):
        raise ValueError("advertising_namespace_invalid")
    filters = normalize_filters(values)
    rows = _context_rows(filters.get("ad_model", "first_touch"), now or datetime.now(UTC))
    statement = select(rows.c.user_id)
    for key in ("ad_campaign_id", "ad_link_id"):
        if key in filters:
            statement = statement.where(rows.c[key.removeprefix("ad_")] == int(filters[key]))
    for key in FILTER_KEYS[3:]:
        if key in filters:
            statement = statement.where(
                cast(rows.c.utm_json, postgresql.JSONB)[key].astext == filters[key]
            )
    compiled = statement.compile(dialect=postgresql.dialect(paramstyle="named"))
    sql = str(compiled)
    params: dict[str, Any] = {}
    for key, value in compiled.params.items():
        name = f"{namespace}_{key}"
        sql = re.sub(rf":{re.escape(key)}(?![a-zA-Z0-9_])", ":" + name, sql)
        params[name] = value
    return AdvertisingAudienceQuery(sql, params)


async def customer_contexts(
    session: AsyncSession, user_ids: Sequence[int]
) -> dict[int, dict[str, Any]]:
    """Batch contexts without exposing ORM objects or anonymous visit identifiers."""
    result: dict[int, dict[str, Any]] = {
        int(user_id): dict.fromkeys(MODELS) for user_id in user_ids
    }
    if not result:
        return result
    for model in MODELS:
        rows = _context_rows(model, datetime.now(UTC))
        statement = (
            select(
                rows,
                func.coalesce(func.nullif(AdCampaign.name, ""), AdCampaign.source).label(
                    "campaign_name"
                ),
                AdLink.label.label("link_label"),
            )
            .select_from(rows)
            .outerjoin(AdCampaign, AdCampaign.ad_campaign_id == rows.c.campaign_id)
            .outerjoin(AdLink, AdLink.id == rows.c.link_id)
            .where(rows.c.user_id.in_(result))
        )
        for row in (await session.execute(statement)).mappings():
            utm = json.loads(str(row["utm_json"] or "{}"))
            occurred_at = row["occurred_at"]
            result[int(row["user_id"])][model] = {
                "campaign_id": row["campaign_id"],
                "campaign_name": row["campaign_name"],
                "link_id": row["link_id"],
                "link_label": row["link_label"],
                "utm": utm if isinstance(utm, dict) else {},
                "channel": row["channel"],
                "evidence": row["evidence"],
                "occurred_at": occurred_at.isoformat(),
                "payment_id": row["payment_id"],
                "policy_version": row["policy_version"],
            }
    return result


async def audience_options(session: AsyncSession) -> dict[str, Any]:
    campaigns = (
        await session.execute(select(AdCampaign).order_by(AdCampaign.ad_campaign_id))
    ).scalars()
    links = (await session.execute(select(AdLink).order_by(AdLink.id))).scalars()
    return {
        "available": True,
        "contract_version": AUDIENCE_CONTRACT_VERSION,
        "models": list(MODELS),
        "campaigns": [
            {"id": row.ad_campaign_id, "name": row.name or row.source} for row in campaigns
        ],
        "links": [
            {"id": row.id, "campaign_id": row.campaign_id, "label": row.label or row.code}
            for row in links
        ],
    }
