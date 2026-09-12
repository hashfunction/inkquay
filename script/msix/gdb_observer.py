"""Opt-in, bounded GDB observer for an already owned installed InkQuay process.

This is diagnostic evidence only. It never starts the consumer, writes its memory,
swallows its fault, or confers consumer acceptance. Live Windows fixture evidence
must pass for this exact debugger/helper before the CLI can attach to InkQuay.
"""
# Copyright 2026 Trieflow LLC. MIT.
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path
import queue
import re
import struct
import subprocess
import sys
import threading
import time

from msix_qualification import _regular_stream, _reject_link
from observer_gdb_build import verified_debugger,RECORD as TOOL_RECORD

PACKAGE = 'Trieflow.InkQuay.Qualification_1.0.0.0_x64__fjvr7t994vwc4'
MAX_BYTES = 1024 * 1024
MAX_LINE = 65536
FAULTS = ('SIGSEGV', 'SIGILL', 'SIGFPE', 'SIGABRT')
CASES = ['signal-pass', 'normal-detach', 'abrupt-debugger-exit', 'timeout-detach']
HELPERS = ['gdb_observer.py', 'test_gdb_observer_windows.py', 'observer_fixture.c',
    'observer_gdb_build.py', 'build-observer-gdb.sh', 'gdb-17.2-worker-kill-on-exit.patch']
SETUP = ['-gdb-set pagination off', '-gdb-set confirm off', '-gdb-set mi-async on',
    '-gdb-set auto-load off', '-gdb-set debuginfod enabled off',
    '-gdb-set may-call-functions off', '-gdb-set may-write-memory off', '-gdb-set may-write-registers off',
    '-gdb-set may-insert-breakpoints off', '-gdb-set may-insert-tracepoints off',
    '-gdb-set may-insert-fast-tracepoints off', '-gdb-set print frame-arguments none',
    '-gdb-set print entry-values no', '-gdb-set print elements 32', '-gdb-set print thread-events off',
    '-interpreter-exec console "handle SIGSEGV SIGILL SIGFPE SIGABRT stop print pass"']


def require(value, message):
    if not value: raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def process_filetime(handle):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    times = [wintypes.FILETIME() for _ in range(4)]
    require(kernel.GetProcessTimes(int(handle), *(ctypes.byref(t) for t in times)), 'Retained process creation query failed')
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def sha(path):
    with _regular_stream(Path(path)) as stream:
        value = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): value.update(chunk)
    return value.hexdigest()


def read_json(path, expected_sha256=None):
    with _regular_stream(Path(path)) as stream: raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, 'Observer JSON exceeds bound')
    if expected_sha256 is not None:
        require(hashlib.sha256(raw).hexdigest() == expected_sha256, 'Observer request bytes differ')
    return json.loads(raw.decode('utf-8-sig'))


def write_json(path, value):
    data = (json.dumps(value, indent=2) + '\n').encode()
    require(len(data) <= MAX_BYTES, 'Observer result exceeds bound')
    with Path(path).open('xb') as stream: stream.write(data)


def dwarf_sections(path):
    """Read only bounded PE headers and section names, including COFF long names."""
    with _regular_stream(Path(path)) as stream:
        def at(offset, size):
            require(0 <= offset and size <= 65536, 'PE header bound')
            stream.seek(offset); value = stream.read(size)
            require(len(value) == size, 'Truncated PE header')
            return value
        dos = at(0, 64); require(dos[:2] == b'MZ', 'Expected Windows PE executable')
        pe = struct.unpack_from('<I', dos, 60)[0];require(pe <= 1024 * 1024, 'PE offset bound')
        header = at(pe, 24);require(header[:4] == b'PE\0\0', 'Expected PE signature')
        count = struct.unpack_from('<H', header, 6)[0]
        symbols, number = struct.unpack_from('<II', header, 12)
        optional = struct.unpack_from('<H', header, 20)[0]
        require(0 < count <= 128 and optional <= 4096, 'PE section count/optional header bound')
        strings = symbols + 18 * number
        names = []
        for i in range(count):
            name = at(pe + 24 + optional + 40*i, 8).split(b'\0')[0]
            if name.startswith(b'/'):
                require(re.fullmatch(b'/[0-9]+', name), 'Invalid COFF section name')
                offset = int(name[1:]);length = struct.unpack('<I', at(strings, 4))[0]
                require(4 <= offset < length, 'COFF string offset bound')
                name = at(strings+offset, min(128, length-offset)).split(b'\0')[0]
            names.append(name.decode('ascii'))
    required = ['.debug_info', '.debug_line']
    require(all(name in names for name in required), 'Exact executable lacks required DWARF sections')
    return required


