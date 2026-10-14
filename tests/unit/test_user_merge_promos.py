from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, noload, selectinload

from db.dal import promo_code_dal
from db.dal.user_merge_promos import merge_promo_activation_history
from db.models import Payment, PromoCode, PromoCodeActivation, User


class _AsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, statement: Any) -> Any:
        return self._session.execute(statement)

    def add(self, instance: Any) -> None:
        self._session.add(instance)

    def expire(self, instance: Any, attributes: list[str]) -> None:
        self._session.expire(instance, attributes)

    async def flush(self) -> None:
        self._session.flush()

    async def refresh(self, instance: Any) -> None:
        self._session.refresh(instance)


@pytest.fixture
def store() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    User.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            PromoCode.__table__,
            Payment.__table__,
            PromoCodeActivation.__table__,
        ],
    )
    with Session(engine) as session:
        session.add_all([User(user_id=user_id) for user_id in (-7, 42, 99)])
        session.add_all(
            [
                PromoCode(
                    promo_code_id=code_id,
                    code=f"SHARED{code_id}",
                    bonus_days=3,
                    max_activations=100,
                    current_activations=2,
                )
                for code_id in (1, 2)
            ]
        )
        session.commit()
        yield session
    engine.dispose()


def _history(store: Session, user_id: int, *, manual: bool = False, code_id: int = 1) -> int:
    row = PromoCodeActivation(
        promo_code_id=code_id,
        user_id=user_id,
        is_manual_override=manual,
        payment_id=1000 + abs(user_id),
        activated_at=datetime(2025, 1, 2, tzinfo=UTC),
        effect_summary="-25%; +3 days",
        discount_percent=25,
        granted_days=3,
    )
    store.add(row)
    store.flush()
    return int(row.activation_id)


def _merge(store: Session, source_id: int, target_id: int) -> None:
    source = store.get(User, source_id)
    target = store.get(User, target_id)
    assert source is not None and target is not None
    asyncio.run(
        merge_promo_activation_history(
            cast(AsyncSession, _AsyncSessionAdapter(store)), source, target
        )
    )


def _activation(store: Session, activation_id: int) -> PromoCodeActivation:
    row = store.get(PromoCodeActivation, activation_id)
    assert row is not None
    return row


def _promo(store: Session, promo_id: int = 1) -> PromoCode:
    row = store.get(PromoCode, promo_id)
    assert row is not None
    return row


def test_shared_code_keeps_both_snapshots_payment_links_counts_and_normal_reuse_guard(
    store: Session,
) -> None:
    source_id = _history(store, -7)
    target_id = _history(store, 42)
    store.commit()

    _merge(store, -7, 42)
    store.commit()

    source = store.get(PromoCodeActivation, source_id)
    target = store.get(PromoCodeActivation, target_id)
    assert source is not None and target is not None
    assert source.user_id == target.user_id == 42
    assert source.merged_from_user_id == -7
    assert target.merged_from_user_id is None
    assert source.is_manual_override is False and target.is_manual_override is False
    assert source.payment_id == 1007 and target.payment_id == 1042
    assert source.effect_summary == target.effect_summary == "-25%; +3 days"
    assert source.granted_days == target.granted_days == 3
    assert _promo(store).current_activations == 2
    adapter = cast(AsyncSession, _AsyncSessionAdapter(store))
    assert (
        asyncio.run(promo_code_dal.consume_promo_activation(adapter, 1, 42, payment_id=9999))
        is None
    )
    assert _promo(store).current_activations == 2
    assert store.scalar(select(func.count()).select_from(PromoCodeActivation)) == 2


@pytest.mark.parametrize(
    "source_manual,target_manual", [(False, True), (True, False), (True, True)]
)
def test_manual_history_keeps_its_original_flags_without_a_unique_conflict(
    store: Session, source_manual: bool, target_manual: bool
) -> None:
    source_id = _history(store, -7, manual=source_manual)
    _history(store, 42, manual=target_manual)
    _merge(store, -7, 42)
    store.commit()
    source = _activation(store, source_id)
    assert source.is_manual_override is source_manual
    assert source.merged_from_user_id is None
    assert store.scalar(select(func.count()).select_from(PromoCodeActivation)) == 2


