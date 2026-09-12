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


def importing_pe(imports=(), delay=(), padding=0):
    """Real PE32+ descriptor/name bytes; fixture only, never an executable run."""
    raw=bytearray(0x2400+padding);raw[:2]=b'MZ';struct.pack_into('<I',raw,60,64)
    raw[64:68]=b'PE\0\0';struct.pack_into('<HH',raw,68,0x8664,2)
    struct.pack_into('<HH',raw,84,240,2);struct.pack_into('<H',raw,88,0x20b)
    struct.pack_into('<Q',raw,112,0x140000000);struct.pack_into('<I',raw,148,0x400)
    struct.pack_into('<I',raw,196,16)
    raw[328:336]=b'.idata\0\0';struct.pack_into('<IIII',raw,336,0x2000,0x1000,0x2000,0x400)
    raw[368:376]=b'.pdata\0\0';struct.pack_into('<IIII',raw,376,padding,0x4000,padding,0x2400)
    for index,names,width,offset in ((1,imports,20,0x400),(13,delay,32,0xc00)):
        if not names:continue
        struct.pack_into('<II',raw,200+index*8,offset+0xc00,(len(names)+1)*width)
        for n,name in enumerate(names):
            at=0x1800+(0 if index==1 else 0x400)+n*64
            encoded=name.encode('ascii')+b'\0';raw[at:at+len(encoded)]=encoded
            if index==1:struct.pack_into('<IIIII',raw,offset+n*width,0x1800,0,0,at+0xc00,0x1800)
            else:struct.pack_into('<8I',raw,offset+n*width,1,at+0xc00,0x1800,0x1800,0x1800,0,0,0)
    return bytes(raw)


