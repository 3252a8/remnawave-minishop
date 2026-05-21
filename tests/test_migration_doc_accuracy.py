"""Pin facts that ``docs/migration-to-minishop.md`` and
``scripts/migrate_to_minishop.sh`` rely on.

Both documents are written for a user upgrading from ``remnawave-tg-shop``
(v2.7.0 era) to the current split-arch ``remnawave-minishop`` (v3.4+). They
make concrete claims about:

* the set of container names produced by today's compose files;
* the set of volume names produced by today's compose files;
* the eras the migration script is allowed to stop containers from.

If any of these drift apart from reality, the migration document silently
goes stale. These tests fail loudly instead.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "migration-to-minishop.md"
SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate_to_minishop.sh"
COMPOSE_FILES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "deploy" / "compose" / "docker-compose-caddy.yml",
    REPO_ROOT / "deploy" / "compose" / "docker-compose-remote-server.yml",
)

# Names that the current architecture must produce in at least one compose file.
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


class MigrationDocumentationFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = _read(DOC_PATH)
        self.script = _read(SCRIPT_PATH)
        self.compose = _all_compose_text()

    def test_doc_lists_every_running_container_in_current_compose(self):
        """The architecture table must reflect what ``docker compose up``
        actually produces today."""
        missing = sorted(name for name in EXPECTED_CONTAINER_NAMES if name not in self.doc)
        self.assertFalse(
            missing,
            f"migration-to-minishop.md is missing container names from current compose: {missing}",
        )

    def test_doc_lists_every_volume_in_current_compose(self):
        missing = sorted(name for name in EXPECTED_VOLUME_NAMES if name not in self.doc)
        self.assertFalse(
            missing,
            f"migration-to-minishop.md is missing volume names from current compose: {missing}",
        )

    def test_doc_warns_about_renamed_telegram_webhook_secret(self):
        # This is the single rename most likely to bite a v2.7.0 → HEAD user.
        self.assertIn("TELEGRAM_WEBHOOK_SECRET", self.doc)
        self.assertIn("WEBHOOK_SECRET_TOKEN", self.doc)

    def test_doc_says_webhook_base_url_is_required(self):
        # Polling mode was dropped — without WEBHOOK_BASE_URL the bot refuses
        # to start. A user migrating from v2.7.0 (where it was optional) must
        # be told this explicitly.
        block = self.doc.lower()
        self.assertIn("webhook_base_url", block)
        # "обязательна" is the marker text in the env-vars table.
        self.assertIn("обязательн", block)

    def test_doc_mentions_migrate_one_shot_service(self):
        # The migrate sidecar is what makes schema migrations transparent on
        # the second-stage upgrade. Don't bury it.
        self.assertIn("migrate", self.doc)
        # "one-shot" or "разовый" / "однораз" text variants accepted.
        normalized = self.doc.lower()
        self.assertTrue(
            "one-shot" in normalized or "однораз" in normalized,
            "migration doc must describe `migrate` as a one-shot service",
        )

    def test_doc_mentions_postgres_host_compose_override_caveat(self):
        # Otherwise users follow the sed-fix step blindly and then panic
        # because their .env still has the "wrong" hostname under compose.
        self.assertIn("POSTGRES_HOST", self.doc)
        # Russian: "переопределя…" / "перебивает" indicate the override is documented.
        text = self.doc.lower()
        self.assertTrue(
            "переопредел" in text or "перебивает" in text,
            "migration doc must explain that compose overrides POSTGRES_HOST",
        )

    def test_doc_describes_redis_data_and_shop_data_as_fresh(self):
        # We do not migrate redis-data or shop-data — make sure that's said
        # so users don't try to copy them from the old stack.
        text = self.doc.lower()
        self.assertIn("redis-data", text)
        self.assertIn("shop-data", text)
        # Some phrasing variant must say it's empty / fresh / new on purpose.
        self.assertTrue(
            any(marker in text for marker in ("пустым", "создаётся пуст", "новые,", "пуст —"))
        )

    def test_doc_explains_reverse_proxy_no_longer_single_upstream(self):
        # The note "rename remnawave-tg-shop → remnawave-minishop in your
        # proxy config" used to be enough; after the split it's wrong.
        # Make sure both backend:8080 and frontend:80 are documented.
        self.assertIn("backend:8080", self.doc)
        self.assertIn("frontend:80", self.doc)


def _known_containers_from_script() -> set[str]:
    """Parse the literal ``KNOWN_CONTAINERS`` array from the script source.

    The array is defined with ``${OLD_PREFIX}`` / ``${NEW_PREFIX}`` placeholders
    that we substitute here. Doing this statically (rather than sourcing the
    script in bash) avoids running ``main`` and keeps the test independent of
    a bash interpreter being available at runtime.
    """
    text = _read(SCRIPT_PATH)

    prefix_match = re.search(r'^OLD_PREFIX="([^"]+)"', text, flags=re.MULTILINE)
    new_match = re.search(r'^NEW_PREFIX="([^"]+)"', text, flags=re.MULTILINE)
    if not prefix_match or not new_match:
        return set()
    old_prefix = prefix_match.group(1)
    new_prefix = new_match.group(1)

    # ``\n)`` as a boundary: a non-greedy ``.*?\)`` would stop at the first
    # close-paren in a comment like ``# (v2.7.0 upstream remnawave-tg-shop)``.
    array_match = re.search(
        r"KNOWN_CONTAINERS=\((.*?)\n\)",
        text,
        flags=re.DOTALL,
    )
    if not array_match:
        return set()

    body = array_match.group(1)
    # Strip line comments and quotes, then expand the two placeholders.
    names: set[str] = set()
    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        for token in re.findall(r'"([^"]+)"', line):
            expanded = token.replace("${OLD_PREFIX}", old_prefix).replace(
                "${NEW_PREFIX}", new_prefix
            )
            names.add(expanded)
    return names


class MigrationScriptCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = _read(SCRIPT_PATH)
        self.known = _known_containers_from_script()

    def test_known_containers_covers_split_arch(self):
        """A re-run on a partially migrated stack must be able to stop the new
        containers, otherwise ``docker compose up`` later fails with name
        conflicts."""
        missing = sorted(EXPECTED_CONTAINER_NAMES - self.known)
        self.assertFalse(
            missing,
            f"KNOWN_CONTAINERS missing split-arch entries: {missing}\nactual: {sorted(self.known)}",
        )

    def test_known_containers_still_covers_legacy_eras(self):
        # We must also keep stopping the original (v2.7.0) and intermediate
        # (v3.1.x – v3.2.x) container names.
        for legacy in ("remnawave-tg-shop", "remnawave-tg-shop-db", "remnawave-minishop-db"):
            with self.subTest(container=legacy):
                self.assertIn(legacy, self.known)

    def test_script_is_syntactically_valid_bash(self):
        # The script is curl|bash'ed from raw.githubusercontent in the docs,
        # so a syntax break is a hard regression.
        import shutil
        import subprocess

        bash = shutil.which("bash")
        if not bash:  # pragma: no cover
            self.skipTest("bash not available in PATH")
        result = subprocess.run(
            [bash, "-n", str(SCRIPT_PATH)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            (
                "bash -n flagged migrate_to_minishop.sh:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            ),
        )


class DocComposeFileReferencesTests(unittest.TestCase):
    """The doc links the user to specific compose files — they must exist."""

    def test_referenced_compose_files_exist(self):
        doc = _read(DOC_PATH)
        for relpath in (
            "docker-compose.yml",
            "deploy/compose/docker-compose-caddy.yml",
            "deploy/compose/docker-compose-remote-server.yml",
        ):
            with self.subTest(path=relpath):
                self.assertIn(relpath, doc)
                self.assertTrue(
                    (REPO_ROOT / relpath).is_file(),
                    f"{relpath} is referenced in migration-to-minishop.md but missing on disk",
                )

    def test_doc_references_migrator_module_path(self):
        # The doc tells users to expect ``backend/db/migrator.py`` migrations
        # to apply via the migrate service. If the file moves, the doc lies.
        doc = _read(DOC_PATH)
        self.assertIn("backend/db/migrator.py", doc)
        self.assertTrue((REPO_ROOT / "backend" / "db" / "migrator.py").is_file())


class MigrationFootprintRegexTests(unittest.TestCase):
    """Spot-check that what compose actually defines matches what we documented."""

    def test_every_compose_volume_documented(self):
        """If a future compose file introduces a new ``remnawave-minishop-*``
        named volume, the migration doc must call out whether it carries data
        from the old stack or starts fresh."""
        doc = _read(DOC_PATH)
        compose_text = _all_compose_text()
        # Find every named volume of the form ``remnawave-minishop-<key>-data``.
        defined = set(re.findall(r"remnawave-minishop-[\w-]+-data", compose_text))
        # Caddy-only volumes only ship in the caddy compose file but are still
        # documented; allow them either way.
        for volume in defined:
            with self.subTest(volume=volume):
                self.assertIn(
                    volume,
                    doc,
                    f"new volume {volume} is defined in compose but missing from migration doc",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
