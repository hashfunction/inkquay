"""Live Windows gate: exact GDB must preserve fault delivery and attached-target survival."""
# Copyright 2026 Trieflow LLC. MIT.
import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading

import gdb_observer as observer


def own_target(process, executable):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    times = [wintypes.FILETIME() for _ in range(4)]
    observer.require(kernel.GetProcessTimes(int(process._handle), *(ctypes.byref(t) for t in times)), 'Fixture creation query failed')
    return {'process_id':process.pid, 'executable':str(executable), 'executable_sha256':observer.sha(executable),
        'start_filetime':(times[0].dwHighDateTime << 32) | times[0].dwLowDateTime, 'package_full_name':None}


def run_case(gdb, executable, case):
    child = subprocess.Popen([str(executable), 'fault' if case == 'signal-pass' else 'normal'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000)
    target = None;session = None
    result = {'faults':[], 'diagnostic_errors':[], 'debugger_fallback_termination':False}
    identity = None;failure = None;survived = False;transcript = ''
    try:
        ready = queue.Queue()
        threading.Thread(target=lambda:ready.put(child.stdout.readline(256)),daemon=True).start()
        observer.require(ready.get(timeout=10).rstrip(b'\r\n') == b'fixture ready', 'Native fixture did not become ready')
        identity = own_target(child, executable)
        # A real process is opened but rejected before GDB when creation/path
        # identity differs. No unrelated process is ever selected for attachment.
        for key, value in [('start_filetime',identity['start_filetime']+1),('executable',str(executable)+'.other')]:
            try: observer.WindowsTarget(dict(identity, **{key:value}))
            except ValueError: pass
            else: raise AssertionError('Native target mismatch accepted')
        target = observer.WindowsTarget(identity);session = observer.Observer(gdb,target,result)
        session.attach()
        if case == 'signal-pass':
            child.stdin.write(b'go\n');child.stdin.flush()
            session.observe(lambda:False,timeout=20)
            observer.require(child.wait(timeout=5) == 1, 'Debugger swallowed or changed native SIGSEGV handler exit')
            observer.require(result['faults'] and result['faults'][0]['signal'] == 'SIGSEGV'
                and 'observer_fault_leaf' in (result['faults'][0]['stack'] or ''), 'Actual symbolized fault stack missing')
        else:
            if case == 'abrupt-debugger-exit':
                session.mi.process.kill();session.mi.process.wait(timeout=5)
            if case == 'timeout-detach':
                try: session.observe(lambda:False,timeout=0.1)
                except TimeoutError: pass
                else: raise AssertionError('Observer deadline was not enforced')
            session.close();transcript='\n'.join(session.mi.transcript)[-32768:];session = None
            observer.require(target.live() and child.poll() is None, 'Debugger shutdown killed the retained native target')
            survived = True
            child.stdin.write(b'go\n');child.stdin.flush()
            observer.require(child.wait(timeout=5) == 0, 'Target did not survive debugger detach/fallback to normal exit')
        observer.require(not result['diagnostic_errors'], 'Native debugger detach/observation failed')
    except Exception as error: failure = str(error)[:1024]
    finally:
        if session:
            try: session.close()
            except Exception as error: failure = 'Fixture cleanup: '+str(error)[:512]
            if session.mi: transcript='\n'.join(session.mi.transcript)[-32768:]
        if target: target.close()
        if child.poll() is None: child.kill()
        child.wait(timeout=5)
        for stream in (child.stdin,child.stdout,child.stderr): stream.close()
    return {'case':case, 'passed':not failure and not result['diagnostic_errors'], 'target':identity,
        'observer':result, 'target_exit_code':child.returncode, 'survival_verified':survived,
        'error':failure, 'transcript_tail':transcript}


def main(output):
    observer.require(sys.platform == 'win32' and os.environ.get('CI') == 'true', 'Live fixture requires Windows CI')
    gdb = Path(sys.executable).parent/'gdb.exe'
    gcc = gdb.parent/'gcc.exe'
    source = Path(__file__).resolve().parents[2]
    packages = (source/'build-evidence/msys2-installed-packages.txt').read_text()
    rows = re.findall(r'^mingw-w64-x86_64-gdb ([^\r\n]+)$',packages,re.M)
    observer.require(len(rows) == 1 and gdb.parent.parent.name.lower() == 'mingw64', 'Native GDB is not in recorded MINGW64 inputs')
    initial = observer.fingerprint(gdb)
    result = {'schema_version':1, 'diagnostic_observer_fixture':True, 'passed':False, 'cases':[], 'results':[],
        'fingerprint':initial, 'gdb_package_version':rows[0], 'gcc_sha256':observer.sha(gcc),
        'package_list_sha256':observer.sha(source/'build-evidence/msys2-installed-packages.txt'),
        'source_commit':os.environ.get('GITHUB_SHA'), 'workflow_run_id':os.environ.get('GITHUB_RUN_ID'),
        'workflow_run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'), 'error':None, 'at_utc':observer.utc()}
    try:
        with tempfile.TemporaryDirectory(prefix='ink-observer-fixture-') as directory:
            executable = Path(directory)/'observer-fixture.exe'
            subprocess.run([str(gcc),'-g','-O0',str(Path(__file__).with_name('observer_fixture.c')),'-o',str(executable)],
                check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for case in observer.CASES:
                row = run_case(gdb,executable,case)
                result['results'].append(row);result['cases'].append(case)
                observer.require(row['passed'], 'Live case failed: '+case)
        observer.require(observer.fingerprint(gdb) == initial, 'Debugger/helpers changed during live fixture')
        result['passed'] = True
    except Exception as error: result['error'] = str(error)[:1024]
    observer.write_json(output,result)
    return result['passed']


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if not main(args.output): raise RuntimeError('Live observer fixture failed; production attachment forbidden')
    except Exception as error:
        print(str(error)[:1024],file=sys.stderr);sys.exit(1)
