"""Public advertising audience filters select a single evidence row."""

from datetime import UTC, datetime

import pytest

from bot.services.advertising.audience import audience_query, normalize_filters


def test_utm_case_and_quotes_remain_bound_data() -> None:
    value = "Partner's Channel'); SELECT 1; --"
    query = audience_query({"utm_source": value}, now=datetime.now(UTC))
    assert value not in query.sql
    assert value in query.params.values()
    assert normalize_filters({"utm_source": "YouTube"})["utm_source"] == "YouTube"


@pytest.mark.parametrize(
    "filters",
    [
        {"ad_model": "unknown"},
        {"ad_campaign_id": "-1"},
        {"ad_link_id": True},
        {"ad_campaign_id": "９"},
        {"utm_source": "bad\ninvalid"},
        {"unknown": "a"},
    ],
)
def test_invalid_filters_fail_closed(filters: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        normalize_filters(filters)


def test_query_namespaces_allow_segment_and_source_conditions_in_one_query() -> None:
    first = audience_query({}, namespace="segment")
    last = audience_query({"ad_model": "last_purchase"}, namespace="filter")
    assert not first.params.keys() & last.params.keys()
    with pytest.raises(ValueError):
        audience_query({}, namespace="invalid; SELECT")
