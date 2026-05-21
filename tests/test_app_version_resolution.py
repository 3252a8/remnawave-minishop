"""Tests for ``_resolve_app_version`` — the source of the admin sidebar footer.

The admin sidebar shows ``{appVersion}`` next to a "remnawave-minishop" GitHub
link. That string is rendered by
``backend/bot/app/web/webapp/assets.py::_resolve_app_version`` through the
following precedence chain:

  1. ``REMNAWAVE_MINISHOP_VERSION`` env var — manual override;
  2. ``$APP_ROOT/.build-version`` file — baked at Docker build time by the
     ``version-builder`` stage in ``deploy/docker/Dockerfile`` (consumes .git
     in a throwaway stage and ships only this one tiny file);
  3. live ``git describe`` / ``rev-parse`` — works in local dev where .git
     is present;
  4. ``"dev+unknown"`` as the ultimate fallback.

Before the build-time bake, the admin footer in production silently fell back
to step 4 because the Docker image carries no .git tree and no git binary.
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


def _reset_cache() -> None:
    # The resolver memoizes the first result in a module-level global.
    assets_module._APP_VERSION_CACHE = None  # type: ignore[attr-defined]
    # Some callers reach through the facade re-export — clear that too.
    runtime = importlib.import_module("bot.app.web.webapp._runtime")
    runtime._APP_VERSION_CACHE = None  # type: ignore[attr-defined]


def _resolve():
    return assets_module._resolve_app_version()


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
        env = {"REMNAWAVE_MINISHOP_VERSION": "   "}
        with (
            patch.dict(os.environ, env),
            patch.object(assets_module, "_run_git_command", lambda *a: ""),
        ):
            # No env, no file, no git → fallback string.
            self.assertEqual(_resolve(), "dev+unknown")


class BuildVersionFileTests(unittest.TestCase):
    """``$APP_ROOT/.build-version`` is what the Docker image ships."""

    def setUp(self) -> None:
        _reset_cache()
        self.addCleanup(_reset_cache)

    def test_reads_baked_version_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".build-version").write_text("v3.4.5+12.gabcdef1", encoding="utf-8")
            env = dict(os.environ)
            env.pop("REMNAWAVE_MINISHOP_VERSION", None)
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                # ensure live git doesn't accidentally win if file read fails:
                patch.object(assets_module, "_run_git_command", lambda *a: ""),
            ):
                self.assertEqual(_resolve(), "v3.4.5+12.gabcdef1")

    def test_strips_trailing_whitespace_and_newlines_in_file(self):
        # Shell ``printf '%s'`` writes no newline, but earlier helpers used
        # ``echo`` which appends one. Both must produce the same result.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".build-version").write_text("v1.2.3\n\n", encoding="utf-8")
            env = dict(os.environ)
            env.pop("REMNAWAVE_MINISHOP_VERSION", None)
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                patch.object(assets_module, "_run_git_command", lambda *a: ""),
            ):
                self.assertEqual(_resolve(), "v1.2.3")

    def test_empty_file_falls_through_to_git_then_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".build-version").write_text("", encoding="utf-8")
            env = dict(os.environ)
            env.pop("REMNAWAVE_MINISHOP_VERSION", None)
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                patch.object(assets_module, "_run_git_command", lambda *a: ""),
            ):
                # No env, empty file, no live git → ultimate fallback.
                self.assertEqual(_resolve(), "dev+unknown")


class LiveGitFallbackTests(unittest.TestCase):
    """Local dev path: no env, no baked file, but ``git`` works."""

    def setUp(self) -> None:
        _reset_cache()
        self.addCleanup(_reset_cache)

    def _run_with_git(self, replies: dict, *, dirty: bool = False) -> str:
        # Map (subcommand, *args) tuples to canned stdout values.
        def fake_git(*args):
            return replies.get(args, "")

        with tempfile.TemporaryDirectory() as tmp:
            # ``.build-version`` deliberately absent so we fall through.
            env = dict(os.environ)
            env.pop("REMNAWAVE_MINISHOP_VERSION", None)
            base = {
                ("describe", "--tags", "--abbrev=0"): replies.get("tag", ""),
                ("rev-parse", "--short", "HEAD"): replies.get("sha", ""),
                ("status", "--porcelain"): "M file\n" if dirty else "",
                ("rev-list", f"{replies.get('tag', '')}..HEAD", "--count"): replies.get(
                    "commits_since_tag", "0"
                ),
            }

            def real_fake_git(*args):
                return base.get(args, "")

            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(assets_module, "APP_ROOT", Path(tmp)),
                patch.object(assets_module, "_run_git_command", real_fake_git),
            ):
                return _resolve()

    def test_tag_with_zero_commits_since_returns_bare_tag(self):
        result = self._run_with_git({"tag": "v2.0.0", "sha": "abcdef1", "commits_since_tag": "0"})
        self.assertEqual(result, "v2.0.0")

    def test_tag_plus_distance_plus_sha_format(self):
        result = self._run_with_git({"tag": "v2.0.0", "sha": "abcdef1", "commits_since_tag": "7"})
        self.assertEqual(result, "v2.0.0+7.gabcdef1")

    def test_sha_only_when_no_tag(self):
        result = self._run_with_git({"sha": "abcdef1"})
        self.assertEqual(result, "dev+gabcdef1")

    def test_neither_tag_nor_sha_is_unknown(self):
        result = self._run_with_git({})
        self.assertEqual(result, "dev+unknown")

    def test_dirty_suffix_is_appended(self):
        result = self._run_with_git(
            {"tag": "v2.0.0", "sha": "abcdef1", "commits_since_tag": "0"},
            dirty=True,
        )
        self.assertEqual(result, "v2.0.0-dirty")


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
            env = dict(os.environ)
            env.pop("REMNAWAVE_MINISHOP_VERSION", None)
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
