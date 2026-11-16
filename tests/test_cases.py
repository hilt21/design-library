"""Recheck saved agent artifacts. These checks do not claim a new model or image run."""
import json
import re
import unittest
from pathlib import Path
from tools.export import ROOT, digest


class SavedCaseTests(unittest.TestCase):
    def test_artifact_bytes_and_output_contracts(self):
        folder = ROOT / 'evals/agent-comparison'
        inputs = json.loads((folder / 'inputs.json').read_text())
        for variant in ('baseline', 'candidate'):
            data = (folder / inputs[variant]['artifact']).read_bytes()
            self.assertEqual(digest(data), inputs[variant]['artifact_sha256'])
            cases = json.loads(data)['cases']
            self.assertEqual([c['id'] for c in cases], ['A', 'B'])
            a, b = cases
            self.assertLessEqual(len(a['title']), 20)
            self.assertTrue(150 <= len(re.sub(r'\s', '', a['body'])) <= 250)
            self.assertTrue(100 <= len(b['body'].split()) <= 150)
            for case, text, ratio in ((a, '制动状态如何验证？', '3:4'), (b, 'Make braking observable', '4:3')):
                recipe = case['recipe']
                self.assertEqual(len(recipe['inks']), 1)
                self.assertEqual(recipe.get('exact_text', recipe.get('cover_text')), text)
                self.assertIn(text, case['prompt'])
                self.assertEqual(recipe.get('aspect_ratio', recipe.get('canvas', {}).get('aspect_ratio')), ratio)
                self.assertIn(recipe['paper']['hex'], case['prompt'])
                self.assertIn(recipe['inks'][0]['hex'], case['prompt'])
                self.assertIn('SIL', case['body'])
            if variant == 'candidate':
                recipes = json.loads((ROOT / 'entries/mono-color-editorial/design-system/recipes.json').read_text())['recipes']
                by_id = {r['id']: r for r in recipes}
                for case in cases:
                    actual = case['recipe']
                    expected = by_id[actual['id']]
                    self.assertEqual(actual['paper']['hex'], expected['substrate']['hex'])
                    self.assertEqual(actual['inks'][0]['hex'], expected['ink']['hex'])
                    self.assertEqual(actual['composition']['id'], expected['composition']['id'])
                    self.assertEqual(actual['typography']['id'], expected['typography']['id'])
                for path, expected in inputs[variant]['files'].items():
                    self.assertEqual(digest((ROOT / path).read_bytes()), expected)


if __name__ == '__main__':
    unittest.main()
