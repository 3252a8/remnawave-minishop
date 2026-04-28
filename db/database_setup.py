import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from config.settings import Settings
from db.models import Base
from .migrator import run_database_migrations

async_engine = None


def init_db_connection(settings: Settings) -> sessionmaker:
    global async_engine

    if async_engine is None:
        logging.info(
            f"Attempting to create SQLAlchemy engine with URL: {settings.DATABASE_URL}"
        )
        async_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=10,
        )

    local_async_session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    logging.info(
        f"SQLAlchemy Async Engine and SessionFactory configured for PostgreSQL."
    )
    return local_async_session_factory


async def get_async_session(session_factory: sessionmaker) -> AsyncSession:

    if session_factory is None:
        raise RuntimeError(
            "AsyncSessionFactory is not provided or initialized.")

    async_session = session_factory()
    try:
        yield async_session
    finally:
        await async_session.close()


async def init_db(settings: Settings, session_factory: sessionmaker):

    global async_engine
    if async_engine is None:

        logging.warning(
            "init_db: async_engine was None, re-initializing via init_db_connection."
        )

        raise RuntimeError(
            "async_engine is not initialized. Call init_db_connection and get session_factory first."
        )

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_database_migrations)
    logging.info(
        "PostgreSQL database initialized/checked successfully using SQLAlchemy."
    )

    async with session_factory() as session:
        from .dal.panel_sync_dal import get_panel_sync_status, update_panel_sync_status
        from sqlalchemy import text
        try:
            current_status = await get_panel_sync_status(session)
            if current_status is None:
                logging.info("Initializing panel_sync_status record.")
                await update_panel_sync_status(session,
                                               status="never_run",
                                               details="System initialized",
                                               users_processed=0,
                                               subs_synced=0)
                await session.commit()
        except Exception as e_sync_init:
            await session.rollback()
            logging.error(
                f"Failed to initialize PanelSyncStatus: {e_sync_init}",
                exc_info=True)

        if settings.tariffs_config:
            try:
                default_tariff = settings.tariffs_config.default
                default_price = default_tariff.period_price(1, "rub") or default_tariff.min_period_price_rub()
                await session.execute(
                    text(
                        """
                        UPDATE subscriptions AS s
                        SET
                            tariff_key = COALESCE(s.tariff_key, :tariff_key),
                            tier_baseline_bytes = COALESCE(s.tier_baseline_bytes, s.traffic_limit_bytes, :baseline),
                            topup_balance_bytes = COALESCE(s.topup_balance_bytes, 0),
                            period_start_at = NULL,
                            effective_monthly_price_rub = COALESCE(
                                s.effective_monthly_price_rub,
                                (
                                    SELECT p.amount / GREATEST(COALESCE(p.subscription_duration_months, 1), 1)
                                    FROM payments p
                                    WHERE p.user_id = s.user_id
                                      AND p.status = 'succeeded'
                                      AND COALESCE(p.subscription_duration_months, 0) > 0
                                    ORDER BY p.created_at DESC
                                    LIMIT 1
                                ),
                                :default_price
                            )
                        WHERE s.is_active = TRUE
                          AND s.tariff_key IS NULL
                        """
                    ),
                    {
                        "tariff_key": default_tariff.key,
                        "baseline": default_tariff.monthly_bytes,
                        "default_price": default_price,
                    },
                )
                await session.execute(
                    text(
                        """
                        UPDATE subscriptions
                        SET period_start_at = NULL
                        WHERE is_active = TRUE
                          AND tariff_key IS NOT NULL
                        """
                    )
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception("Failed to backfill existing subscriptions for tariffs config.")
