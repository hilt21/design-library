import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools import export


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(export.ROOT / "entries", self.root / "entries")
        self.catalog = self.root / "catalog.json"
        shutil.copyfile(export.ROOT / "catalog.json", self.catalog)

    def update(self, edit):
        data = json.loads(self.catalog.read_text())
        edit(data["entries"])
        self.catalog.write_text(json.dumps(data))

    def test_export_matches_declared_files(self):
        self.assertEqual(export.encode(export.build(self.root)),
                         (export.ROOT / export.EXPORT).read_bytes())

    def test_normalized_alias_collision_is_rejected(self):
        self.update(lambda entries: entries[1]["aliases"].append("ＭＯＮＯ－ＣＯＬＯＲ"))
        with self.assertRaisesRegex(ValueError, "conflicting alias"):
            export.build(self.root)

    def test_missing_prompt_is_rejected(self):
        (self.root / "entries/mono-color-editorial/PROMPT.md").unlink()
        with self.assertRaisesRegex(ValueError, "Files differ"):
            export.build(self.root)

    def test_self_dependency_is_rejected(self):
        self.update(lambda entries: entries[0]["dependencies"].append("SKILL.md"))
        with self.assertRaisesRegex(ValueError, "self dependency"):
            export.build(self.root)
