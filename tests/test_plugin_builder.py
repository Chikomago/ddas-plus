import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from build_plugin import PLUGIN_FILES, build_plugin, validate_project


class PluginBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_dir = Path(__file__).resolve().parent.parent

    def test_project_matches_sanka_manifest(self):
        manifest = validate_project(self.project_dir)
        self.assertEqual(manifest["entry"], "main.py")
        self.assertEqual(manifest["runtime"], ["python"])

    def test_zip_contains_only_whitelisted_files_at_root(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "plugin.zip"
            build_plugin(self.project_dir, output)
            with ZipFile(output) as archive:
                names = archive.namelist()
                self.assertEqual(set(names), set(PLUGIN_FILES))
                self.assertTrue(all(not name.startswith("/") and ".." not in Path(name).parts for name in names))
                manifest = json.loads(archive.read("plugin.json"))
                self.assertIn(manifest["entry"], names)


if __name__ == "__main__":
    unittest.main()
