"""Exercise real owned file creation, report checks and preservation boundaries."""
import copy,gzip,json,re,tempfile,unittest
from pathlib import Path
import capture_files as f
import capture_checks as checks
from demo_note import make_note,validate_note

class CaptureFiles(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.state=f.create(self.root/'demo',[self.root/'roaming',self.root/'local'])
    def test_original_note_and_owned_cleanup(self):
        self.assertEqual(validate_note(make_note())['pages'],1)
        self.assertEqual(make_note(),make_note())
        seal=f.verify(self.state,False)
        with self.assertRaisesRegex(ValueError,'stopped'):f.cleanup(self.state,seal,False)
        self.assertTrue(f.cleanup(self.state,seal,True)['removed'])
    def test_existing_or_changed_content_is_preserved(self):
        with self.assertRaisesRegex(ValueError,'Existing'):f.create(self.root/'demo',[self.root/'x',self.root/'y'])
        seal=f.verify(self.state,False);p=self.root/'local/new.txt';p.write_text('retained')
        with self.assertRaisesRegex(ValueError,'changed'):f.cleanup(self.state,seal,True)
        self.assertEqual(p.read_text(),'retained')
    def test_linked_profile_is_preserved(self):
        (self.root/'roaming/link').symlink_to(self.root/'local',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Linked'):f.verify(self.state,False)
    def test_report_must_name_exact_original_and_actual_pdf(self):
        root=Path(self.state['root']);(root/f.PDF).write_bytes(b'%PDF-1.7\n'+b'fixture'*200)
        report=dict(version=1,status='passed',expectedPages=1,actualPages=1,outputBytes=(root/f.PDF).stat().st_size,error='',published=True,recoveryFiles=[],output=str(root/f.PDF),protectedFiles=[dict(path=str(root/f.NOTE),sha256Before=self.state['original']['sha256'])])
        path=root/(f.PDF+'.01234567-1234-1234-1234-0123456789ab.inkquay-report.json');path.write_text(json.dumps(report))
        self.assertTrue(f.verify(self.state,True)['complete'])
        for key,value in [('actualPages',True),('status','failed'),('outputBytes',0),('published',False),('output',str(root/'other.pdf'))]:
            changed=copy.deepcopy(report);changed[key]=value;path.write_text(json.dumps(changed))
            with self.subTest(key=key),self.assertRaises(ValueError):f.verify(self.state,True)
        path.write_text(json.dumps(report));(root/f.NOTE).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Original'):f.verify(self.state,True)
    def test_pdf_reopen_does_not_autoload_the_original_notebook(self):
        # Read the unchanged product route/default. This is a filename fixture
        # regression, not a replacement for actual installed PDF reopening.
        source=Path(__file__).resolve().parents[2]
        control=(source/'src/core/control/Control.cpp').read_text()
        settings=(source/'src/core/control/settings/Settings.cpp').read_text()
        route=control.split('if (Util::hasPdfFileExt(filepath)) {',1)[1].split('callback(this->openPdfFile',1)[0]
        self.assertIn('this->settings->isAutoloadPdfXoj()',route)
        self.assertIn('this->autoloadPdfXoj = true;',settings)
        extensions=re.findall(r'"([^"\n]+)"',re.search(r'const std::vector<std::string> exts = \{([^}]+)\}',route).group(1))
        self.assertEqual(extensions,['.xopp','.xoj','.pdf.xopp','.pdf.xoj'])
        self.assertIn('this->openXoppFile(std::move(f)',route)
        root=Path(self.state['root'])
        original_stem=Path(f.NOTE).stem
        self.assertEqual([p.name for p in (root/(original_stem+ext) for ext in extensions) if p.exists()],[f.NOTE])
        # Old capture PDF stem chose the existing xopp; the handout must reach
        # the normal PDF route without changing application settings or input.
        pdf_stem=Path(f.PDF).stem
        self.assertEqual([p.name for p in (root/(pdf_stem+ext) for ext in extensions) if p.exists()],[])
        for ext in extensions:
            companion=root/(pdf_stem+ext)
            companion.write_bytes(b'unexpected companion')
            try:
                with self.subTest(extension=ext),self.assertRaisesRegex(ValueError,'Unexpected demo output'):
                    f.verify(self.state,False)
                self.assertTrue(companion.exists())
            finally:companion.unlink()

    def test_unbound_and_unsafe_artifacts_fail(self):
        with self.assertRaisesRegex(ValueError,'reviewed'):checks.validate_binding(dict(schema_version=1,product='Scriblark',qualified=None))
        for name in ('../private','/absolute','C:drive','a\\b','a//b','a/./b'):
            with self.subTest(name=name),self.assertRaises(ValueError):checks.relative_path(name)

if __name__=='__main__':unittest.main()
