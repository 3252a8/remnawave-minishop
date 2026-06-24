import unittest

from bot.services.subscription_service_impl.sale_mode import (
    SaleModeContext,
    parse_sale_mode_context,
)


class ParseSaleModeContextTests(unittest.TestCase):
    def test_empty_token_defaults_to_subscription(self):
        self.assertEqual(
            parse_sale_mode_context(""),
            SaleModeContext(base="subscription", tariff_key=None),
        )

    def test_plain_mode_without_separator(self):
        self.assertEqual(
            parse_sale_mode_context("topup"),
            SaleModeContext(base="topup", tariff_key=None),
        )

    def test_whitespace_is_stripped(self):
        self.assertEqual(
            parse_sale_mode_context("  topup  "),
            SaleModeContext(base="topup", tariff_key=None),
        )

    def test_at_separator_splits_base_and_tariff_key(self):
        self.assertEqual(
            parse_sale_mode_context("subscription@premium"),
            SaleModeContext(base="subscription", tariff_key="premium"),
        )

    def test_pipe_separator_splits_base_and_tariff_key(self):
        self.assertEqual(
            parse_sale_mode_context("subscription|premium"),
            SaleModeContext(base="subscription", tariff_key="premium"),
        )

    def test_legacy_pipe_bot_suffix_yields_no_tariff_key(self):
        self.assertEqual(
            parse_sale_mode_context("subscription|bot"),
            SaleModeContext(base="subscription", tariff_key=None),
        )

    def test_explicit_tariff_key_wins_over_suffix(self):
        self.assertEqual(
            parse_sale_mode_context("subscription@premium", explicit_tariff_key="basic"),
            SaleModeContext(base="subscription", tariff_key="basic"),
        )

    def test_explicit_tariff_key_without_separator(self):
        self.assertEqual(
            parse_sale_mode_context("subscription", explicit_tariff_key="basic"),
            SaleModeContext(base="subscription", tariff_key="basic"),
        )

    def test_only_first_separator_is_used(self):
        # The "@" branch wins (checked first) and the suffix is taken up to the next "|".
        self.assertEqual(
            parse_sale_mode_context("subscription@premium|bot"),
            SaleModeContext(base="subscription", tariff_key="premium"),
        )

    def test_empty_base_falls_back_to_original_mode(self):
        self.assertEqual(
            parse_sale_mode_context("@premium"),
            SaleModeContext(base="@premium", tariff_key="premium"),
        )


if __name__ == "__main__":
    unittest.main()