def check_inferior(line, expected):
    pids = re.findall(r'\bpid="([0-9]+)"', line)
    executables = re.findall(r'\bexecutable=("(?:[^"\\]|\\.)*")', line)
    require(pids == [str(expected['process_id'])] and len(executables) == 1,
        'GDB did not attach to exactly one expected inferior')
    require(ntpath.normcase(ntpath.normpath(json.loads(executables[0]))) ==
        ntpath.normcase(ntpath.normpath(expected['executable'])), 'GDB inferior executable differs')


def fault_signal(line):
    if not line.startswith('*stopped,reason="signal-received",'): return None
    match = re.search(r'\bsignal-name="([A-Z0-9]+)"', line)
    return match[1] if match and match[1] in FAULTS else None


class MiProcess:
    """Bounded asynchronous pipe transport; only this retained child is stopped."""
    def __init__(self, arguments, environment=None):
        self.process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=environment, creationflags=0x08000000 if sys.platform == 'win32' else 0)
        self.lines = queue.Queue(maxsize=128);self.transcript = [];self.token = 0
        self.events = [];self.overflow = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        total = 0
        try:
            while True:
                line = self.process.stdout.readline(MAX_LINE+1)
                if not line: break
                total += len(line)
                if len(line) > MAX_LINE or total > MAX_BYTES:
                    if not self.overflow:
                        self.overflow = True;self.lines.put(ValueError('GDB output exceeds diagnostic bound'))
                    continue  # Drain without retaining unbounded output during cleanup.
                if not self.overflow: self.lines.put(line.decode('utf-8', errors='replace').rstrip('\r\n'))
        finally: self.lines.put(EOFError('GDB pipe closed'))

    def read(self, timeout):
        try: value = self.lines.get(timeout=max(0, timeout))
        except queue.Empty: raise TimeoutError('GDB response deadline exceeded') from None
        if isinstance(value, Exception): raise value
        self.transcript.append(value)
        return value

    def command(self, command, timeout=5):
        if timeout <= 0: raise TimeoutError('GDB command deadline exceeded')
        self.token += 1;token = str(self.token)
        self.process.stdin.write((token+command+'\n').encode());self.process.stdin.flush()
        deadline = time.monotonic()+timeout
        while True:
            line = self.read(deadline-time.monotonic())
            if line.startswith('*stopped,'): self.events.append(line)
            if line.startswith(token+'^'):
                require(line.startswith((token+'^done', token+'^running', token+'^exit')), 'GDB command failed: '+line[:512])
                return line

    def __enter__(self): return self

    def __exit__(self, *_):
        try: self.process.wait(timeout=1)
        except subprocess.TimeoutExpired: self.process.kill()
        self.process.wait(timeout=5)
        self.process.stdin.close();self.process.stdout.close()


