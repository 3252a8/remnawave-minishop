"""Tests for ``_resolve_app_version``: the admin sidebar footer source.

The admin sidebar shows ``{appVersion}`` next to a "remnawave-minishop" GitHub
link. Release builds from ``main`` should render the latest reachable tag and
commit sha, without a dirty suffix. Builds from other branches include the
branch name. That string is rendered by
``backend/bot/app/web/webapp/assets.py::_resolve_app_version`` through this
precedence chain:

  1. ``REMNAWAVE_MINISHOP_VERSION`` env var: manual override;
  2. ``$APP_ROOT/.build-version`` file: baked at Docker build time by the
     ``version-builder`` stage in ``deploy/docker/Dockerfile``;
  3. live ``git describe`` / ``rev-parse``: local dev fallback where .git is
     present;
  4. ``"dev+unknown"`` as the ultimate fallback.

The Docker image carries no git binary and no .git tree at runtime, so the
baked ``.build-version`` file is the production source for the sidebar.
"""

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Importing the webapp facade populates the runtime helpers we need.
import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import assets as assets_module
from bot.utils import app_version as app_version_module

_VERSION_ENV_NAMES = (
    "REMNAWAVE_MINISHOP_VERSION",
    "REMNAWAVE_MINISHOP_BUILD_PROVENANCE",
    "REMNAWAVE_MINISHOP_BRANCH",
    "GIT_BRANCH",
    "BRANCH_NAME",
    "GITHUB_REF_NAME",
    "CI_COMMIT_REF_NAME",
)


def _reset_cache() -> None:
    # The resolver memoizes the first result in a module-level global.
    assets_module._APP_VERSION_CACHE = None  # type: ignore[attr-defined]
    app_version_module._APP_VERSION_CACHE = None  # type: ignore[attr-defined]
    app_version_module._APP_BUILD_PROVENANCE_CACHE = None  # type: ignore[attr-defined]
    # Some callers reach through the facade re-export; clear that too.
    runtime = importlib.import_module("bot.app.web.webapp._runtime")
    runtime._APP_VERSION_CACHE = None  # type: ignore[attr-defined]


def _resolve() -> str:
    version: str = assets_module._resolve_app_version()
    return version


def _clean_version_env() -> dict:
    env = dict(os.environ)
    for name in _VERSION_ENV_NAMES:
        env.pop(name, None)
    return env


class EnvOverrideTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()
        self.addCleanup(_reset_cache)

    def test_env_var_short_circuits_everything(self):
        # No git lookups, no file IO when the operator provided a value.
        called = {"git": 0}

        def fake_git(*args):
            called["git"] += 1
            return "should-not-be-used"

        with (
            patch.dict(os.environ, {"REMNAWAVE_MINISHOP_VERSION": "v9.9.9-rc1"}),
            patch.object(assets_module, "_run_git_command", fake_git),
        ):
            self.assertEqual(_resolve(), "v9.9.9-rc1")
        self.assertEqual(called["git"], 0)

    def test_blank_env_var_falls_through(self):
        env = _clean_version_env()
        env["REMNAWAVE_MINISHOP_VERSION"] = "   "
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(assets_module, "_run_git_command", lambda *a: ""),
        ):
            # No env, no file, no git: fallback string.
            self.assertEqual(_resolve(), "dev+unknown")


class BuildVersionFileTests(unittest.TestCase):
    """``$APP_ROOT/.build-version`` is what the Docker image ships."""

    def setUp(self) -> None:
        _reset_cache()
        self.addCleanup(_reset_cache)

    def test_reads_baked_version_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".build-version").write_text("v3.4.5+gabcdef1", encoding="utf-8")
            env = _clean_version_env()
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                # Ensure live git does not accidentally win if file read fails.
                patch.object(assets_module, "_run_git_command", lambda *a: ""),
            ):
                self.assertEqual(_resolve(), "v3.4.5+gabcdef1")

    def test_strips_trailing_whitespace_and_newlines_in_file(self):
        # Shell ``printf '%s'`` writes no newline, but older helpers may have
        # used ``echo``. Both must produce the same result.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".build-version").write_text("v1.2.3\n\n", encoding="utf-8")
            env = _clean_version_env()
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                patch.object(assets_module, "_run_git_command", lambda *a: ""),
            ):
                self.assertEqual(_resolve(), "v1.2.3")

    def test_empty_file_falls_through_to_git_then_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".build-version").write_text("", encoding="utf-8")
            env = _clean_version_env()
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                patch.object(assets_module, "_run_git_command", lambda *a: ""),
            ):
                # No env, empty file, no live git: ultimate fallback.
                self.assertEqual(_resolve(), "dev+unknown")


