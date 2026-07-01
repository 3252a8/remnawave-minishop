from bot.handlers.admin.promo.manage import _single_effect_update


def test_single_effect_update_clears_other_effect_fields_for_discount():
    update_data = {"discount_percent": 15.0}

    _single_effect_update("discount_percent", update_data)

    assert update_data == {
        "bonus_days": 0,
        "discount_percent": 15.0,
        "duration_multiplier": None,
        "traffic_multiplier": None,
    }


def test_single_effect_update_keeps_other_effects_when_resetting_multiplier():
    update_data = {"duration_multiplier": 1.0}

    _single_effect_update("duration_multiplier", update_data)

    assert update_data == {"duration_multiplier": 1.0}
