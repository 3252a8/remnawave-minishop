from pathlib import Path
from unittest.mock import patch

import pytest

from config import subscription_guides_config as guides
from tests.support.settings_stub import settings_stub


def test_database_override_cannot_select_another_operator_file(tmp_path: Path) -> None:
    settings = settings_stub(SUBSCRIPTION_PAGE_CONFIG_PATH=str(tmp_path / "selected.json"))
    settings.SUBSCRIPTION_PAGE_CONFIG_PATH = str(tmp_path / "secret.json")
    with pytest.raises(guides.SubscriptionGuidesConfigError, match="outside"):
        guides.resolve_subscription_guides_config_path(settings)


def test_traversal_from_data_directory_is_rejected(tmp_path: Path) -> None:
    settings = settings_stub()
    settings.SUBSCRIPTION_PAGE_CONFIG_PATH = "data/subpage-config/../../secret.json"
    with (
        patch.object(guides, "APP_ROOT", tmp_path),
        pytest.raises(guides.SubscriptionGuidesConfigError, match="outside"),
    ):
        guides.resolve_subscription_guides_config_path(settings)


def test_large_operator_file_is_not_read_without_a_limit(tmp_path: Path) -> None:
    source = tmp_path / "large.json"
    source.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    settings = settings_stub(SUBSCRIPTION_PAGE_CONFIG_PATH=str(source))
    with pytest.raises(guides.SubscriptionGuidesConfigError, match="size limit"):
        guides._read_config_source(settings)
