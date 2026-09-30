from bot.services.device_names import DEVICE_NAME_MAX_LENGTH, normalize_device_name


def test_collapses_whitespace_and_line_breaks():
    assert normalize_device_name("  Work \n\t laptop\u2028 two  ") == "Work laptop two"


def test_drops_bidi_overrides_and_invisible_format_characters():
    assert normalize_device_name("ab\u202ecd\u200b\ufeff") == "abcd"


def test_keeps_zero_width_joiners_inside_emoji_sequences():
    family = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
    assert normalize_device_name(f"{family} tablet") == f"{family} tablet"


def test_composes_to_nfc_so_length_matches_what_the_user_sees():
    assert normalize_device_name("Cafe\u0301") == "Caf\u00e9"


def test_empty_values_mean_default_name():
    assert normalize_device_name(None) == ""
    assert normalize_device_name(" \n ") == ""


def test_limit_matches_the_column_width():
    from db.device_models import UserDeviceName

    assert UserDeviceName.__table__.c.name.type.length == DEVICE_NAME_MAX_LENGTH
