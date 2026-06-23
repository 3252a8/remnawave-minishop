from db.dal import support_dal


def test_support_dal_status_groups_are_future_close_ready():
    assert "closed" in support_dal.CLOSED_STATUSES
    assert "resolved" in support_dal.CLOSED_STATUSES
    assert "awaiting_admin" in support_dal.ACTIVE_STATUSES


def test_support_dal_all_status_filter_means_no_filter():
    assert support_dal._status_condition("all") is None
    assert support_dal._status_condition("any") is None
