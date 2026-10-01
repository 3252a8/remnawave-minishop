import pytest

from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    _sanitize_svg,
    default_subscription_guides_config_text,
    validate_subscription_guides_config_text,
)


@pytest.mark.parametrize(
    "svg",
    [
        '<svg/onload="alert(1)"></svg>',
        '<svg onload="alert(1)"></svg>',
        '<svg><animate attributeName="onload" values="alert(1)"/></svg>',
        '<svg><path style="fill:url(https://evil.test/a)"/></svg>',
        '<svg><path fill="url(https://evil.test/a)"/></svg>',
        '<svg xmlns:x="http://evil.test"><x:path/></svg>',
        '<!DOCTYPE svg [<!ENTITY x "a">]><svg>&x;</svg>',
    ],
)
def test_active_or_malformed_svg_is_rejected(svg: str) -> None:
    with pytest.raises(SubscriptionGuidesConfigError):
        _sanitize_svg(svg, "icon")


def test_bundled_icons_and_local_geometry_remain_usable() -> None:
    assert validate_subscription_guides_config_text(default_subscription_guides_config_text())
    icon = '<svg viewBox="0 0 24 24"><path d="M0 0 L2 2" fill="currentColor"/></svg>'
    assert _sanitize_svg(icon, "icon") == icon
