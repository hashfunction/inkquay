"""Production diagnostic-tool source patch and receipt binding regressions."""
import copy
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import observer_gdb_build as build


class DiagnosticToolTests(unittest.TestCase):
    def test_worker_patch_is_exact_single_use_and_preserves_other_code(self):
        original='prefix\n'+build.ATTACH_OLD+'middle\n'+build.OUTSIDE_OLD+'suffix\n'
        changed=build.patch_worker(original)
        self.assertEqual('prefix\n'+build.ATTACH_NEW+'middle\n'+build.OUTSIDE_NEW+'suffix\n',changed)
        self.assertIn('else if (!DebugSetProcessKillOnExit (FALSE))',changed)
        self.assertLess(changed.index('DebugSetProcessKillOnExit'),changed.index('return ok;'))
        self.assertIn('DebugActiveProcessStop (pid);',changed)
        for invalid in (changed,original+build.ATTACH_OLD,original.replace('return ok;','return TRUE;')):
            with self.assertRaises(ValueError):build.patch_worker(invalid)

    def test_build_receipt_requires_current_source_inputs_patch_and_exact_tool(self):
        inputs={'compiler':{'sha256':'a'*64}};tool={'bytes':123,'sha256':'b'*64}
        value={'schema_version':1,'built':True,'diagnostic_only':True,'consumer_acceptance':False,
            'source_commit':'c'*40,'workflow_run_id':'123','workflow_run_attempt':'1',
            'gnu_source':build.GNU_SOURCE,'source_before_sha256':build.WINDOWS_NAT_SHA256,
            'source_after_sha256':build.PATCHED_SHA256,'inputs':inputs,'tool':tool,'error':None}
        check=lambda row:build.validate_record(row,inputs,tool,'c'*40,'123','1')
        check(value)
        for key,changed in [('built',1),('built',False),('consumer_acceptance',True),('source_commit','d'*40),
                ('workflow_run_id','122'),('workflow_run_attempt','2'),('inputs',{}),('tool',{}),
                ('gnu_source',{}),('source_after_sha256','0'*64),('error','build failed')]:
            row=copy.deepcopy(value);row[key]=changed
            with self.subTest(key=key),self.assertRaises(ValueError):check(row)

    def test_real_archive_extraction_preserves_regular_source_and_rejects_escapes_links(self):
        for name,kind in [('gdb-17.2/source.c',tarfile.REGTYPE),('../escape',tarfile.REGTYPE),('gdb-17.2/link',tarfile.SYMTYPE)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);archive=root/'source.tar.xz';dest=root/'out';dest.mkdir()
                with tarfile.open(archive,'w:xz') as stream:
                    row=tarfile.TarInfo(name);row.type=kind;row.size=1 if kind==tarfile.REGTYPE else 0;row.linkname='outside';row.mtime=123456789
                    stream.addfile(row,io.BytesIO(b'x'))
                if name=='gdb-17.2/source.c':
                    build.extract_source(archive,dest);self.assertEqual(b'x',(dest/name).read_bytes())
                    self.assertEqual(123456789,int((dest/name).stat().st_mtime),'Generated GNU build-file timestamps were lost')
                else:
                    with self.assertRaises(ValueError):build.extract_source(archive,dest)

    def test_actual_tool_and_runtime_bytes_must_match_before_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'mingw64/bin';prefix.mkdir(parents=True)
            tool=root/'gdb.exe';tool.write_bytes(b'original');dll=prefix/'runtime.dll';dll.write_bytes(b'runtime')
            record=root/'record.json';inputs={'compiler':{'sha256':'a'*64}}
            value={'schema_version':1,'built':True,'diagnostic_only':True,'consumer_acceptance':False,
                'source_commit':'c'*40,'workflow_run_id':'123','workflow_run_attempt':'1','gnu_source':build.GNU_SOURCE,
                'source_before_sha256':build.WINDOWS_NAT_SHA256,'source_after_sha256':build.PATCHED_SHA256,
                'inputs':inputs,'tool':build.file_record(tool),'error':None,'runtime_files':{str(dll):build.file_record(dll)}}
            record.write_text(json.dumps(value))
            with patch.object(build,'RECORD',record),patch.object(build,'TOOL',tool),patch.object(build,'build_inputs',return_value=inputs),\
                    patch.object(build.sys,'executable',str(prefix/'python.exe')),patch.dict(os.environ,{'GITHUB_SHA':'c'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}):
                self.assertEqual(tool.resolve(),build.verified_debugger())
                tool.write_bytes(b'changed!')
                with self.assertRaisesRegex(ValueError,'receipt'):build.verified_debugger()
                tool.write_bytes(b'original');dll.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'runtime bytes'):build.verified_debugger()

    def test_failed_build_keeps_failure_even_if_executable_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record=root/'result.json'
            (root/'request.json').write_text(json.dumps({'schema_version':1,'built':False,'diagnostic_only':True,'consumer_acceptance':False}))
            (root/'gdb.exe').write_bytes(b'partial')
            with patch.object(build,'BUILD',root),patch.object(build,'RECORD',record):
                with self.assertRaisesRegex(ValueError,'unavailable'):build.finish(7)
            result=json.loads(record.read_text());self.assertIs(result['built'],False);self.assertIn('exit 7',result['error'])


if __name__=='__main__':unittest.main()
