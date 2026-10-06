import tempfile
import unittest
from pathlib import Path

from qa_tools.source_files import iter_source_files


class SourceTraversalTests(unittest.TestCase):
    def test_nested_first_party_is_checked_and_dependency_trees_are_pruned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("frontend/src/nested", "frontend/node_modules", ".venv-tools/lib"):
                directory = root / name
                directory.mkdir(parents=True)
                (directory / "module.py").write_text("pass\n", encoding="utf-8")
            files = {path.relative_to(root).as_posix() for path in iter_source_files(root, {".py"})}
            self.assertEqual(files, {"frontend/src/nested/module.py"})
