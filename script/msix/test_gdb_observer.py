"""Production observer protocol/identity/bounds regressions; Windows attachment has a separate live gate."""
import json
import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import gdb_observer as observer


class ObserverTests(unittest.TestCase):
    def test_exact_inferior_identity_excludes_unrelated_or_multiple_targets(self):
        expected = {'process_id':42, 'executable':r'C:\owned\Scriblark.exe'}
        valid = '7^done,groups=[{id="i1",type="process",pid="42",executable="C:\\\\owned\\\\Scriblark.exe"}]'
        observer.check_inferior(valid, expected)
        for value in [valid.replace('pid="42"','pid="43"'), valid.replace('owned','other'),
                valid.replace('}]','},{id="i2",pid="99"}]')]:
            with self.subTest(value=value), self.assertRaises(ValueError): observer.check_inferior(value, expected)

    def test_only_fault_events_trigger_stack_capture(self):
        for signal in ('SIGSEGV','SIGILL','SIGFPE','SIGABRT'):
            self.assertEqual(signal, observer.fault_signal(f'*stopped,reason="signal-received",signal-name="{signal}",thread-id="1"'))
        for value in ('*running,thread-id="all"', '*stopped,reason="breakpoint-hit"',
                '*stopped,reason="signal-received",signal-name="SIGTRAP"', '~"SIGSEGV"'):
            self.assertIsNone(observer.fault_signal(value))

    def test_real_pipe_protocol_correlates_tokens_and_bounds_output(self):
        program = 'import sys,json\nfor line in sys.stdin:\n t=line.split("-",1)[0];print("*running,thread-id=\\"all\\"",flush=True);print(t+"^done",flush=True)'
        with observer.MiProcess([sys.executable,'-u','-c',program]) as mi:
            self.assertRegex(mi.command('-test', 2), r'^1\^done$')
        noisy = 'import sys;print("x"*70000,flush=True);sys.stdin.read()'
        with observer.MiProcess([sys.executable,'-u','-c',noisy]) as mi:
            with self.assertRaisesRegex(ValueError, 'bound'): mi.read(2)

    def test_protocol_failure_and_timeout_are_not_ready(self):
        bad = 'import sys\nfor line in sys.stdin: print(line.split("-",1)[0]+\'^error,msg="denied"\',flush=True)'
        with observer.MiProcess([sys.executable,'-u','-c',bad]) as mi:
            with self.assertRaisesRegex(ValueError,'GDB command'): mi.command('-target-attach 42',2)
        with observer.MiProcess([sys.executable,'-c','import time;time.sleep(30)']) as mi:
            with self.assertRaises(TimeoutError): mi.command('-target-attach 42',0.1)

    def test_dwarf_sections_are_required_from_actual_pe_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owned.exe'
            data=bytearray(256);data[:2]=b'MZ';struct.pack_into('<I',data,60,64)
            data[64:68]=b'PE\0\0';struct.pack_into('<H',data,70,2)
            struct.pack_into('<II',data,76,200,0)
            data[88:96]=b'/4\0\0\0\0\0\0';data[128:136]=b'/16\0\0\0\0\0'
            strings=b'.debug_info\0.debug_line\0';struct.pack_into('<I',data,200,len(strings)+4)
            data[204:204+len(strings)]=strings;path.write_bytes(data)
            self.assertEqual(['.debug_info','.debug_line'],observer.dwarf_sections(path))
            data[204:215]=b'no_symbols\0';path.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'DWARF'): observer.dwarf_sections(path)

    def test_debugger_permissions_and_fault_delivery_are_fixed(self):
        commands='\n'.join(observer.SETUP)
        for required in ('auto-load off','debuginfod enabled off','may-write-memory off',
                'may-write-registers off','may-insert-breakpoints off','may-call-functions off',
                'handle SIGSEGV SIGILL SIGFPE SIGABRT stop print pass'):
            self.assertIn(required,commands)
        self.assertNotIn('nopass',commands)
        self.assertNotIn('-exec-run',commands)

    def test_partial_stale_or_failed_live_fixture_cannot_authorize_attachment(self):
        fingerprint={'gdb':'recorded-gdb','gdb_sha256':'1'*64,'helpers':{}}
        value={'schema_version':1,'diagnostic_observer_fixture':True,'error':None,
            'passed':True,'cases':observer.CASES,'fingerprint':fingerprint,'source_commit':'2'*40,
            'workflow_run_id':'123','workflow_run_attempt':'1','results':[]}
        for case in observer.CASES:
            row={'case':case,'passed':True,'target_exit_code':1 if case=='signal-pass' else 0,'survival_verified':True,
                'observer':{'diagnostic_errors':[],'resumed_at_utc':'fixture-time','debugger_process_id':42,
                    'debugger_exit_code':1 if case=='abrupt-debugger-exit' else 0,'detached_at_utc':'fixture-time',
                    'faults':[{'signal':'SIGSEGV','stack':'observer_fault_leaf','error':None}]}}
            value['results'].append(row)
        check=lambda item:observer.validate_preflight(item,fingerprint,'2'*40,'123','1')
        check(value)
        for field, changed in [('passed',False),('passed',1),('results',[]),('workflow_run_id','122'),
                ('workflow_run_attempt','2'),('fingerprint',{}),('source_commit','3'*40)]:
            with self.subTest(field=field), self.assertRaises(ValueError): check(dict(value,**{field:changed}))
        for index,key,changed in [(0,'target_exit_code',0),(1,'survival_verified',False),(2,'passed',False)]:
            item=copy.deepcopy(value);item['results'][index][key]=changed
            with self.subTest(index=index,key=key),self.assertRaises(ValueError):check(item)
        item=copy.deepcopy(value);item['results'][0]['observer']['faults'][0]['stack']='no symbols'
        with self.assertRaises(ValueError):check(item)

    def test_request_hash_is_checked_on_the_exact_bytes_being_parsed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'request.json';path.write_text('{"nonce":"one"}')
            expected=observer.sha(path)
            self.assertEqual({'nonce':'one'},observer.read_json(path,expected))
            path.write_text('{"nonce":"two"}')
            with self.assertRaisesRegex(ValueError,'request bytes'):observer.read_json(path,expected)


if __name__ == '__main__': unittest.main()
