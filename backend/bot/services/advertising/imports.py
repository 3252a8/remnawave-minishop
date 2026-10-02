"""Mapped CSV import, explicit revisions and explainable temporal candidates."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.advertising_models import AdExternalMetric, AdImportBatch, AdMatchCandidate, AdTouchpoint
from db.models import AdCampaign

from .capture import utc
from .validation import currency_scale, minor_units


def parse_time(value: str, timezone: ZoneInfo) -> datetime:
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid_import_timestamp") from error
    if result.tzinfo is None:
        first = result.replace(tzinfo=timezone, fold=0)
        second = result.replace(tzinfo=timezone, fold=1)
        if (
            first.utcoffset() != second.utcoffset()
            or first.astimezone(UTC).astimezone(timezone).replace(tzinfo=None) != result
        ):
            raise ValueError("ambiguous_import_timestamp")
        result = first
    return result.astimezone(UTC)


def normalize_csv(
    source: str,
    *,
    mapping: dict[str, str],
    timezone_name: str,
    account: str,
    granularity: str,
    currency: str | None = None,
    delimiter: str = ",",
) -> list[dict[str, Any]]:
    if len(source.encode("utf-8")) > 1_048_576 or delimiter not in {",", ";", "\t"}:
        raise ValueError("import_size_or_delimiter")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("invalid_import_timezone") from error
    if set(mapping) - {
        "start",
        "end",
        "advertisement",
        "impressions",
        "clicks",
        "starts",
        "cost",
        "currency",
    }:
        raise ValueError("invalid_import_mapping")
    reader = csv.DictReader(io.StringIO(source.lstrip("\ufeff")), delimiter=delimiter)
    if reader.fieldnames and len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("duplicate_import_columns")
    if not reader.fieldnames or any(
        column not in reader.fieldnames for column in mapping.values() if column
    ):
        raise ValueError("invalid_import_columns")
    if not mapping.get("start") or not mapping.get("advertisement"):
        raise ValueError("missing_import_columns")
    rows = []
    keys = set()
    for number, row in enumerate(reader, 2):
        if number > 5001:
            raise ValueError("import_row_limit")
        if None in row:
            raise ValueError("invalid_import_row")

        def cell(name: str, default: str = "", source_row: dict[str, str] = row) -> str:
            return str(source_row.get(mapping.get(name, ""), default) or default).strip()

        start = parse_time(cell("start"), timezone)
        duration = {
            "daily": timedelta(days=1),
            "minute": timedelta(minutes=1),
            "event": timedelta(microseconds=1),
        }.get(granularity)
        if duration is None and not cell("end"):
            raise ValueError("missing_import_interval_end")
        end = (
            parse_time(cell("end"), timezone)
            if cell("end")
            else (
                (start.astimezone(timezone) + timedelta(days=1)).astimezone(UTC)
                if granularity == "daily"
                else start + (duration or timedelta())
            )
        )
        if end <= start:
            raise ValueError("invalid_import_interval")
        advertisement = cell("advertisement")
        if not advertisement or len(advertisement) > 128:
            raise ValueError("invalid_import_advertisement")
        item: dict[str, Any] = {
            "account": account,
            "advertisement": advertisement,
            "interval_start": start.isoformat(),
            "interval_end": end.isoformat(),
            "granularity": granularity,
        }
        item["available_metrics"] = []
        for metric in ("impressions", "clicks", "starts"):
            if cell(metric).strip():
                item["available_metrics"].append(metric)
            try:
                item[metric] = int(
                    cell(metric, "1" if metric == "starts" and granularity == "event" else "0")
                )
            except ValueError as error:
                raise ValueError("invalid_import_counter") from error
            if item[metric] < 0 or item[metric] > 10**12:
                raise ValueError("invalid_import_counter")
        row_currency = cell("currency", currency or "").upper()
        if row_currency and not re.fullmatch(r"[A-Z]{3,8}", row_currency):
            raise ValueError("invalid_import_currency")
        if granularity == "event" and item["starts"] != 1:
            raise ValueError("aggregate_import_cannot_identify_users")
        if cell("cost") and not row_currency:
            raise ValueError("missing_import_currency")
        item["cost_minor"] = minor_units(cell("cost"), row_currency) if cell("cost") else None
        item["currency"] = row_currency or None
        item["currency_scale"] = currency_scale(row_currency)
        logical = [
            account,
            advertisement,
            item["interval_start"],
            item["interval_end"],
            granularity,
        ]
        item["logical_key"] = hashlib.sha256(json.dumps(logical).encode()).hexdigest()
        if item["logical_key"] in keys:
            raise ValueError("duplicate_import_interval")
        keys.add(item["logical_key"])
        rows.append(item)
    if not rows:
        raise ValueError("empty_import")
    ordered = sorted(rows, key=lambda item: (item["advertisement"], item["interval_start"]))
    for previous, current in pairwise(ordered):
        if (
            previous["advertisement"] == current["advertisement"]
            and previous["interval_end"] > current["interval_start"]
        ):
            raise ValueError("incompatible_import_overlap")
    return sorted(rows, key=lambda item: item["logical_key"])


async def preview_import(
    session: AsyncSession,
    *,
    campaign_id: int,
    user_id: int,
    source: str,
    mapping: dict[str, str],
    timezone_name: str,
    account: str,
    granularity: str,
    currency: str | None,
    delimiter: str,
) -> AdImportBatch:
    rows = normalize_csv(
        source,
        mapping=mapping,
        timezone_name=timezone_name,
        account=account,
        granularity=granularity,
        currency=currency,
        delimiter=delimiter,
    )
    serialized = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    batch = AdImportBatch(
        id=uuid.uuid4().hex,
        campaign_id=campaign_id,
        created_by=user_id,
        fingerprint=fingerprint,
        file_hash=hashlib.sha256(source.encode()).hexdigest(),
        account=account,
        timezone=timezone_name,
        rows_json=serialized,
        status="preview",
    )
    session.add(batch)
    await session.flush()
    return batch


async def lock_import_account(session: AsyncSession, account: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:account, 0))"),
            {"account": f"advertising-import:{account}"},
        )


async def confirm_import(session: AsyncSession, batch: AdImportBatch, *, replace: bool) -> str:
    await lock_import_account(session, batch.account)
    await session.refresh(batch)
    await session.execute(
        select(AdCampaign).where(AdCampaign.ad_campaign_id == batch.campaign_id).with_for_update()
    )
    if batch.status == "confirmed":
        return "already_confirmed"
    if batch.status != "preview":
        raise ValueError("invalid_import_state")
    duplicate = (
        await session.execute(
            select(AdImportBatch.id).where(
                AdImportBatch.fingerprint == batch.fingerprint,
                AdImportBatch.account == batch.account,
                AdImportBatch.status == "confirmed",
            )
        )
    ).first()
    if duplicate:
        raise ValueError("duplicate_import")
    rows = json.loads(batch.rows_json)
    for row in rows:
        start, end = (
            datetime.fromisoformat(row["interval_start"]),
            datetime.fromisoformat(row["interval_end"]),
        )
        current = list(
            (
                await session.execute(
                    select(AdExternalMetric).where(
                        AdExternalMetric.account == row["account"],
                        AdExternalMetric.advertisement == row["advertisement"],
                        AdExternalMetric.is_current.is_(True),
                        AdExternalMetric.interval_start < end,
                        AdExternalMetric.interval_end > start,
                    )
                )
            ).scalars()
        )
        if current and not replace:
            raise ValueError("import_revision_requires_confirmation")
        if any(metric.logical_key != row["logical_key"] for metric in current):
            raise ValueError("incompatible_import_overlap")
        for metric in current:
            metric.is_current = False
        await session.flush()
        values = dict(row)
        values.pop("available_metrics", None)
        values["interval_start"], values["interval_end"] = start, end
        session.add(AdExternalMetric(batch_id=batch.id, **values))
    batch.status = "confirmed"
    await session.flush()
    return "confirmed"


async def revert_import(session: AsyncSession, batch: AdImportBatch) -> None:
    await lock_import_account(session, batch.account)
    await session.refresh(batch)
    await session.execute(
        select(AdCampaign).where(AdCampaign.ad_campaign_id == batch.campaign_id).with_for_update()
    )
    if batch.status == "reverted":
        return
    if batch.status != "confirmed":
        raise ValueError("invalid_import_state")
    metrics = list(
        (
            await session.execute(
                select(AdExternalMetric).where(AdExternalMetric.batch_id == batch.id)
            )
        ).scalars()
    )
    batch.status = "reverted"
    for metric in metrics:
        if not metric.is_current:
            continue
        metric.is_current = False
        await session.flush()
        previous = (
            await session.execute(
                select(AdExternalMetric)
                .join(AdImportBatch)
                .where(
                    AdExternalMetric.logical_key == metric.logical_key,
                    AdImportBatch.status == "confirmed",
                    AdImportBatch.id != batch.id,
                )
                .order_by(AdImportBatch.created_at.desc(), AdExternalMetric.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if previous:
            previous.is_current = True
    await session.execute(
        update(AdMatchCandidate)
        .where(AdMatchCandidate.batch_id == batch.id)
        .values(status="reverted")
    )


async def build_candidates(
    session: AsyncSession, batch: AdImportBatch, *, bot_id: str, window_seconds: int
) -> None:
    await lock_import_account(session, batch.account)
    await session.refresh(batch)
    if batch.status != "confirmed":
        raise ValueError("invalid_import_state")
    rows = json.loads(batch.rows_json)
    if any(row["granularity"] != "event" for row in rows):
        raise ValueError("aggregate_import_cannot_identify_users")
    existing = (
        await session.execute(
            select(AdMatchCandidate.id).where(AdMatchCandidate.batch_id == batch.id)
        )
    ).first()
    if existing:
        return
    for row in rows:
        occurred = datetime.fromisoformat(row["interval_start"])
        touches = list(
            (
                await session.execute(
                    select(AdTouchpoint).where(
                        AdTouchpoint.channel == "bot",
                        AdTouchpoint.bot_id == bot_id,
                        AdTouchpoint.occurred_at >= occurred - timedelta(seconds=window_seconds),
                        AdTouchpoint.occurred_at <= occurred + timedelta(seconds=window_seconds),
                    )
                )
            ).scalars()
        )
        if not touches:
            session.add(
                AdMatchCandidate(
                    batch_id=batch.id,
                    event_key=row["logical_key"],
                    status="unmatched",
                    reason="no_local_start",
                    window_seconds=window_seconds,
                    bot_id=bot_id,
                )
            )
        for touch in touches:
            competing = (
                await session.execute(
                    select(AdExternalMetric.id)
                    .join(AdImportBatch)
                    .where(
                        AdImportBatch.status == "confirmed",
                        AdExternalMetric.is_current.is_(True),
                        AdExternalMetric.granularity == "event",
                        AdExternalMetric.logical_key != row["logical_key"],
                        AdExternalMetric.interval_start
                        >= utc(touch.occurred_at) - timedelta(seconds=window_seconds),
                        AdExternalMetric.interval_start
                        <= utc(touch.occurred_at) + timedelta(seconds=window_seconds),
                    )
                    .limit(1)
                )
            ).first()
            session.add(
                AdMatchCandidate(
                    batch_id=batch.id,
                    event_key=row["logical_key"],
                    touchpoint_id=touch.id,
                    status="candidate" if len(touches) == 1 and not competing else "ambiguous",
                    delta_seconds=int((utc(touch.occurred_at) - occurred).total_seconds()),
                    reason="temporal_identity_unproven"
                    if len(touches) == 1 and not competing
                    else "competing_events",
                    window_seconds=window_seconds,
                    bot_id=bot_id,
                )
            )
    await session.flush()


def export_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        safe = {
            key: "'" + value
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
            else value
            for key, value in row.items()
        }
        writer.writerow(safe)
    return output.getvalue()
