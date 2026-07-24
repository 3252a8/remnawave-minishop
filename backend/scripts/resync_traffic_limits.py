"""One-shot fleet resync of main traffic limits.

Recomputes every active subscription's traffic limit through the SAME
production code path a purchase/renewal would use — including the
active package traffic bonuses and the unlimited-tariff guard — and
pushes changed limits to the panel.

DRY RUN by default (prints what would change, writes nothing).
Set APPLY=1 in the environment to actually apply.
"""

import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_service import PanelApiService
from bot.services.settings_override_service import load_overrides_from_db
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.dal import tariff_dal
from db.database_setup import init_db_connection
from db.models import Subscription

APPLY = os.environ.get("APPLY") == "1"
GB = 1024**3


def _gb(value: int | None) -> str:
    v = int(value or 0)
    return "unlimited" if v == 0 else f"{v / GB:g} GB"


async def _target_limit(
    svc: SubscriptionService,
    session: AsyncSession,
    sub: Subscription,
) -> tuple[int, int]:
    """Read-only mirror of sync_main_traffic_limit_to_panel's computation."""
    tariff = svc._resolve_tariff(sub.tariff_key) if sub.tariff_key else None
    baseline = int(sub.tier_baseline_bytes or (tariff.monthly_bytes if tariff else 0) or 0)
    summary = await tariff_dal.get_hwid_device_entitlement_summary(
        session, subscription_id=sub.subscription_id, at=datetime.now(UTC)
    )
    extras = int(summary.get("active_devices") or 0)
    return svc._compute_main_traffic_limit_bytes(
        tier_baseline_bytes=baseline,
        topup_balance_bytes=int(sub.topup_balance_bytes or 0),
        regular_bonus_bytes=int(getattr(sub, "regular_bonus_bytes", 0) or 0),
        regular_unlimited_override=bool(getattr(sub, "regular_unlimited_override", False)),
        traffic_used_bytes=int(getattr(sub, "traffic_used_bytes", 0) or 0),
        hwid_device_bonus_bytes=svc._hwid_traffic_bonus_bytes_from_summary(summary),
    ), extras


async def main() -> None:
    settings = Settings()
    session_factory = init_db_connection(settings)
    overrides = await load_overrides_from_db(settings, session_factory)
    bonus_gb = float(settings.HWID_DEVICE_TRAFFIC_BONUS_GB)
    print(f"mode: {'APPLY' if APPLY else 'DRY RUN'}")
    print(f"settings overrides applied from DB: {overrides}")
    print(f"legacy HWID_DEVICE_TRAFFIC_BONUS_GB fallback = {bonus_gb}")

    panel = PanelApiService(settings)
    svc = SubscriptionService(settings, panel, None, None)
    try:
        async with session_factory() as session:
            subs = (
                (
                    await session.execute(
                        select(Subscription).where(
                            Subscription.is_active == True,
                            Subscription.end_date > datetime.now(UTC),
                        )
                    )
                )
                .scalars()
                .all()
            )
            print(f"active subscriptions: {len(subs)}")
            plan: list[tuple[int, int, int, int]] = []
            for sub in subs:
                target, extras = await _target_limit(svc, session, sub)
                current = int(sub.traffic_limit_bytes or 0)
                if target != current:
                    plan.append((sub.user_id, current, target, extras))

        if not plan:
            print("nothing to change — every active limit already matches the model.")
            return
        print(f"limits that differ from the model: {len(plan)}")
        for user_id, current, target, extras in plan:
            print(
                f"  user {user_id}: {_gb(current)} -> {_gb(target)} "
                f"(active extra devices: {extras})"
            )

        if not APPLY:
            print("dry run complete. rerun with APPLY=1 to apply.")
            return

        changed = 0
        for user_id, current, target, _extras in plan:
            async with session_factory() as session:
                ok = await svc.sync_main_traffic_limit_to_panel(session, user_id)
                if ok:
                    await session.commit()
                    changed += 1
                    print(f"  applied user {user_id}: {_gb(current)} -> {_gb(target)}")
                else:
                    await session.rollback()
                    print(f"  !! FAILED user {user_id} (panel refused / user missing) — unchanged")
            await asyncio.sleep(0.2)
        print(f"done: {changed}/{len(plan)} applied.")
    finally:
        await panel.close()


if __name__ == "__main__":
    asyncio.run(main())
