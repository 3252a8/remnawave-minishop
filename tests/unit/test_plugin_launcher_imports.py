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
            timeout=30,
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
            "assert bot.plugins.register is register\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)

    def test_bot_utils_lazy_exports_load_on_demand(self) -> None:
        code = (
            "import sys\n"
            "import bot.utils\n"
            "assert 'aiogram' not in sys.modules\n"
            "from bot.utils import Bot, types\n"
            "assert 'aiogram' in sys.modules\n"
            "assert Bot is sys.modules['aiogram'].Bot\n"
            "assert types is sys.modules['aiogram'].types\n"
            "assert bot.utils.__dict__['Bot'] is Bot\n"
            "assert bot.utils.__dict__['types'] is types\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)

    def test_spec_exports_do_not_load_the_plugin_loader(self) -> None:
        code = (
            "import sys\n"
            "from bot.plugins import Plugin, PluginContext, WorkerTaskSpec\n"
            "from bot.plugins import spec\n"
            "assert Plugin is spec.Plugin\n"
            "assert PluginContext is spec.PluginContext\n"
            "assert WorkerTaskSpec is spec.WorkerTaskSpec\n"
            "assert 'bot.plugins.loader' not in sys.modules\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)

    def test_all_public_plugin_exports_remain_available(self) -> None:
        code = (
            "import bot.plugins as plugins\n"
            "from bot.plugins import loader, spec\n"
            "loader_exports = {\n"
            "    'apply_plugin_locales', 'collect_migrations', 'collect_queue_handlers',\n"
            "    'collect_worker_tasks', 'configure_entitlements', 'get_plugins',\n"
            "    'register', 'reset_plugins', 'run_setup', 'setup_bot_plugins',\n"
            "    'setup_web_plugins',\n"
            "}\n"
            "spec_exports = {\n"
            "    'ENTRY_POINT_GROUP', 'PLUGIN_API_VERSION', 'WEB_SCOPE_WEBAPP',\n"
            "    'WEB_SCOPE_WEBHOOKS', 'Plugin', 'PluginApiCompatibilityError',\n"
            "    'PluginContext', 'PluginLocaleGroup', 'QueueHandler', 'WorkerTaskSpec',\n"
            "    'validate_plugin_api_compatibility',\n"
            "}\n"
            "assert set(plugins.__all__) == loader_exports | spec_exports\n"
            "namespace = {}\n"
            "exec('from bot.plugins import *', namespace)\n"
            "for module, names in [(loader, loader_exports), (spec, spec_exports)]:\n"
            "    for name in names:\n"
            "        expected = getattr(module, name)\n"
            "        assert getattr(plugins, name) is expected, name\n"
            "        assert plugins.__dict__[name] is expected, name\n"
            "        assert namespace[name] is expected, name\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)

    def test_unknown_exports_raise_attribute_error(self) -> None:
        code = (
            "import bot.plugins\n"
            "import bot.utils\n"
            "for module in (bot.plugins, bot.utils):\n"
            "    try:\n"
            "        getattr(module, 'missing_export')\n"
            "    except AttributeError:\n"
            "        pass\n"
            "    else:\n"
            "        raise AssertionError(module.__name__)\n"
        )
        result = self._run_python(code)
        self.assertEqual(result.returncode, 0)
