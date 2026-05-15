import json
import tempfile
import unittest
from pathlib import Path

from config.webapp_themes_config import (
    WebappThemesConfig,
    apply_webapp_theme_env_overrides,
    builtin_webapp_themes_config,
    default_webapp_theme_descriptors,
    ensure_webapp_core_themes,
    load_webapp_theme_dir,
    public_themes_catalog_payload,
    resolved_webapp_themes_catalog,
    write_webapp_theme_dir,
)


class WebappThemesConfigTests(unittest.TestCase):
    def test_builtin_has_core_themes(self):
        cfg = builtin_webapp_themes_config("#abcdef")
        self.assertEqual(cfg.default_theme, "dark")
        keys = {theme.key for theme in cfg.themes}
        self.assertEqual(keys, {"dark", "light", "windows95", "ascii"})
        dark = cfg.theme_by_key("dark")
        self.assertIsNotNone(dark)
        self.assertTrue(dark.default)
        self.assertEqual(dark.tokens.accent, "#abcdef")
        win95 = cfg.theme_by_key("windows95")
        self.assertIsNotNone(win95)
        self.assertEqual(cfg.theme_by_key("light").css_file, "style.css")
        self.assertEqual(win95.css_file, "style.css")
        self.assertEqual(win95.tokens.style_preset, "win95")
        self.assertFalse(win95.use_primary_accent)
        self.assertTrue(win95.use_in_admin)
        self.assertEqual(win95.assets_version, 5)
        ascii_theme = cfg.theme_by_key("ascii")
        self.assertIsNotNone(ascii_theme)
        self.assertEqual(ascii_theme.css_file, "style.css")
        self.assertFalse(ascii_theme.use_primary_accent)
        self.assertTrue(ascii_theme.use_in_admin)
        self.assertEqual(ascii_theme.assets_version, 1)

    def test_env_override_default_theme(self):
        cfg = builtin_webapp_themes_config("#00fe7a")
        out = apply_webapp_theme_env_overrides(cfg, "light")
        self.assertEqual(out.default_theme, "light")
        self.assertTrue(out.theme_by_key("light").default)
        self.assertFalse(out.theme_by_key("dark").default)

    def test_core_themes_are_merged_when_missing(self):
        cfg = WebappThemesConfig(
            default_theme="custom",
            themes=[
                {
                    "key": "custom",
                    "enabled": True,
                    "default": True,
                    "use_primary_accent": False,
                    "tokens": {"color_scheme": "dark"},
                }
            ],
        )

        merged, changed = ensure_webapp_core_themes(cfg, "#00fe7a")

        self.assertTrue(changed)
        self.assertEqual(
            {theme.key for theme in merged.themes},
            {"custom", "dark", "light", "windows95", "ascii"},
        )
        self.assertEqual(merged.default_theme, "custom")
        self.assertTrue(merged.theme_by_key("custom").default)
        self.assertEqual(merged.theme_by_key("light").css_file, "style.css")
        self.assertTrue(merged.theme_by_key("custom").use_in_admin)
        self.assertFalse(merged.theme_by_key("custom").use_primary_accent)

    def test_default_theme_descriptors_are_read_from_source_files(self):
        descriptors = default_webapp_theme_descriptors()

        self.assertEqual(set(descriptors), {"dark", "light", "windows95", "ascii"})
        self.assertTrue(descriptors["dark"]["default"])
        self.assertEqual(descriptors["windows95"]["css_file"], "style.css")
        self.assertEqual(descriptors["ascii"]["css_file"], "style.css")

    def test_resolved_creates_default_files_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_dir = Path(tmp) / "themes"
            cfg = resolved_webapp_themes_catalog(
                theme_dir=themes_dir,
                primary_accent="#abc123",
                env_default_theme=None,
            )

            self.assertTrue((themes_dir / "dark" / "theme.json").exists())
            self.assertTrue((themes_dir / "light" / "theme.json").exists())
            self.assertTrue((themes_dir / "light" / "style.css").exists())
            self.assertTrue((themes_dir / "windows95" / "theme.json").exists())
            self.assertTrue((themes_dir / "windows95" / "style.css").exists())
            self.assertTrue((themes_dir / "windows95" / "icons" / "save.png").exists())
            self.assertTrue((themes_dir / "ascii" / "theme.json").exists())
            self.assertTrue((themes_dir / "ascii" / "style.css").exists())
            self.assertEqual(cfg.default_theme, "dark")
            self.assertIsNone(cfg.theme_by_key("dark").tokens.accent)

    def test_load_theme_dir_uses_filename_as_key_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_dir = Path(tmp) / "themes"
            themes_dir.mkdir()
            (themes_dir / "custom").mkdir()
            (themes_dir / "custom" / "theme.json").write_text(
                json.dumps(
                    {
                        "names": {"en": "Custom"},
                        "enabled": True,
                        "css_file": "style.css",
                        "tokens": {"color_scheme": "light"},
                    }
                ),
                encoding="utf-8",
            )

            themes = load_webapp_theme_dir(themes_dir)

            self.assertEqual(len(themes), 1)
            self.assertEqual(themes[0].key, "custom")
            self.assertEqual(themes[0].names["en"], "Custom")

    def test_resolved_catalog_includes_custom_mounted_theme_descriptor(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_dir = Path(tmp) / "themes"
            themes_dir.mkdir()
            (themes_dir / "neon").mkdir()
            (themes_dir / "neon" / "theme.json").write_text(
                json.dumps(
                    {
                        "names": {"en": "Neon"},
                        "enabled": True,
                        "default": True,
                        "css_file": "style.css",
                        "tokens": {"color_scheme": "dark"},
                    }
                ),
                encoding="utf-8",
            )

            cfg = resolved_webapp_themes_catalog(
                theme_dir=themes_dir,
                primary_accent="#00fe7a",
                env_default_theme=None,
            )

            self.assertEqual(cfg.default_theme, "neon")
            self.assertIsNotNone(cfg.theme_by_key("neon"))
            self.assertEqual(
                {theme.key for theme in cfg.themes},
                {"dark", "light", "windows95", "ascii", "neon"},
            )

    def test_env_default_overrides_descriptor_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_dir = Path(tmp) / "themes"
            themes_dir.mkdir()
            (themes_dir / "neon").mkdir()
            (themes_dir / "neon" / "theme.json").write_text(
                json.dumps(
                    {
                        "names": {"en": "Neon"},
                        "enabled": True,
                        "default": True,
                        "tokens": {"color_scheme": "dark"},
                    }
                ),
                encoding="utf-8",
            )

            cfg = resolved_webapp_themes_catalog(
                theme_dir=themes_dir,
                primary_accent="#00fe7a",
                env_default_theme="windows95",
            )

            self.assertEqual(cfg.default_theme, "windows95")
            self.assertTrue(cfg.theme_by_key("windows95").default)
            self.assertFalse(cfg.theme_by_key("neon").default)

    def test_custom_descriptor_default_wins_over_seeded_core_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_dir = Path(tmp) / "themes"
            themes_dir.mkdir()
            (themes_dir / "dark").mkdir()
            (themes_dir / "dark" / "theme.json").write_text(
                json.dumps(
                    {
                        "key": "dark",
                        "names": {"en": "Dark"},
                        "enabled": True,
                        "default": True,
                        "tokens": {"color_scheme": "dark"},
                    }
                ),
                encoding="utf-8",
            )
            (themes_dir / "neon").mkdir()
            (themes_dir / "neon" / "theme.json").write_text(
                json.dumps(
                    {
                        "names": {"en": "Neon"},
                        "enabled": True,
                        "default": True,
                        "tokens": {"color_scheme": "dark"},
                    }
                ),
                encoding="utf-8",
            )

            cfg = resolved_webapp_themes_catalog(
                theme_dir=themes_dir,
                primary_accent="#00fe7a",
                env_default_theme=None,
            )

            self.assertEqual(cfg.default_theme, "neon")
            self.assertTrue(cfg.theme_by_key("neon").default)
            self.assertFalse(cfg.theme_by_key("dark").default)

    def test_theme_dir_writer_writes_descriptors_with_single_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = builtin_webapp_themes_config("#00fe7a")
            cfg = WebappThemesConfig(default_theme="windows95", themes=cfg.themes)
            themes_dir = Path(tmp) / "themes"

            write_webapp_theme_dir(themes_dir, cfg)

            dark = json.loads((themes_dir / "dark" / "theme.json").read_text(encoding="utf-8"))
            win95 = json.loads(
                (themes_dir / "windows95" / "theme.json").read_text(encoding="utf-8")
            )
            self.assertFalse(dark["default"])
            self.assertTrue(win95["default"])

            resolved = resolved_webapp_themes_catalog(
                theme_dir=themes_dir,
                primary_accent="#00fe7a",
                env_default_theme=None,
            )
            self.assertEqual(resolved.default_theme, "windows95")

    def test_resolved_falls_back_to_dark_when_saved_theme_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_dir = Path(tmp) / "themes"
            cfg = builtin_webapp_themes_config("#00fe7a")
            cfg = WebappThemesConfig(default_theme="windows95", themes=cfg.themes)
            write_webapp_theme_dir(themes_dir, cfg)
            windows_theme = themes_dir / "windows95" / "theme.json"
            windows_theme.unlink()

            resolved = resolved_webapp_themes_catalog(
                theme_dir=themes_dir,
                primary_accent="#00fe7a",
                env_default_theme=None,
            )

            self.assertEqual(resolved.default_theme, "dark")
            self.assertTrue(resolved.theme_by_key("dark").default)

    def test_public_payload_injects_primary_accent_when_enabled(self):
        cfg = builtin_webapp_themes_config("#abc123")

        payload = public_themes_catalog_payload(cfg, "#abc123")
        light = next(theme for theme in payload["themes"] if theme["key"] == "light")
        dark = next(theme for theme in payload["themes"] if theme["key"] == "dark")
        win95 = next(theme for theme in payload["themes"] if theme["key"] == "windows95")

        self.assertEqual(light["css_file"], "style.css")
        self.assertEqual(light["tokens"]["accent"], "#abc123")
        self.assertEqual(dark["tokens"]["accent"], "#abc123")
        self.assertFalse(win95["use_primary_accent"])
        self.assertTrue(win95["use_in_admin"])
        self.assertNotIn("accent", win95["tokens"])

    def test_theme_accent_is_normalized_to_hex(self):
        cfg = WebappThemesConfig(
            default_theme="custom",
            themes=[
                {
                    "key": "custom",
                    "enabled": True,
                    "default": True,
                    "tokens": {"color_scheme": "dark", "accent": "0F8"},
                }
            ],
        )

        self.assertEqual(cfg.theme_by_key("custom").tokens.accent, "#00ff88")

    def test_theme_home_logo_scale_is_public_token(self):
        cfg = WebappThemesConfig(
            default_theme="custom",
            themes=[
                {
                    "key": "custom",
                    "enabled": True,
                    "default": True,
                    "tokens": {"color_scheme": "dark", "home_logo_scale": 135},
                }
            ],
        )

        payload = public_themes_catalog_payload(cfg, "#abc123")
        custom = payload["themes"][0]

        self.assertEqual(cfg.theme_by_key("custom").tokens.home_logo_scale, 135)
        self.assertEqual(custom["tokens"]["home_logo_scale"], 135)

    def test_theme_accent_rejects_non_hex_values(self):
        with self.assertRaises(ValueError):
            WebappThemesConfig(
                default_theme="custom",
                themes=[
                    {
                        "key": "custom",
                        "enabled": True,
                        "default": True,
                        "tokens": {"color_scheme": "dark", "accent": "lime"},
                    }
                ],
            )

    def test_public_payload_keeps_admin_usage_flag(self):
        cfg = WebappThemesConfig(
            default_theme="custom",
            themes=[
                {
                    "key": "custom",
                    "names": {"en": "Custom"},
                    "enabled": True,
                    "default": True,
                    "use_in_admin": False,
                    "tokens": {"color_scheme": "dark"},
                }
            ],
        )

        payload = public_themes_catalog_payload(cfg, "#abc123")

        self.assertFalse(payload["themes"][0]["use_in_admin"])

    def test_resolved_refreshes_stale_builtin_windows95_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_dir = Path(tmp) / "themes"
            stale_theme_dir = themes_dir / "windows95"
            stale_theme_dir.mkdir(parents=True)
            (stale_theme_dir / "theme.json").write_text(
                json.dumps(
                    {
                        "key": "windows95",
                        "names": {"en": "Windows 95"},
                        "enabled": True,
                        "default": False,
                        "use_primary_accent": True,
                        "css_file": "style.css",
                        "assets_version": 1,
                        "tokens": {"color_scheme": "light", "style_preset": "win95"},
                    }
                ),
                encoding="utf-8",
            )
            (stale_theme_dir / "style.css").write_text("/* stale */", encoding="utf-8")

            cfg = resolved_webapp_themes_catalog(
                theme_dir=themes_dir,
                primary_accent="#00fe7a",
                env_default_theme=None,
            )

            descriptor = json.loads((stale_theme_dir / "theme.json").read_text(encoding="utf-8"))
            css = (stale_theme_dir / "style.css").read_text(encoding="utf-8")
            self.assertEqual(
                descriptor["assets_version"],
                cfg.theme_by_key("windows95").assets_version,
            )
            self.assertEqual(descriptor["assets_version"], 5)
            self.assertIn("lucide-house", css)
            self.assertIn("lucide-earth", css)
            self.assertIn("lucide-circle-check", css)
            self.assertIn("lucide-circle-check-big", css)
            self.assertIn("filter: none !important", css)
            self.assertIn("Press Start 2P", css)
            self.assertIn(".theme-key-windows95 .traffic-top strong", css)
            self.assertTrue((stale_theme_dir / "icons" / "dashboard.png").exists())

    def test_resolved_refreshes_stale_builtin_light_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_dir = Path(tmp) / "themes"
            stale_theme_dir = themes_dir / "light"
            stale_theme_dir.mkdir(parents=True)
            (stale_theme_dir / "theme.json").write_text(
                json.dumps(
                    {
                        "key": "light",
                        "names": {"en": "Light"},
                        "enabled": True,
                        "default": False,
                        "use_primary_accent": True,
                        "css_file": "style.css",
                        "assets_version": 1,
                        "tokens": {"color_scheme": "light"},
                    }
                ),
                encoding="utf-8",
            )
            (stale_theme_dir / "style.css").write_text("/* stale */", encoding="utf-8")

            resolved_webapp_themes_catalog(
                theme_dir=themes_dir,
                primary_accent="#00fe7a",
                env_default_theme=None,
            )

            css = (stale_theme_dir / "style.css").read_text(encoding="utf-8")
            self.assertIn(".theme-key-light.app-shell", css)
