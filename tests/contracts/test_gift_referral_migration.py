from sqlalchemy import create_engine, text

from db.migrator.chain_0104_gift_referral_qualification import (
    _migration_0104_gift_referral_qualification,
)


def test_old_activations_are_not_qualified_and_upgrade_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE subscription_gifts (gift_id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO subscription_gifts VALUES (8)"))
        connection.execute(
            text("CREATE TABLE referral_period_accruals (accrual_id INTEGER PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO referral_period_accruals VALUES (1)"))
        _migration_0104_gift_referral_qualification(connection)
        _migration_0104_gift_referral_qualification(connection)
        assert (
            connection.execute(text("SELECT referral_qualified FROM subscription_gifts")).scalar()
            == 0
        )
        assert (
            connection.execute(text("SELECT gift_id FROM referral_period_accruals")).scalar()
            is None
        )
    engine.dispose()