class WindowsTarget:
    """Open once, verify against the parent's retained identity, retain until detach."""
    def __init__(self, expected):
        require(sys.platform == 'win32', 'Native process identity requires Windows')
        self.expected = expected
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        k = self.kernel
        for name, args, result in [
            ('OpenProcess', [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD],wintypes.HANDLE),
            ('CloseHandle',[wintypes.HANDLE],wintypes.BOOL),
            ('WaitForSingleObject',[wintypes.HANDLE,wintypes.DWORD],wintypes.DWORD),
            ('GetProcessTimes',[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4,wintypes.BOOL),
            ('QueryFullProcessImageNameW',[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)],wintypes.BOOL),
            ('GetPackageFullName',[wintypes.HANDLE,ctypes.POINTER(wintypes.UINT),wintypes.LPWSTR],wintypes.LONG)]:
            method = getattr(k, name);method.argtypes = args;method.restype = result
        self.handle = k.OpenProcess(0x100000 | 0x1000, False, expected['process_id'])
        require(self.handle, 'Cannot retain target process handle')
        try: self.verify()
        except Exception: self.close();raise

    def live(self):
        status = self.kernel.WaitForSingleObject(self.handle, 0)
        require(status in (0,258), 'Retained target exit observation failed')
        return status == 258

    def verify(self):
        require(self.live(), 'Retained target has exited before observer readiness')
        times = [wintypes.FILETIME() for _ in range(4)]
        require(self.kernel.GetProcessTimes(self.handle, *(ctypes.byref(t) for t in times)), 'Target creation query failed')
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        require(created == self.expected['start_filetime'], 'Target creation identity differs')
        path = ctypes.create_unicode_buffer(32768);size = wintypes.DWORD(len(path))
        require(self.kernel.QueryFullProcessImageNameW(self.handle, 0, path, ctypes.byref(size)), 'Target executable query failed')
        require(ntpath.normcase(ntpath.normpath(path.value)) == ntpath.normcase(ntpath.normpath(self.expected['executable'])), 'Target executable differs')
        size = wintypes.UINT(1024);package = ctypes.create_unicode_buffer(size.value)
        status = self.kernel.GetPackageFullName(self.handle, ctypes.byref(size), package)
        observed = None if status == 15700 else package.value
        require(status in (0,15700) and observed == self.expected['package_full_name'], 'Target package identity differs')
        require(sha(path.value) == self.expected['executable_sha256'], 'Target executable bytes differ')

    def close(self):
        if self.handle: self.kernel.CloseHandle(self.handle);self.handle = None


