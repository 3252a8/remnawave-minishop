"""When the cabinet offers the auto-renew switch."""

import unittest
from typing import Any
from unittest.mock import patch

from bot.app.web.webapp.serializers_auto_renew import resolve_auto_renew_capabilities


def _fields(provider: str, *, enabled: bool, chargeable: bool) -> dict[str, Any]:
    with patch("bot.payment_providers.provider_label_map", return_value={}):
        capabilities = resolve_auto_renew_capabilities(
            provider, settings=None, language="ru", chargeable=chargeable
        )
    fields: dict[str, Any] = capabilities.payload_fields(enabled=enabled)
    return fields


class AutoRenewCapabilityTests(unittest.TestCase):
    def test_card_provider_without_a_chargeable_method_hides_the_switch(self):
        fields = _fields("yookassa", enabled=False, chargeable=False)

        self.assertFalse(fields["auto_renew_available"])
        self.assertFalse(fields["auto_renew_can_enable"])

    def test_card_provider_with_a_saved_card_offers_the_switch(self):
        fields = _fields("yookassa", enabled=False, chargeable=True)

        self.assertTrue(fields["auto_renew_available"])
        self.assertTrue(fields["auto_renew_can_enable"])

    def test_enabled_renewal_stays_visible_so_it_can_be_turned_off(self):
        fields = _fields("yookassa", enabled=True, chargeable=False)

        self.assertTrue(fields["auto_renew_available"])
        self.assertFalse(fields["auto_renew_can_enable"])

    def test_provider_managed_mandate_is_only_ever_turned_off(self):
        stopped = _fields("platega", enabled=False, chargeable=True)
        running = _fields("platega", enabled=True, chargeable=True)

        self.assertFalse(stopped["auto_renew_available"])
        self.assertTrue(running["auto_renew_available"])
        self.assertFalse(running["auto_renew_can_enable"])

    def test_one_off_provider_never_shows_the_switch(self):
        fields = _fields("freekassa", enabled=False, chargeable=True)

        self.assertFalse(fields["auto_renew_available"])
        self.assertFalse(fields["auto_renew_can_enable"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
