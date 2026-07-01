from bot.handlers.user.subscription.core_status import (
    _devices_count_from_panel_response,
    _devices_list_from_panel_response,
)


def test_devices_helpers_accept_remnawave_devices_object():
    response = {"response": {"total": 2, "devices": [{"hwid": "a"}, {"hwid": "b"}]}}

    assert _devices_list_from_panel_response(response) == [{"hwid": "a"}, {"hwid": "b"}]
    assert _devices_count_from_panel_response(response) == 2


def test_devices_helpers_keep_empty_list_as_zero_devices():
    assert _devices_list_from_panel_response([]) == []
    assert _devices_count_from_panel_response([]) == 0
