"""Guards the Docker packaging of the Mini App's hashed web assets.

The backend renders the Mini App shell and rewrites the stylesheet/script tags
to content-hashed asset names (``subscription_webapp.<hash>.css``). Those hashed
files are gitignored build artifacts, so the backend image only sees them if the
Dockerfile copies them in from the ``frontend-builder`` stage. Without that copy
the asset resolver falls back to the bare ``/subscription_webapp.css`` URL, which
never changes between deploys and is served ``no-store`` -- iOS WebViews cache it
aggressively and render a stale, broken-looking Mini App.

These checks fail loudly if a future Dockerfile refactor drops the copy or moves
the stages so the copy can no longer resolve.
"""

import re
import unittest
from pathlib import Path

DOCKERFILE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "docker" / "Dockerfile"


class DockerWebappAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

    def test_backend_stage_copies_built_webapp_assets(self) -> None:
        self.assertRegex(
            self.dockerfile,
            r"COPY\s+--from=frontend-builder\s+\S*backend/bot/app/web/templates/"
            r"\s+\S*backend/bot/app/web/templates/",
            "backend image must copy the freshly built (hashed) webapp assets so the "
            "shell emits immutable, cache-busting asset URLs",
        )

    def test_frontend_builder_is_defined_before_backend_stage(self) -> None:
        builder_idx = self.dockerfile.find("AS frontend-builder")
        backend_idx = self.dockerfile.find("AS backend")
        self.assertNotEqual(builder_idx, -1, "frontend-builder stage is missing")
        self.assertNotEqual(backend_idx, -1, "backend stage is missing")
        self.assertLess(
            builder_idx,
            backend_idx,
            "frontend-builder must be defined before the backend stage that copies from it",
        )

    def test_frontend_builder_builds_the_webapp_assets(self) -> None:
        self.assertIn("npm run build:webapp", self.dockerfile)

    def test_worker_stage_does_not_copy_webapp_assets(self) -> None:
        # The worker runs background jobs and never serves the web shell, so it
        # should stay lean and not depend on the frontend build.
        worker_match = re.search(
            r"FROM\s+python-base\s+AS\s+worker(?P<body>.*?)(?:\nFROM\s|\Z)",
            self.dockerfile,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(worker_match, "worker stage is missing")
        self.assertNotIn("frontend-builder", worker_match.group("body"))


if __name__ == "__main__":
    unittest.main()
