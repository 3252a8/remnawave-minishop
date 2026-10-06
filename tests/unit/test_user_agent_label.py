import unittest

from bot.utils.user_agent import describe_user_agent

WEBKIT = "AppleWebKit/537.36 (KHTML, like Gecko)"
CASES = (
    (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {WEBKIT} Chrome/141.0 Safari/537.36",
        "Chrome",
        "Windows",
    ),
    (
        f"Mozilla/5.0 (Windows NT 10.0) {WEBKIT} Chrome/141.0 Safari/537.36 Edg/141.0",
        "Edge",
        "Windows",
    ),
    (
        f"Mozilla/5.0 (Linux; Android 14) {WEBKIT} Chrome/140.0 YaBrowser/25.8 Safari/537.36",
        "Yandex Browser",
        "Android",
    ),
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) Version/18.6 Mobile Safari/604.1",
        "Safari",
        "iOS",
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) Version/18.6 Safari/605.1.15",
        "Safari",
        "macOS",
    ),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0", "Firefox", "Linux"),
)


class DescribeUserAgentTests(unittest.TestCase):
    def test_common_browsers_and_systems(self):
        for user_agent, browser, system in CASES:
            with self.subTest(user_agent=user_agent):
                self.assertEqual(describe_user_agent(user_agent), (browser, system))

    def test_missing_header_names_nothing(self):
        self.assertEqual(describe_user_agent(None), ("", ""))
        self.assertEqual(describe_user_agent("curl/8.5.0"), ("", ""))