class LiveGitFallbackTests(unittest.TestCase):
    """Local dev path: no env, no baked file, but ``git`` works."""

    def setUp(self) -> None:
        _reset_cache()
        self.addCleanup(_reset_cache)

    def _run_with_git(self, replies: dict) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            # ``.build-version`` deliberately absent so we fall through.
            env = _clean_version_env()
            base = {
                ("describe", "--tags", "--abbrev=0"): replies.get("tag", ""),
                ("rev-parse", "--short", "HEAD"): replies.get("sha", ""),
                ("branch", "--show-current"): replies.get("branch", ""),
            }

            def fake_git(*args):
                return base.get(args, "")

            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                patch.object(assets_module, "_run_git_command", fake_git),
            ):
                return _resolve()

    def test_tag_with_sha_returns_tag_plus_sha(self):
        result = self._run_with_git({"tag": "v2.0.0", "sha": "abcdef1"})
        self.assertEqual(result, "v2.0.0+gabcdef1")

    def test_main_branch_does_not_add_branch_suffix(self):
        result = self._run_with_git({"tag": "v2.0.0", "sha": "abcdef1", "branch": "main"})
        self.assertEqual(result, "v2.0.0+gabcdef1")

    def test_non_main_branch_adds_branch_suffix(self):
        result = self._run_with_git({"tag": "v2.0.0", "sha": "abcdef1", "branch": "dev"})
        self.assertEqual(result, "v2.0.0-dev+gabcdef1")

    def test_branch_name_is_sanitized_for_version(self):
        result = self._run_with_git(
            {"tag": "v2.0.0", "sha": "abcdef1", "branch": "feature/cool build"}
        )
        self.assertEqual(result, "v2.0.0-feature-cool-build+gabcdef1")

    def test_commit_distance_is_not_included(self):
        result = self._run_with_git({"tag": "v2.0.0", "sha": "abcdef1", "commits_since_tag": "7"})
        self.assertEqual(result, "v2.0.0+gabcdef1")

    def test_sha_only_when_no_tag(self):
        result = self._run_with_git({"sha": "abcdef1"})
        self.assertEqual(result, "dev+gabcdef1")

    def test_tag_only_when_no_sha(self):
        result = self._run_with_git({"tag": "v2.0.0"})
        self.assertEqual(result, "v2.0.0")

    def test_neither_tag_nor_sha_is_unknown(self):
        result = self._run_with_git({})
        self.assertEqual(result, "dev+unknown")

    def test_dirty_suffix_is_not_appended_or_queried(self):
        calls = []

        def fake_git(*args):
            calls.append(args)
            replies = {
                ("describe", "--tags", "--abbrev=0"): "v2.0.0",
                ("rev-parse", "--short", "HEAD"): "abcdef1",
                ("status", "--porcelain"): "M file\n",
            }
            return replies.get(args, "")

        with tempfile.TemporaryDirectory() as tmp:
            env = _clean_version_env()
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                patch.object(assets_module, "_run_git_command", fake_git),
            ):
                result = _resolve()

        self.assertEqual(result, "v2.0.0+gabcdef1")
        self.assertNotIn(("status", "--porcelain"), calls)


class CacheBehaviourTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()
        self.addCleanup(_reset_cache)

    def test_second_call_is_cached_and_does_not_reread(self):
        calls = {"git": 0}

        def fake_git(*args):
            calls["git"] += 1
            return "abcdef1" if args == ("rev-parse", "--short", "HEAD") else ""

        with tempfile.TemporaryDirectory() as tmp:
            env = _clean_version_env()
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                patch.object(assets_module, "_run_git_command", fake_git),
            ):
                first = _resolve()
                first_calls = calls["git"]
                second = _resolve()
                second_calls = calls["git"]

        self.assertEqual(first, "dev+gabcdef1")
        self.assertEqual(second, first)
        # No additional git invocations after the cache was populated.
        self.assertGreater(first_calls, 0)
        self.assertEqual(first_calls, second_calls)


class BuildProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()
        self.addCleanup(_reset_cache)

    def test_env_var_short_circuits_build_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".build-provenance").write_text("custom", encoding="utf-8")
            env = _clean_version_env()
            env["REMNAWAVE_MINISHOP_BUILD_PROVENANCE"] = "official"
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(app_version_module, "APP_ROOT", Path(tmp)),
            ):
                self.assertEqual(app_version_module.resolve_build_provenance(), "official")
                self.assertFalse(app_version_module.resolve_image_modified())

    def test_reads_baked_build_provenance_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".build-provenance").write_text("custom\n", encoding="utf-8")
            env = _clean_version_env()
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(app_version_module, "APP_ROOT", Path(tmp)),
            ):
                self.assertEqual(app_version_module.resolve_build_provenance(), "custom")
                self.assertTrue(app_version_module.resolve_image_modified())

    def test_missing_marker_defaults_to_custom(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _clean_version_env()
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(app_version_module, "APP_ROOT", Path(tmp)),
            ):
                self.assertEqual(app_version_module.resolve_build_provenance(), "custom")
                self.assertTrue(app_version_module.resolve_image_modified())

    def test_legacy_boolean_aliases_are_normalized(self):
        env = _clean_version_env()
        env["REMNAWAVE_MINISHOP_BUILD_PROVENANCE"] = "true"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(app_version_module.resolve_build_provenance(), "official")

        _reset_cache()
        env["REMNAWAVE_MINISHOP_BUILD_PROVENANCE"] = "fork"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(app_version_module.resolve_build_provenance(), "custom")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
