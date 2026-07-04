import unittest

from bot.app.web.webapp.common import (
    _format_months_title,
    _hwid_devices_payment_description,
    _payment_description,
    _traffic_payment_description,
)


class WebappCommonLocalizationTests(unittest.TestCase):
    def test_format_months_title_uses_requested_language(self):
        self.assertEqual(_format_months_title(1, "zh-cn"), "1 个月")
        self.assertEqual(_format_months_title(3, "zh-cn"), "3 个月")
        self.assertEqual(_format_months_title(12, "zh"), "12 个月")

        self.assertEqual(_format_months_title(1, "en"), "1 month")
        self.assertEqual(_format_months_title(3, "en"), "3 months")

        self.assertEqual(_format_months_title(1, "ru"), "1 месяц")
        self.assertEqual(_format_months_title(3, "ru"), "3 месяца")
        self.assertEqual(_format_months_title(6, "ru"), "6 месяцев")

    def test_payment_descriptions_use_requested_language(self):
        self.assertEqual(_payment_description(3, "zh-cn"), "订阅 3 个月")
        self.assertEqual(_traffic_payment_description(60, "zh-cn"), "流量包 60 GB")
        self.assertEqual(_hwid_devices_payment_description(2, "zh-cn"), "加购 HWID 设备 +2")

        self.assertEqual(_payment_description(3, "en"), "Subscription for 3 months")
        self.assertEqual(_payment_description(3, "ru"), "Подписка на 3 месяца")


if __name__ == "__main__":
    unittest.main()