class Observer:
    def __init__(self, gdb, target, output):
        self.target = target;self.output = output;self.mi = None;self.attached = False

        # -iex happens before any file is loaded; --nx/--nh prohibit startup files.
        self.arguments = [str(gdb), '--nx', '--nh', '--quiet', '--interpreter=mi3',
            '-iex', 'set auto-load off', '-iex', 'set debuginfod enabled off']

    def attach(self):
        self.target.verify();self.output['dwarf_sections'] = dwarf_sections(self.target.expected['executable'])
        environment=dict(os.environ)
        # The private debugger's recorded native runtime DLLs remain in the
        # unchanged MINGW64 toolchain, outside the consumer package/runtime.
        environment['PATH']=str(Path(sys.executable).parent)+os.pathsep+environment.get('PATH','')
        self.mi = MiProcess(self.arguments,environment);self.output['debugger_process_id'] = self.mi.process.pid
        deadline = time.monotonic()+20
        for command in SETUP:
            self.mi.command(command, max(0, deadline-time.monotonic()))
        self.mi.command('-file-exec-and-symbols '+json.dumps(self.target.expected['executable']), max(0, deadline-time.monotonic()))
        self.mi.command('-target-attach '+str(self.target.expected['process_id']), max(0, deadline-time.monotonic()))
        self.attached = True;self.output['attached_at_utc'] = utc()
        check_inferior(self.mi.command('-list-thread-groups', max(0, deadline-time.monotonic())), self.target.expected)
        self.target.verify()
        require(not any(fault_signal(event) for event in self.mi.events), 'Target faulted during debugger attachment')
        self.mi.events.clear()  # Attachment's own SIGTRAP is not an app fault.
        self.mi.command('-exec-continue', max(0, deadline-time.monotonic()))
        self.output['resumed_at_utc'] = utc()

    def observe(self, stop, timeout=300):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            if stop(): return
            if self.mi.events: line = self.mi.events.pop(0)
            else:
                try: line = self.mi.read(min(0.1, deadline-time.monotonic()))
                except TimeoutError: continue
                except EOFError:
                    require(not self.target.live(), 'Debugger exited while target remained live')
                    return
            signal = fault_signal(line)
            if signal:
                require(len(self.output['faults']) < 4, 'Fault capture count exceeds bound')
                check_inferior(self.mi.command('-list-thread-groups'), self.target.expected)
                fault = {'at_utc':utc(), 'signal':signal, 'stop_record':line[:4096], 'stack':None, 'error':None}
                self.output['faults'].append(fault)
                try:
                    fault['stack'] = self.mi.command('-stack-list-frames 0 39')
                    self.mi.command('-interpreter-exec console "info registers rip rsp rbp"')
                except Exception as error: fault['error'] = str(error)[:512]
                finally:
                    # Keep GDB's original signal pending and pass it to the app.
                    self.mi.command('-exec-continue')
            if line.startswith('*stopped,reason="exited'): return
        raise TimeoutError('Observer observation deadline exceeded')

    def close(self):
        if not self.mi: return
        try:
            if self.mi.process.poll() is None:
                if self.attached and self.target.live():
                    self.mi.command('-target-detach', 5)
                    self.output['detached_at_utc'] = utc()
                self.mi.command('-gdb-exit', 5)
        except Exception as error: self.output['diagnostic_errors'].append('Detach: '+str(error)[:512])
        finally:
            try: self.mi.process.wait(timeout=1)
            except subprocess.TimeoutExpired: pass
            if self.mi.process.poll() is None:
                self.output['debugger_fallback_termination'] = True
            self.mi.__exit__()
            self.output['debugger_exit_code'] = self.mi.process.returncode


def fingerprint(gdb):
    require(Path(gdb).resolve()==verified_debugger(), 'Unverified diagnostic debugger selected')
    return {'gdb':str(Path(gdb).resolve()), 'gdb_sha256':sha(gdb),
        'diagnostic_build_record_sha256':sha(TOOL_RECORD),
        'helpers':{name:sha(Path(__file__).parent/name) for name in HELPERS}}


def validate_preflight(value, current, commit, run_id, attempt):
    require(type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('diagnostic_observer_fixture') is True and value.get('error') is None
        and value.get('passed') is True and value.get('cases') == CASES and value.get('fingerprint') == current
        and value.get('source_commit') == commit and value.get('workflow_run_id') == run_id
        and value.get('workflow_run_attempt') == attempt, 'Live Windows observer fixture differs from this debugger/source/run')
    rows = value.get('results')
    require(isinstance(rows,list) and len(rows) == len(CASES), 'Live observer fixture is incomplete')
    for case, row in zip(CASES,rows):
        require(row.get('case') == case and row.get('passed') is True, 'Live observer case did not pass')
        capture = row['observer']
        require(capture.get('diagnostic_errors') == [] and capture.get('resumed_at_utc')
            and type(capture.get('debugger_process_id')) is int and capture['debugger_process_id'] > 0
            and type(capture.get('debugger_exit_code')) is int, 'Live observer lifecycle is incomplete')
        require(type(row.get('target_exit_code')) is int, 'Live target exit is missing')
        if case == 'signal-pass':
            require(row['target_exit_code'] == 1 and capture['faults'] and capture['faults'][0]['signal'] == 'SIGSEGV'
                and capture['faults'][0].get('error') is None
                and 'observer_fault_leaf' in (capture['faults'][0].get('stack') or ''), 'Live signal propagation/stack was not proven')
        else:
            require(row['target_exit_code'] == 0 and row.get('survival_verified') is True, 'Debugger shutdown survival was not proven')
            if case == 'abrupt-debugger-exit':
                require(capture['debugger_exit_code'] != 0, 'Abrupt debugger exit was not exercised')
            else: require(capture.get('detached_at_utc'), 'Explicit native detach was not proven')