def test_different_codes_move_as_standard_redemptions(store: Session) -> None:
    source_id = _history(store, -7, code_id=2)
    _history(store, 42)
    _merge(store, -7, 42)
    store.commit()
    source = _activation(store, source_id)
    assert source.user_id == 42 and source.merged_from_user_id is None


def test_followup_merge_keeps_each_historical_origin_and_payment_replay_is_idempotent(
    store: Session,
) -> None:
    source_id = _history(store, -7)
    target_id = _history(store, 42)
    final_id = _history(store, 99)
    promo = store.get(PromoCode, 1)
    assert promo is not None
    promo.current_activations = 3
    store.commit()
    _merge(store, -7, 42)
    _merge(store, 42, 99)
    store.commit()
    assert _activation(store, source_id).merged_from_user_id == -7
    assert _activation(store, target_id).merged_from_user_id == 42
    assert _activation(store, final_id).merged_from_user_id is None
    adapter = cast(AsyncSession, _AsyncSessionAdapter(store))
    for payment_id in (1007, 1042, 1099):
        activation = asyncio.run(
            promo_code_dal.consume_promo_activation(adapter, 1, 99, payment_id=payment_id)
        )
        assert activation is not None and activation.payment_id == payment_id
    assert _promo(store).current_activations == 3
    assert store.scalar(select(func.count()).select_from(PromoCodeActivation)) == 3


def test_merge_rollback_restores_ownership_and_provenance(store: Session) -> None:
    source_id = _history(store, -7)
    _history(store, 42)
    store.commit()
    _merge(store, -7, 42)
    store.rollback()
    source = _activation(store, source_id)
    assert source.user_id == -7 and source.merged_from_user_id is None


def test_source_deletion_does_not_cascade_preloaded_transferred_history(store: Session) -> None:
    source_id = _history(store, -7)
    _history(store, 42)
    store.commit()
    # Only promo-related tables are needed here; other empty relationships do
    # not take part in this regression.
    source = store.scalars(
        select(User)
        .where(User.user_id == -7)
        .options(noload("*"), selectinload(User.promo_code_activations))
    ).one()
    assert len(source.promo_code_activations) == 1
    _merge(store, -7, 42)
    store.delete(source)
    store.commit()
    assert _activation(store, source_id).user_id == 42
    assert store.scalar(select(func.count()).select_from(PromoCodeActivation)) == 2


def test_standard_unique_guard_still_rejects_a_fresh_second_redemption(store: Session) -> None:
    _history(store, 42)
    store.commit()
    with pytest.raises(IntegrityError):
        _history(store, 42)
    store.rollback()


def test_historical_redemption_still_blocks_reuse_after_canonical_payment_is_released(
    store: Session,
) -> None:
    source_id = _history(store, -7)
    _history(store, 42)
    store.commit()
    _merge(store, -7, 42)
    adapter = cast(AsyncSession, _AsyncSessionAdapter(store))
    assert asyncio.run(promo_code_dal.release_promo_activation(adapter, 1, 42, payment_id=1042))
    assert _activation(store, source_id).merged_from_user_id == -7
    assert _promo(store).current_activations == 1
    assert (
        asyncio.run(promo_code_dal.consume_promo_activation(adapter, 1, 42, payment_id=9999))
        is None
    )
    assert _promo(store).current_activations == 1


def test_explicit_admin_override_remains_distinct_from_merge_history(store: Session) -> None:
    source_id = _history(store, -7)
    _history(store, 42)
    store.commit()
    _merge(store, -7, 42)
    adapter = cast(AsyncSession, _AsyncSessionAdapter(store))
    activation = asyncio.run(
        promo_code_dal.consume_promo_activation(
            adapter, 1, 42, payment_id=9999, allow_existing_user=True
        )
    )
    assert activation is not None and activation.is_manual_override is True
    assert activation.merged_from_user_id is None
    assert _activation(store, source_id).is_manual_override is False
    assert _activation(store, source_id).merged_from_user_id == -7
    assert _promo(store).current_activations == 3
