"""Pin facts shared by the migration docs and the unified install wizard."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "migrations" / "remnawave-tg-shop.md"
REMNASHOP_DOC_PATH = REPO_ROOT / "docs" / "migrations" / "remnashop.md"
DEPLOYMENT_DOC_PATH = REPO_ROOT / "docs" / "getting-started" / "deployment.md"
INSTALL_SCRIPT_PATH = REPO_ROOT / "scripts" / "install.sh"
REMOVED_SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate_to_minishop.sh"
COMPOSE_FILES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "deploy" / "examples" / "caddy" / "docker-compose.yml",
    REPO_ROOT / "deploy" / "examples" / "nginx" / "docker-compose.yml",
    REPO_ROOT / "deploy" / "examples" / "newt" / "docker-compose.yml",
    REPO_ROOT / "deploy" / "examples" / "no-proxy" / "docker-compose.yml",
)

EXPECTED_CONTAINER_NAMES = {
    "remnawave-minishop-backend",
    "remnawave-minishop-worker",
    "remnawave-minishop-frontend",
    "remnawave-minishop-migrate",
    "remnawave-minishop-postgres",
    "remnawave-minishop-redis",
}
EXPECTED_VOLUME_NAMES = {
    "remnawave-minishop-db-data",
    "remnawave-minishop-redis-data",
    "remnawave-minishop-shop-data",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _all_compose_text() -> str:
    return "\n".join(_read(path) for path in COMPOSE_FILES if path.is_file())


def _known_containers_from_install_script() -> set[str]:
    text = _read(INSTALL_SCRIPT_PATH)
    match = re.search(r'^KNOWN_LEGACY_CONTAINERS="([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        return set()
    return set(match.group(1).split())


class MigrationDocumentationFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = _read(DOC_PATH)
        self.script = _read(INSTALL_SCRIPT_PATH)
        self.compose = _all_compose_text()

    def test_unified_install_script_is_the_only_migration_entrypoint(self):
        self.assertTrue(INSTALL_SCRIPT_PATH.is_file())
        self.assertFalse(REMOVED_SCRIPT_PATH.exists())
        self.assertIn("scripts/install.sh", self.doc)
        self.assertNotIn("migrate_to_minishop.sh", self.doc)

    def test_doc_lists_every_running_container_in_current_compose(self):
        missing = sorted(name for name in EXPECTED_CONTAINER_NAMES if name not in self.doc)
        self.assertFalse(
            missing,
            "migrations/remnawave-tg-shop.md is missing container names "
            f"from current compose: {missing}",
        )

    def test_doc_lists_every_volume_in_current_compose(self):
        missing = sorted(name for name in EXPECTED_VOLUME_NAMES if name not in self.doc)
        self.assertFalse(
            missing,
            "migrations/remnawave-tg-shop.md is missing volume names "
            f"from current compose: {missing}",
        )

    def test_doc_warns_about_renamed_telegram_webhook_secret(self):
        self.assertIn("TELEGRAM_WEBHOOK_SECRET", self.doc)
        self.assertIn("WEBHOOK_SECRET_TOKEN", self.doc)

    def test_doc_says_webhook_base_url_is_required(self):
        block = self.doc.lower()
        self.assertIn("webhook_base_url", block)
        self.assertIn("обязательн", block)

    def test_doc_mentions_migrate_one_shot_service(self):
        normalized = self.doc.lower()
        self.assertIn("migrate", normalized)
        self.assertTrue(
            "one-shot" in normalized or "однораз" in normalized,
            "migration doc must describe `migrate` as a one-shot service",
        )

    def test_doc_mentions_postgres_host_compose_override_caveat(self):
        self.assertIn("POSTGRES_HOST", self.doc)
        text = self.doc.lower()
        self.assertTrue(
            "переопредел" in text or "service name" in text,
            "migration doc must explain that compose overrides POSTGRES_HOST",
        )

    def test_doc_describes_redis_data_and_shop_data_as_fresh(self):
        text = self.doc.lower()
        self.assertIn("redis-data", text)
        self.assertIn("shop-data", text)
        self.assertTrue(any(marker in text for marker in ("пустым", "создается пуст")))

    def test_doc_explains_reverse_proxy_no_longer_single_upstream(self):
        self.assertIn("backend:8080", self.doc)
        self.assertIn("frontend:80", self.doc)

    def test_doc_describes_safe_tgshop_dsn_restore(self):
        self.assertIn("не копирует raw PostgreSQL", self.doc)
        self.assertIn("LEGACY_TGSHOP_DB_CONTAINER", self.doc)
        self.assertIn("LEGACY_TGSHOP_SOURCE_DSN", self.doc)
        self.assertIn("удаляет целевой DB volume", self.doc)
        self.assertIn("pre-remnawave-tg-shop-source", self.doc)
        self.assertIn("remnawave-tg-shop-db-data", self.doc)
        self.assertIn("pg_dump", self.doc)

    def test_doc_uses_current_russian_wizard_menu_labels(self):
        self.assertIn("Установить новый remnawave-minishop и мигрировать", self.doc)
        self.assertIn("Мигрировать данные в уже установленный remnawave-minishop", self.doc)
        self.assertIn("Старый remnawave-tg-shop", self.doc)


class InstallWizardCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = _read(INSTALL_SCRIPT_PATH)
        self.known = _known_containers_from_install_script()

    def test_known_containers_covers_split_arch(self):
        missing = sorted(EXPECTED_CONTAINER_NAMES - self.known)
        self.assertFalse(
            missing,
            f"KNOWN_LEGACY_CONTAINERS missing split-arch entries: {missing}",
        )

    def test_known_containers_still_covers_old_eras(self):
        for legacy in ("remnawave-tg-shop", "remnawave-tg-shop-db", "remnawave-minishop-db"):
            with self.subTest(container=legacy):
                self.assertIn(legacy, self.known)

    def test_installer_contains_tgshop_dsn_restore_path(self):
        self.assertNotIn("run_tgshop_volume_migration", self.script)
        self.assertIn("run_tgshop_dsn_migration", self.script)
        self.assertIn("detect_tgshop_source_dsn", self.script)
        self.assertIn("create_tgshop_source_backup", self.script)
        self.assertIn("reset_target_postgres_volume", self.script)
        self.assertIn('docker volume rm "$volume"', self.script)
        self.assertIn("pg_dump --clean --if-exists", self.script)
        self.assertIn('psql "$TARGET_DSN" -v ON_ERROR_STOP=1', self.script)
        self.assertIn("run_compose_checked run --rm migrate", self.script)

    def test_script_is_syntactically_valid_sh_and_bash(self):
        sh = shutil.which("sh")
        if not sh:  # pragma: no cover
            self.skipTest("sh not available in PATH")
        result = subprocess.run(
            [sh, "-n", str(INSTALL_SCRIPT_PATH)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        bash = shutil.which("bash")
        if bash:
            result = subprocess.run(
                [bash, "-n", str(INSTALL_SCRIPT_PATH)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


class DocComposeFileReferencesTests(unittest.TestCase):
    def test_referenced_compose_files_exist(self):
        doc = _read(DOC_PATH)
        for relpath in (
            "docker-compose.yml",
            "deploy/examples/caddy/docker-compose.yml",
            "deploy/examples/nginx/docker-compose.yml",
            "deploy/examples/newt/docker-compose.yml",
            "deploy/examples/no-proxy/docker-compose.yml",
        ):
            with self.subTest(path=relpath):
                self.assertIn(relpath, doc)
                self.assertTrue((REPO_ROOT / relpath).is_file())

    def test_doc_references_migrator_module_path(self):
        doc = _read(DOC_PATH)
        self.assertIn("backend/db/migrator/", doc)
        self.assertTrue((REPO_ROOT / "backend" / "db" / "migrator" / "__init__.py").is_file())


class RemnashopMigrationDocumentationFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = _read(REMNASHOP_DOC_PATH)
        self.deployment_doc = _read(DEPLOYMENT_DOC_PATH)

    def test_doc_mentions_env_payment_gateways_and_encrypted_secrets(self):
        self.assertIn("--source-env-file", self.doc)
        self.assertIn("APP_CRYPT_KEY", self.doc)
        self.assertIn("payment_gateways", self.doc)
        self.assertIn("enc_", self.doc)

    def test_doc_lists_new_webhook_paths_after_migration(self):
        for path in (
            "/webhook/panel",
            "/webhook/yookassa",
            "/webhook/wata",
            "/webhook/cryptopay",
            "/webhook/heleket",
            "/webhook/paykilla",
            "/webhook/freekassa",
            "/webhook/platega",
            "/tg/webhook",
        ):
            with self.subTest(path=path):
                self.assertIn(path, self.doc)

    def test_doc_matches_current_wizard_prompts_and_defaults(self):
        for phrase in (
            "Установить новый remnawave-minishop и мигрировать данные из другого бота",
            "Мигрировать данные в уже установленный remnawave-minishop",
            "Уже установленная Remnawave через eGames",
            "/opt/remnawave-minishop",
            "MINISHOP_INSTALL_REPO",
            "MINISHOP_INSTALL_REF",
            "REMNASHOP_SOURCE_SCHEMA",
            "backups/pre-remnashop-migration",
            "backend`, `worker` и `frontend`",
            "eGames Nginx",
            "Дальнейшие шаги",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.doc)

        self.assertNotIn("Install new stack and run migration", self.doc)
        self.assertNotIn("Run migration only", self.doc)
        self.assertNotIn("source PostgreSQL DSN Remnashop и schema", self.doc)

    def test_deployment_doc_mentions_installer_dns_tls_and_proxy_refresh(self):
        for phrase in (
            "/opt/remnawave-minishop",
            "проверить A-записи",
            "Certbot Cloudflare DNS-01",
            "10001:10001",
            "backend`, `worker` и `frontend`",
            "nginx -t",
            "reload/restart eGames Nginx",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.deployment_doc)


class MigrationFootprintRegexTests(unittest.TestCase):
    def test_every_compose_volume_documented(self):
        doc = _read(DOC_PATH)
        compose_text = _all_compose_text()
        defined = set(re.findall(r"remnawave-minishop-[\w-]+-data", compose_text))
        for volume in defined:
            with self.subTest(volume=volume):
                self.assertIn(volume, doc)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
