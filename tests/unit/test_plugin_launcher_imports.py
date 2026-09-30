from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import TestCase

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


class PluginLauncherImportIsolationTests(TestCase):
    def _run_python(self, code: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            check=True,
        )

    def test_packages_module_does_not_import_aiogram_or_sqlalchemy(self) -> None:
        code = (
            "import sys\n"
            "import bot.plugins.packages\n"
            "assert 'aiogram' not in sys.modules, 'aiogram leaked into sys.modules'\n"
            "assert 'sqlalchemy' not in sys.modules, 'sqlalchemy leaked into sys.modules'\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)

    def test_plugin_launcher_does_not_import_aiogram_or_sqlalchemy(self) -> None:
        code = (
            "import sys\n"
            "import plugin_launcher\n"
            "assert 'aiogram' not in sys.modules, 'aiogram leaked into sys.modules'\n"
            "assert 'sqlalchemy' not in sys.modules, 'sqlalchemy leaked into sys.modules'\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)

    def test_bot_plugins_lazy_exports_load_on_demand(self) -> None:
        code = (
            "import sys\n"
            "import bot.plugins\n"
            "assert 'aiogram' not in sys.modules\n"
            "assert 'sqlalchemy' not in sys.modules\n"
            "# Access an export that triggers loader\n"
            "register = bot.plugins.register\n"
            "assert callable(register)\n"
            "# Now loader has been loaded\n"
            "assert 'bot.plugins.loader' in sys.modules\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)

    def test_bot_utils_lazy_exports_load_on_demand(self) -> None:
        code = (
            "import sys\n"
            "import bot.utils\n"
            "assert 'aiogram' not in sys.modules\n"
            "# Access Bot on bot.utils\n"
            "Bot = bot.utils.Bot\n"
            "assert 'aiogram' in sys.modules\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)
