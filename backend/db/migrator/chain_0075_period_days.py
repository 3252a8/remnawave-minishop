"""Add fixed-day billing without changing historical entitlement boundaries."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration

PERIOD_COLUMNS = {
    "subscriptions": (("duration_days", "duration_months"),),
    "payments": (
        ("subscription_duration_days", "subscription_duration_months"),
        ("hwid_pricing_period_days", "hwid_pricing_period_months"),
        ("promo_min_subscription_days", "promo_min_subscription_months"),
        ("checkout_charged_days", "checkout_charged_months"),
    ),
    "tribute_entitlements": (("duration_days", "duration_months"),),
    "platega_subscriptions": (("duration_days", "months"),),
    "rollypay_subscriptions": (("duration_days", "months"),),
    "promo_codes": (("min_subscription_days", "min_subscription_months"),),
    "promo_code_activations": (("charged_days", "charged_months"),),
}


def _migration_0075_add_period_days(connection: Connection) -> None:
    tables = set(inspect(connection).get_table_names())
    for table, fields in PERIOD_COLUMNS.items():
        if table not in tables:
            continue
        columns = {column["name"] for column in inspect(connection).get_columns(table)}
        for target, source in fields:
            if target not in columns:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {target} INTEGER"))
            if source not in columns:
                continue
            predicate = ""
            if table == "payments" and target in {
                "subscription_duration_days",
                "checkout_charged_days",
            }:
                predicate = (
                    " AND (sale_mode IS NULL OR sale_mode = 'subscription'"
                    " OR sale_mode LIKE 'subscription@%' OR sale_mode LIKE 'subscription|%')"
                )
            if table == "subscriptions":
                if "provider" in columns:
                    predicate += " AND (provider IS NULL OR provider <> 'trial')"
                if "status_from_panel" in columns:
                    predicate += (
                        " AND (status_from_panel IS NULL"
                        " OR status_from_panel NOT IN ('TRIAL', 'ACTIVE_BONUS'))"
                    )
            if (
                table == "payments"
                and target == "subscription_duration_days"
                and "purchased_gb" in columns
            ):
                predicate += (
                    " AND (sale_mode IS NOT NULL OR purchased_gb IS NULL OR purchased_gb = 0)"
                )
            expression = f"(CAST({source} AS BIGINT) / 12) * 365 + ({source} % 12) * 30"
            invalid = connection.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} WHERE {target} IS NULL AND {source} > 0 "
                    f"AND ({expression}) > 2147483647{predicate}"
                )
            ).scalar_one()
            if invalid:
                raise ValueError(f"{table}.{source}: period exceeds the day storage range")
            connection.execute(
                text(
                    f"UPDATE {table} SET {target} = {expression} "
                    f"WHERE {target} IS NULL AND {source} > 0{predicate}"
                )
            )
    for table in (
        "subscriptions",
        "tribute_entitlements",
        "platega_subscriptions",
        "rollypay_subscriptions",
    ):
        if table not in tables:
            continue
        columns = {column["name"] for column in inspect(connection).get_columns(table)}
        if "period_semantics" not in columns:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN period_semantics VARCHAR(32)"))
        semantics = "calendar_months" if table == "subscriptions" else "provider_managed"
        connection.execute(
            text(
                f"UPDATE {table} SET period_semantics = :semantics "
                "WHERE period_semantics IS NULL AND duration_days IS NOT NULL"
            ),
            {"semantics": semantics},
        )

    if "payments" in tables:
        columns = {column["name"] for column in inspect(connection).get_columns("payments")}
        if "subscription_terms_snapshot" not in columns:
            connection.execute(
                text("ALTER TABLE payments ADD COLUMN subscription_terms_snapshot TEXT")
            )
        if "period_semantics" not in columns:
            connection.execute(text("ALTER TABLE payments ADD COLUMN period_semantics VARCHAR(32)"))
        connection.execute(
            text(
                "UPDATE payments SET period_semantics = 'calendar_months' "
                "WHERE period_semantics IS NULL AND subscription_duration_days IS NOT NULL"
            )
        )


CHAIN_0075_PERIOD_DAYS = [
    Migration(
        id="0075_add_period_days",
        description="Add fixed-day billing periods while preserving historical dates",
        upgrade=_migration_0075_add_period_days,
    )
]
