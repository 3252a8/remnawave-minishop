import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from startup_banner import _redis_target, print_startup_banner


def _render(service: str, env: dict) -> str:
    buffer = io.StringIO()
    with patch.dict(os.environ, env, clear=False), redirect_stdout(buffer):
        print_startup_banner(service)
    return buffer.getvalue()


class StartupBannerTests(unittest.TestCase):
    def test_startup_banner_marks_services_without_mojibake(self):
        for service in ("frontend", "backend", "worker", "migrate"):
            with self.subTest(service=service):
                output = _render(
                    service,
                    {
                        "IMAGE_TAG": "test-tag",
                        "REMNAWAVE_MINISHOP_TAG": "v3.4.0",
                        "REMNAWAVE_MINISHOP_COMMIT": "abc1234",
                        "POSTGRES_HOST": "postgres",
                        "POSTGRES_DB": "postgres",
                        "REDIS_URL": "redis://redis:6379/0",
                    },
                )
                self.assertIn(f"container :: {service.upper()}", output)
                self.assertIn("image tag :: test-tag", output)
                self.assertIn("commit :: abc1234", output)
                self.assertIn("remnawave-minishop", output)
                self.assertIn("███", output)
                self.assertNotIn("в", output)

    def test_startup_banner_expands_latest_and_dev_tags(self):
        latest_output = _render(
            "backend",
            {
                "IMAGE_TAG": "latest",
                "REMNAWAVE_MINISHOP_TAG": "v3.4.0",
                "REMNAWAVE_MINISHOP_COMMIT": "abc1234",
            },
        )
        self.assertIn("image tag :: latest-v3.4.0", latest_output)

        dev_output = _render(
            "backend",
            {
                "IMAGE_TAG": "dev",
                "REMNAWAVE_MINISHOP_TAG": "v3.4.0",
                "REMNAWAVE_MINISHOP_COMMIT": "abc1234",
            },
        )
        self.assertIn("image tag :: dev-v3.4.0+abc1234", dev_output)


class StartupBannerServiceDetailsTests(unittest.TestCase):
    def test_backend_lists_ports_postgres_and_redis(self):
        output = _render(
            "backend",
            {
                "IMAGE_TAG": "v1",
                "WEB_SERVER_PORT": "8090",
                "WEBAPP_SERVER_PORT": "8091",
                "WEBAPP_ENABLED": "True",
                "POSTGRES_HOST": "pg",
                "POSTGRES_PORT": "5440",
                "POSTGRES_DB": "shop",
                "REDIS_URL": "redis://r:6380/2",
            },
        )
        self.assertIn("webhooks :: :8090", output)
        self.assertIn("webapp api :: on / :8091", output)
        self.assertIn("postgres :: pg:5440/shop", output)
        self.assertIn("redis :: r:6380/2", output)

    def test_worker_lists_queue_and_panel_sync_interval(self):
        output = _render(
            "worker",
            {
                "IMAGE_TAG": "v1",
                "WEBHOOK_QUEUE_CONCURRENCY": "8",
                "WORKER_PANEL_SYNC_INTERVAL_SECONDS": "600",
                "TARIFFS_CONFIG_PATH": "data/tariffs.json",
                "POSTGRES_HOST": "pg",
                "POSTGRES_DB": "shop",
                "REDIS_URL": "redis://r:6379/0",
            },
        )
        self.assertIn("queue concurrency :: 8", output)
        self.assertIn("panel sync interval :: 600s", output)
        self.assertIn("tariffs config :: data/tariffs.json", output)

    def test_migrate_shows_one_shot_mode_and_data_dir(self):
        output = _render(
            "migrate",
            {
                "IMAGE_TAG": "v1",
                "POSTGRES_HOST": "pg",
                "POSTGRES_DB": "shop",
            },
        )
        self.assertIn("mode :: one-shot migrations", output)
        self.assertIn("data dir :: /app/data", output)


class StartupBannerRedisTargetTests(unittest.TestCase):
    def test_redis_target_renders_host_port_db(self):
        with patch.dict(os.environ, {"REDIS_URL": "redis://r:6379/3"}, clear=False):
            self.assertEqual(_redis_target(), "r:6379/3")

    def test_redis_target_defaults_db_to_zero(self):
        with patch.dict(os.environ, {"REDIS_URL": "redis://r"}, clear=False):
            self.assertEqual(_redis_target(), "r/0")

    def test_redis_target_when_url_missing(self):
        env = dict(os.environ)
        env.pop("REDIS_URL", None)
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(_redis_target(), "-")
