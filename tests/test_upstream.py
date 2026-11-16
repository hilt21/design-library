import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.check_upstream import compare


class UpstreamTests(unittest.TestCase):
    def test_change_report_maps_only_watched_paths_to_cases(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def git(*args):
                return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.DEVNULL).strip()
            git('init','-q')
            git('config','user.name','Test')
            git('config','user.email','test@example.invalid')
            (root/'SKILL.md').write_text('first')
            git('add','.')
            git('commit','-qm','first')
            baseline=git('rev-parse','HEAD')
            entry={'id':'example','source':{'repository':'example/skill','path':'SKILL.md','commit':baseline},'cases':['cover']}
            (root/'README.md').write_text('unrelated')
            git('add','.')
            git('commit','-qm','docs')
            self.assertEqual(compare(entry,root,'HEAD')['review_status'],'unchanged')
            (root/'SKILL.md').write_text('changed')
            git('add','.')
            git('commit','-qm','method')
            report=compare(entry,root,'HEAD')
            self.assertEqual(report['review_status'],'needs-review')
            self.assertEqual(report['affected_cases'],['cover'])
            self.assertEqual(git('rev-parse','HEAD'),report['candidate_commit'])