def main(request_path, request_hash):
    require(sys.platform == 'win32' and os.environ.get('CI') == 'true', 'Observer requires disposable Windows CI')
    request = read_json(request_path, request_hash)
    require(request['source_commit'] == os.environ.get('GITHUB_SHA') and re.fullmatch('[0-9a-f]{40}',request['source_commit']), 'Observer source differs')
    require(re.fullmatch('[0-9a-f]{32}', request['nonce']), 'Invalid observer nonce')
    require(request['target']['package_full_name'] == PACKAGE and type(request['target']['process_id']) is int
        and request['target']['process_id'] > 0 and type(request['target']['start_filetime']) is int, 'Invalid owned package target')
    executable = Path(request['target']['executable'])
    require(executable.is_absolute() and executable.name.lower() == 'inkquay.exe' and executable.parent.name.lower() == 'bin'
        and executable.parent.parent.name.lower() == PACKAGE.lower(), 'Observer target is outside the exact installed package')
    gdb = verified_debugger()
    preflight = read_json(request['preflight'])
    validate_preflight(preflight,fingerprint(gdb),request['source_commit'],os.environ.get('GITHUB_RUN_ID'),os.environ.get('GITHUB_RUN_ATTEMPT'))
    output = Path(request['output']);_reject_link(output)
    result = {'schema_version':1, 'diagnostic_observer':True, 'consumer_acceptance':False,
        'nonce':request['nonce'], 'source_commit':request['source_commit'], 'target':request['target'],
        'fingerprint':preflight['fingerprint'], 'activation_utc':request['activation_utc'],
        'attached_at_utc':None,'resumed_at_utc':None,'detached_at_utc':None,'faults':[], 'diagnostic_errors':[],
        'debugger_fallback_termination':False, 'debugger_process_id':None, 'debugger_exit_code':None}
    target = None;observer = None
    try:
        target = WindowsTarget(request['target']);observer = Observer(gdb,target,result)
        observer.attach()
        require(fingerprint(gdb) == preflight['fingerprint'], 'Debugger/helpers changed during attachment')
        write_json(output/'crash-observer-ready.json', {'nonce':request['nonce'], 'target':request['target'],
            'helper_process_id':os.getpid(), 'debugger_process_id':observer.mi.process.pid,
            'debugger_start_filetime':process_filetime(observer.mi.process._handle), 'resumed_at_utc':result['resumed_at_utc']})
        def stop():
            path = output/'crash-observer-stop.json'
            if not path.exists(): return False
            require(read_json(path) == {'nonce':request['nonce']}, 'Observer stop identity differs')
            return True
        observer.observe(stop)
    except Exception as error: result['diagnostic_errors'].append(str(error)[:1024])
    finally:
        if observer:
            try: observer.close()
            except Exception as error: result['diagnostic_errors'].append('Observer cleanup: '+str(error)[:512])
            if observer.mi:
                data = ('\n'.join(observer.mi.transcript)+'\n').encode('utf-8')[:MAX_BYTES]
                with (output/'crash-observer.txt').open('xb') as stream: stream.write(data)
        if target: target.close()
        try:
            require(fingerprint(gdb) == preflight['fingerprint'], 'Debugger/helpers changed during observation')
        except Exception as error: result['diagnostic_errors'].append(str(error)[:512])
        write_json(output/'crash-observer.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path,required=True);parser.add_argument('--request-sha256',required=True)
    arguments = parser.parse_args()
    try: main(arguments.request, arguments.request_sha256)
    except Exception as error:
        print('Observer unavailable: '+str(error)[:1024],file=sys.stderr);sys.exit(1)
