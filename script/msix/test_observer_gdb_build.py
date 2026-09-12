"""Production diagnostic-tool source patch and receipt binding regressions."""
import copy
import io
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import observer_gdb_build as build


def native_pe():
    raw=bytearray(256);raw[:2]=b'MZ';struct.pack_into('<I',raw,60,64)
    raw[64:68]=b'PE\0\0';struct.pack_into('<H',raw,68,0x8664)
    struct.pack_into('<H',raw,86,2);struct.pack_into('<H',raw,88,0x20b)
    return bytes(raw)


class DiagnosticToolTests(unittest.TestCase):
    def test_real_libtool_output_selection_excludes_launcher_and_requires_one_native_executable(self):
        for relative in ('build/gdb/.libs/gdb.exe','build/gdb/.libs/lt-gdb.exe'):
            with self.subTest(relative=relative),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);launcher=root/'build/gdb/gdb.exe';launcher.parent.mkdir(parents=True);launcher.write_bytes(native_pe())
                with patch.object(build,'BUILD',root):
                    self.assertTrue(callable(getattr(build,'resolve_tool',None)), 'Production debugger selection still points at the Libtool launcher')
                    with self.assertRaisesRegex(ValueError,'exactly one'):build.resolve_tool()
                    tool=root/relative;tool.parent.mkdir();tool.write_bytes(native_pe())
                    self.assertEqual(tool,build.resolve_tool())
                    other=tool.parent/('gdb.exe' if tool.name=='lt-gdb.exe' else 'lt-gdb.exe');other.write_bytes(native_pe())
                    with self.assertRaisesRegex(ValueError,'exactly one'):build.resolve_tool()
                    other.unlink()
                    for invalid in (b'MZ',native_pe().replace(b'PE\0\0',b'NOPE'),native_pe().replace(b'd\x86',b'L\x01'),native_pe().replace(b'\x0b\x02',b'\x0b\x01')):
                        tool.write_bytes(invalid)
                        with self.assertRaises(ValueError):build.resolve_tool()
                    # Replay the Windows reparse bit through the real lstat
                    # guard without requiring the runner's symlink privilege.
                    tool.write_bytes(native_pe());real_lstat=Path.lstat
                    def lstat(path):
                        info=real_lstat(path)
                        return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400) if path==tool else info
                    with patch.object(Path,'lstat',autospec=True,side_effect=lstat):
                        with self.assertRaisesRegex(ValueError,'reparse'):build.resolve_tool()
                    if os.name!='nt':
                        tool.unlink();tool.symlink_to(launcher)
                        with self.assertRaisesRegex(ValueError,'Symlink'):build.resolve_tool()

    def test_empty_runtime_closure_cannot_be_recorded_as_a_built_debugger(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record=root/'result.json';tool=root/'build/gdb/.libs/gdb.exe';tool.parent.mkdir(parents=True);tool.write_bytes(native_pe())
            native=root/'source/gdb-17.2/gdb/windows-nat.c';native.parent.mkdir(parents=True);native.write_bytes(b'fixture')
            (native.parent.parent/'COPYING3').write_bytes(b'fixture license')
            inputs={'compiler':{'sha256':'a'*64}}
            (root/'request.json').write_text(json.dumps({'schema_version':1,'built':False,'diagnostic_only':True,'consumer_acceptance':False,'inputs':inputs}))
            real_file_record=build.file_record
            def file_record(path):
                return {'sha256':build.PATCHED_SHA256} if Path(path)==native else real_file_record(path)
            with patch.object(build,'BUILD',root),patch.object(build,'RECORD',record),\
                    patch.object(build,'build_inputs',return_value=inputs),patch.object(build,'file_record',side_effect=file_record),patch.object(build,'runtime_files',return_value={}):
                with self.assertRaisesRegex(ValueError,'runtime binding'):build.finish(0)
            value=json.loads(record.read_text());self.assertIs(value['built'],False);self.assertIn('runtime binding',value['error'])

    def test_successful_finish_records_real_payload_path_and_nonempty_closure_without_throwing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record=root/'result.json';tool=root/'build/gdb/.libs/lt-gdb.exe';tool.parent.mkdir(parents=True);tool.write_bytes(native_pe())
            native=root/'source/gdb-17.2/gdb/windows-nat.c';native.parent.mkdir(parents=True);native.write_bytes(b'fixture')
            (native.parent.parent/'COPYING3').write_bytes(b'fixture license')
            inputs={'compiler':{'sha256':'a'*64}};runtime={'fixture.dll':{'bytes':123,'sha256':'b'*64}}
            (root/'request.json').write_text(json.dumps({'schema_version':1,'built':False,'diagnostic_only':True,'consumer_acceptance':False,'inputs':inputs}))
            real_file_record=build.file_record
            def file_record(path):
                return {'sha256':build.PATCHED_SHA256} if Path(path)==native else real_file_record(path)
            with patch.object(build,'BUILD',root),patch.object(build,'RECORD',record),patch.object(build,'build_inputs',return_value=inputs),\
                    patch.object(build,'file_record',side_effect=file_record),patch.object(build,'runtime_files',return_value=runtime) as closure:
                build.finish(0);closure.assert_called_once_with(tool)
            value=json.loads(record.read_text());self.assertIs(value['built'],True);self.assertIsNone(value['error'])
            self.assertEqual('build/gdb/.libs/lt-gdb.exe',value['tool_relative_path']);self.assertEqual(build.file_record(tool),value['tool'])
            self.assertEqual(runtime,value['runtime_files']);self.assertIs(value['consumer_acceptance'],False)

    def test_runtime_import_graph_starts_at_real_payload_and_rejects_unresolved_dlls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'mingw64/bin';prefix.mkdir(parents=True)
            tool=root/'build/gdb/.libs/gdb.exe';tool.parent.mkdir(parents=True);tool.write_bytes(native_pe())
            runtime=prefix/'runtime.dll';runtime.write_bytes(b'first');child=prefix/'child.dll';child.write_bytes(b'second')
            system=root/'Windows/System32';system.mkdir(parents=True);(system/'KERNEL32.dll').write_bytes(b'OS fixture')
            imports={tool:b'DLL Name: runtime.dll\nDLL Name: KERNEL32.dll',runtime:b'DLL Name: child.dll',child:b'DLL Name: KERNEL32.dll'}
            observed=[]
            def objdump(arguments,**kwargs):
                observed.append(Path(arguments[-1]));return imports[observed[-1]]
            with patch.object(build.sys,'executable',str(prefix/'python.exe')),patch.dict(os.environ,{'SystemRoot':str(system.parent)}),\
                    patch.object(build.subprocess,'check_output',side_effect=objdump):
                self.assertEqual({str(p.resolve()):build.file_record(p) for p in (runtime,child)},build.runtime_files(tool))
                self.assertEqual(tool,observed[0]);self.assertEqual({tool,runtime,child},set(observed))
                imports[child]=b'DLL Name: foreign.dll'
                with self.assertRaisesRegex(ValueError,'Unresolved diagnostic DLL'):build.runtime_files(tool)

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
            'source_after_sha256':build.PATCHED_SHA256,'inputs':inputs,'tool':tool,'tool_relative_path':'build/gdb/.libs/gdb.exe','error':None}
        check=lambda row:build.validate_record(row,inputs,tool,'c'*40,'123','1','build/gdb/.libs/gdb.exe')
        check(value)
        for key,changed in [('built',1),('built',False),('consumer_acceptance',True),('source_commit','d'*40),
                ('workflow_run_id','122'),('workflow_run_attempt','2'),('inputs',{}),('tool',{}),
                ('gnu_source',{}),('source_after_sha256','0'*64),('error','build failed'),('tool_relative_path','build/gdb/gdb.exe'),('tool_relative_path','build/gdb/.libs/lt-gdb.exe')]:
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
            tool=root/'build/gdb/.libs/gdb.exe';tool.parent.mkdir(parents=True);tool.write_bytes(native_pe());dll=prefix/'runtime.dll';dll.write_bytes(b'runtime')
            record=root/'record.json';inputs={'compiler':{'sha256':'a'*64}}
            value={'schema_version':1,'built':True,'diagnostic_only':True,'consumer_acceptance':False,
                'source_commit':'c'*40,'workflow_run_id':'123','workflow_run_attempt':'1','gnu_source':build.GNU_SOURCE,
                'source_before_sha256':build.WINDOWS_NAT_SHA256,'source_after_sha256':build.PATCHED_SHA256,
                'inputs':inputs,'tool':build.file_record(tool),'tool_relative_path':'build/gdb/.libs/gdb.exe','error':None,'runtime_files':{str(dll):build.file_record(dll)}}
            record.write_text(json.dumps(value))
            with patch.object(build,'RECORD',record),patch.object(build,'BUILD',root),patch.object(build,'build_inputs',return_value=inputs),\
                    patch.object(build.sys,'executable',str(prefix/'python.exe')),patch.dict(os.environ,{'GITHUB_SHA':'c'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}):
                self.assertEqual(tool.resolve(),build.verified_debugger())
                tool.write_bytes(native_pe()+b'changed!')
                with self.assertRaisesRegex(ValueError,'receipt'):build.verified_debugger()
                tool.write_bytes(native_pe());dll.write_bytes(b'changed')
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