class DiagnosticToolTests(unittest.TestCase):
    def test_pe_descriptor_boundaries_reject_malformed_names_ranges_and_counts(self):
        valid=importing_pe(['runtime.dll'],['delayed.dll'])
        mutations=[]
        for offset,fmt,value in ((60,'I',1048577),(68,'H',0x14c),(70,'H',97),(84,'H',111),
                (88,'H',0x10b),(148,'I',100),(196,'I',17),(212,'I',1048577),
                (208,'I',0xfffffff0),(0x40c,'I',0x3000),(0xc00,'I',0)):
            raw=bytearray(valid);struct.pack_into('<'+fmt,raw,offset,value);mutations.append(raw)
        mutations.extend((valid[:30],valid[:-1],valid.replace(b'PE\0\0',b'NOPE'),
                          valid.replace(b'runtime.dll',b'../evil.dll'),valid.replace(b'runtime.dll',b'\xffuntime.dll')))
        raw=bytearray(valid);raw[0x1800:0x1900]=b'a'*256;mutations.append(raw)
        raw=bytearray(valid);raw[0x1800]=0;mutations.append(raw)
        raw=bytearray(valid);struct.pack_into('<I',raw,212,20);mutations.append(raw) # no null descriptor
        raw=bytearray(valid);struct.pack_into('<IIII',raw,376,0x2000,0x1000,0,0);mutations.append(raw) # ambiguous RVA
        raw=bytearray(valid);struct.pack_into('<IIII',raw,376,0x2000,0x4000,0,0)
        struct.pack_into('<I',raw,0x40c,0x4000);mutations.append(raw) # virtual-only name
        raw=bytearray(importing_pe(['runtime.dll']));descriptor=bytes(raw[0x400:0x414])
        for n in range(65):raw[0x400+n*20:0x414+n*20]=descriptor
        struct.pack_into('<I',raw,212,66*20);mutations.append(raw)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owned.dll';path.write_bytes(valid)
            self.assertEqual(['runtime.dll','delayed.dll'],build.pe_import_names(path))
            for index,raw in enumerate(mutations):
                path.write_bytes(raw)
                with self.subTest(index=index),self.assertRaisesRegex(ValueError,f'owned.dll.*file_bytes={len(raw)}'):
                    build.pe_import_names(path)

    def test_pe_reads_remain_bounded_and_do_not_read_unrelated_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owned.exe';path.write_bytes(importing_pe(['runtime.dll'],padding=2*1024*1024))
            actual=build._regular_stream;reads=[]
            class Tracked:
                def __enter__(self):self.stream=actual(path);return self
                def __exit__(self,*args):self.stream.close()
                def fileno(self):return self.stream.fileno()
                def seek(self,offset):return self.stream.seek(offset)
                def read(self,count):
                    reads.append((self.stream.tell(),count));return self.stream.read(count)
            with patch.object(build,'_regular_stream',return_value=Tracked()):
                self.assertEqual(['runtime.dll'],build.pe_import_names(path))
            self.assertLess(sum(count for _,count in reads),65536)
            self.assertTrue(all(offset+count<=0x2400 for offset,count in reads))

    def test_import_reader_rejects_redirected_or_changed_owned_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owned.exe';path.write_bytes(importing_pe(['runtime.dll']))
            actual_lstat=Path.lstat
            def redirected(candidate):
                info=actual_lstat(candidate)
                return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400) if candidate==path else info
            with patch.object(Path,'lstat',autospec=True,side_effect=redirected):
                with self.assertRaisesRegex(ValueError,'reparse'):build.pe_import_names(path)
            actual_fstat=build.os.fstat;calls=[]
            def changed(fd):
                calls.append(fd)
                if len(calls)==3:
                    with path.open('ab') as output:output.write(b'changed during parse')
                return actual_fstat(fd)
            with patch.object(build.os,'fstat',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed during import reads'):build.pe_import_names(path)

    def test_failed_import_parse_retains_exact_file_size_and_blocks_tool_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record=root/'result.json';tool=root/'build/gdb/.libs/gdb.exe'
            tool.parent.mkdir(parents=True);tool.write_bytes(native_pe())
            native=root/'source/gdb-17.2/gdb/windows-nat.c';native.parent.mkdir(parents=True);native.write_bytes(b'fixture')
            inputs={'compiler':{'sha256':'a'*64}}
            (root/'request.json').write_text(json.dumps({'schema_version':1,'built':False,'diagnostic_only':True,
                'consumer_acceptance':False,'inputs':inputs,'tool':None}))
            real_record=build.file_record
            def file_record(path):return {'sha256':build.PATCHED_SHA256} if Path(path)==native else real_record(path)
            with patch.object(build,'BUILD',root),patch.object(build,'RECORD',record),\
                    patch.object(build,'build_inputs',return_value=inputs),patch.object(build,'file_record',side_effect=file_record):
                with self.assertRaisesRegex(ValueError,'gdb.exe.*file_bytes=256'):build.finish(0)
            value=json.loads(record.read_text());self.assertIs(value['built'],False);self.assertIsNone(value['tool'])
            self.assertIn(str(tool),value['error']);self.assertIn('file_bytes=256',value['error'])
            self.assertIs(value['consumer_acceptance'],False)

    def test_owned_pe_imports_ignore_large_unrelated_private_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'mingw64/bin';prefix.mkdir(parents=True)
            tool=root/'gdb.exe';tool.write_bytes(importing_pe(['runtime.dll','KERNEL32.dll'],['delayed.dll'],padding=2*1024*1024))
            runtime=prefix/'runtime.dll';runtime.write_bytes(importing_pe(['child.dll']))
            child=prefix/'child.dll';child.write_bytes(importing_pe(['runtime.dll']))
            delayed=prefix/'delayed.dll';delayed.write_bytes(importing_pe())
            system=root/'Windows/System32';system.mkdir(parents=True);(system/'KERNEL32.dll').write_bytes(b'OS fixture')
            # objdump -p prints unrelated private tables too. Base implementation
            # rejects the total text size even though the import graph is small.
            with patch.object(build.sys,'executable',str(prefix/'python.exe')),patch.dict(os.environ,{'SystemRoot':str(system.parent)}),\
                    patch.object(build.subprocess,'check_output',return_value=b'unrelated unwind row\n'*60000) as objdump:
                self.assertEqual({str(p.resolve()):build.file_record(p) for p in (runtime,child,delayed)},build.runtime_files(tool))
                objdump.assert_not_called()

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
            tool=root/'build/gdb/.libs/gdb.exe';tool.parent.mkdir(parents=True)
            tool.write_bytes(importing_pe(['runtime.dll','KERNEL32.dll']))
            runtime=prefix/'runtime.dll';runtime.write_bytes(importing_pe(['child.dll']))
            child=prefix/'child.dll';child.write_bytes(importing_pe(['KERNEL32.dll']))
            system=root/'Windows/System32';system.mkdir(parents=True);(system/'KERNEL32.dll').write_bytes(b'OS fixture')
            with patch.object(build.sys,'executable',str(prefix/'python.exe')),patch.dict(os.environ,{'SystemRoot':str(system.parent)}),\
                    patch.object(build,'pe_import_names',wraps=build.pe_import_names) as reader:
                self.assertEqual({str(p.resolve()):build.file_record(p) for p in (runtime,child)},build.runtime_files(tool))
                self.assertEqual(tool,reader.call_args_list[0].args[0])
                self.assertEqual({tool,runtime,child},{row.args[0] for row in reader.call_args_list})
                child.write_bytes(importing_pe(['foreign.dll']))
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
