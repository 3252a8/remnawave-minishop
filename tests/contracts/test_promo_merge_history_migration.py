from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from db.migrator.chain_0103_promo_activation_merge_history import (
    _migration_0103_promo_activation_merge_history,
)
from db.models import PromoCodeActivation


def test_upgrade_preserves_old_records_and_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE promo_code_activations ("
                "activation_id INTEGER PRIMARY KEY, promo_code_id INTEGER NOT NULL, "
                "user_id BIGINT NOT NULL, is_manual_override BOOLEAN NOT NULL DEFAULT FALSE)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_promo_user_activation_standard "
                "ON promo_code_activations (promo_code_id, user_id) "
                "WHERE is_manual_override = FALSE"
            )
        )
        connection.execute(text("INSERT INTO promo_code_activations VALUES (1, 5, 42, FALSE)"))
        _migration_0103_promo_activation_merge_history(connection)
        _migration_0103_promo_activation_merge_history(connection)
        columns = {
            column["name"] for column in inspect(connection).get_columns("promo_code_activations")
        }
        assert "merged_from_user_id" in columns
        assert connection.execute(text("SELECT * FROM promo_code_activations")).one() == (
            1,
            5,
            42,
            False,
            None,
        )
        connection.execute(text("INSERT INTO promo_code_activations VALUES (2, 5, 42, FALSE, -7)"))
        _migration_0103_promo_activation_merge_history(connection)
        try:
            connection.execute(
                text("INSERT INTO promo_code_activations VALUES (3, 5, 42, FALSE, NULL)")
            )
        except IntegrityError:
            pass
        else:
            raise AssertionError("The standard per-user redemption guard was lost")
    engine.dispose()


def test_upgrade_skips_an_absent_table():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        _migration_0103_promo_activation_merge_history(connection)
        assert inspect(connection).get_table_names() == []
    engine.dispose()


def test_postgres_model_index_distinguishes_history_from_a_new_redemption():
    index = next(
        index
        for index in PromoCodeActivation.__table__.indexes
        if index.name == "uq_promo_user_activation_standard"
    )
    predicate = str(
        index.dialect_options["postgresql"]["where"].compile(dialect=postgresql.dialect())
    )
    assert "is_manual_override IS false" in predicate
    assert "merged_from_user_id IS NULL" in predicate
    assert index.unique
