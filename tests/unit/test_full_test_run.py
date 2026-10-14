"""Composition preserves required edges while removing inactive profiles."""

import unittest
from typing import Any

from qa_tools.compose import prune_optional_dependencies


class FullTestDependenciesTests(unittest.TestCase):
    def test_optional_profile_removed_and_live_dependency_retained(self) -> None:
        services: dict[str, Any] = {
            "frontend": {
                "depends_on": {
                    "backend": {"condition": "service_healthy", "required": True},
                    "advertising-mock-data": {
                        "condition": "service_completed_successfully",
                        "required": False,
                    },
                }
            },
            "backend": {},
        }
        prune_optional_dependencies(services)
        self.assertEqual(
            services["frontend"]["depends_on"],
            {"backend": {"condition": "service_healthy", "required": True}},
        )

    def test_missing_required_dependency_fails_before_starting(self) -> None:
        for options in ({"required": True}, {}):
            with (
                self.subTest(options=options),
                self.assertRaisesRegex(RuntimeError, "frontend requires missing service backend"),
            ):
                prune_optional_dependencies({"frontend": {"depends_on": {"backend": options}}})
