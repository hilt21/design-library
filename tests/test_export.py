import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import export, sync


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'library'
        shutil.copytree(export.ROOT, self.root, ignore=shutil.ignore_patterns('.git','__pycache__'))
        self.catalog = self.root / 'catalog.json'

    def update(self, edit):
        data = json.loads(self.catalog.read_text())
        edit(data['entries'])
        self.catalog.write_text(json.dumps(data))

    def test_export_matches_declared_files(self):
        export.check_export(self.root, export.export_files(export.build(self.root)))

    def test_normalized_alias_collision_is_rejected(self):
        self.update(lambda entries: entries[1]['aliases'].append('ＭＯＮＯ－ＣＯＬＯＲ'))
        with self.assertRaisesRegex(ValueError,'Conflicting alias'):
            export.build(self.root)

    def test_missing_prompt_is_rejected(self):
        (self.root/'entries/mono-color-editorial/PROMPT.md').unlink()
        with self.assertRaisesRegex(ValueError,'Files differ'):
            export.build(self.root)

    def test_self_dependency_is_rejected(self):
        self.update(lambda entries: entries[0]['required'].append('SKILL.md'))
        with self.assertRaisesRegex(ValueError,'self dependency'):
            export.build(self.root)

    def test_nested_json_and_source_hashes_are_checked(self):
        data = export.build(self.root)
        entry = data['entries']['mono-color-editorial']
        self.assertIn('design-system/colors.json',entry['files'])
        self.assertIn('design-system/recipes.json',entry['required'])
        (self.root/'entries/mono-color-editorial/design-system/colors.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Imported file drift'):
            export.build(self.root)

    def test_optional_resource_can_exceed_old_limit(self):
        path = self.root/'entries/mono-color-editorial/references/examples.md'
        path.write_text(path.read_text() + 'example\n'*1500)
        export.build(self.root)

    def test_path_escape_and_symlink_fail(self):
        self.update(lambda entries: entries[0]['required'].append('../secret.json'))
        with self.assertRaises(ValueError): export.build(self.root)
        path=self.root/'entries/mono-color-editorial/PROMPT.md'
        path.unlink()
        path.symlink_to(self.catalog)
        with self.assertRaisesRegex(ValueError,'Symlink'): export.build(self.root)


class SyncTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name)
        self.package=self.folder/'skills/design-library'
        self.package.mkdir(parents=True)
        (self.package/'SKILL.md').write_text('consumer adapter')
        self.data=export.build(export.ROOT)
        self.ids=['mono-color-editorial','channel-draft-review']
        self.sha='a'*40
        self.run_sync(self.sha)
        self.previous=export.inventory(self.package)
        self.pointer=(self.package/'index.json').read_bytes()

    def run_sync(self,sha):
        sync._sync_locked(export.ROOT,self.package,self.data,sha,self.ids)

    def assert_active_unchanged(self):
        self.assertEqual((self.package/'index.json').read_bytes(),self.pointer)
        sync.verify_previous(self.package)

    def test_failed_second_write_keeps_previous_snapshot(self):
        original=Path.write_bytes
        count=0
        def fail(path,data):
            nonlocal count
            count+=1
            if count==2: raise OSError('injected write failure')
            return original(path,data)
        with patch.object(Path,'write_bytes',fail), self.assertRaises(OSError):
            self.run_sync('b'*40)
        self.assert_active_unchanged()

    def test_failed_pointer_switch_keeps_previous_snapshot_and_retry_works(self):
        original=os.replace
        def fail(src,dst):
            if Path(dst)==self.package/'index.json': raise OSError('pointer failure')
            return original(src,dst)
        with patch('tools.sync.os.replace',fail), self.assertRaises(OSError):
            self.run_sync('b'*40)
        self.assert_active_unchanged()
        self.run_sync('b'*40)
        sync.verify_previous(self.package)
        self.assertEqual(export.as_json(self.package/'index.json')['commit_sha'],'b'*40)

    def test_repeat_is_idempotent_and_rollback_can_select_old_snapshot(self):
        self.run_sync(self.sha)
        self.assertEqual(export.inventory(self.package),self.previous)
        self.run_sync('b'*40)
        self.run_sync(self.sha)
        self.assert_active_unchanged()

    def test_local_edit_is_preserved_and_blocks_sync(self):
        state=export.as_json(self.package/'index.json')
        path=self.package/state['snapshot']/'entries/mono-color-editorial/PROMPT.md'
        path.write_text('local edit')
        with self.assertRaisesRegex(ValueError,'local changes'):
            self.run_sync('b'*40)
        self.assertEqual(path.read_text(),'local edit')

    def test_migrates_legacy_snapshot(self):
        legacy=self.folder/'legacy'
        files={}
        for eid in self.ids:
            entry=self.data['entries'][eid]
            for name in [entry['entry'],*entry['required']]:
                file=legacy/'entries'/eid/name
                file.parent.mkdir(parents=True,exist_ok=True)
                file.write_bytes((export.ROOT/'entries'/eid/name).read_bytes())
                files[file.relative_to(legacy).as_posix()]=export.digest(file.read_bytes())
        (legacy/'index.json').write_bytes(export.encode({'schema_version':1,'entries':{'legacy':{'files':files}}}))
        sync._sync_locked(export.ROOT,legacy,self.data,self.sha,self.ids)
        sync.verify_previous(legacy)


if __name__=='__main__': unittest.main()
