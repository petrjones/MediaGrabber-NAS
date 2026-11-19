"""Localization completeness checks for the actual shipped UI assets."""
import json
import re
import unittest
from pathlib import Path

STATIC=Path(__file__).resolve().parents[1]/'mg_nas/static'

class LocalizationTests(unittest.TestCase):
    def test_all_nine_windows_languages_have_complete_ui_and_help(self):
        source=(STATIC/'locales.js').read_text(encoding='utf-8')
        languages=json.loads(source.split('const LANGUAGES=',1)[1].split(';',1)[0])
        catalogs=json.loads(source.split('const STRINGS=',1)[1].rstrip().removesuffix(';'))
        self.assertEqual([x[0] for x in languages],['cs','en','es','de','fr','pt-PT','pt-BR','pl','it'])
        expected=set(catalogs['en'])
        used=set(re.findall(r'data-t="([\w]+)"',(STATIC/'index.html').read_text(encoding='utf-8')))
        used.update(re.findall(r'data-t="([\w]+)"',(STATIC/'app.js').read_text(encoding='utf-8')))
        used.update(re.findall(r"(?<![\w])t\('([\w]+)'\)",(STATIC/'app.js').read_text(encoding='utf-8')))
        used.discard('status_') # Dynamic status key is checked below.
        for language,_ in languages:
            with self.subTest(language=language):
                self.assertEqual(set(catalogs[language]),expected)
                self.assertTrue(used <= set(catalogs[language]),used-set(catalogs[language]))
                self.assertTrue(all(isinstance(v,str) and v.strip() for v in catalogs[language].values()))
                for key in ('initialHelp','existingHelp','newExplanation','allExplanation','dateExplanation','lockedHelp','hintType','hintDuplicates','hintCheck','hintLogin'):
                    self.assertGreater(len(catalogs[language][key]),35)
                for status in ('queued','processing','running','pending','completed','done','skipped','failed','partial','paused','interrupted','cancelled','waiting','checking','baseline','ok','error'):
                    self.assertIn('status_'+status,catalogs[language])

    def test_catalog_is_loaded_before_application_and_help_is_visible(self):
        html=(STATIC/'index.html').read_text(encoding='utf-8')
        self.assertLess(html.index('src="locales.js"'),html.index('src="app.js"'))
        self.assertIn('data-t="initialHelp"',html)
        self.assertIn('data-t="existingHelp"',html)
        self.assertIn('id="source-mode-help"',html)
        app=(STATIC/'app.js').read_text(encoding='utf-8')
        self.assertIn("'pointerover'",app)
        self.assertIn("'focusin'",app)
        self.assertIn("'aria-description'",app)

if __name__=='__main__': unittest.main()
