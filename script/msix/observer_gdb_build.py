"""Build-record boundary for a private diagnostic-only GDB, never an app input."""
# Copyright 2026 Trieflow LLC. MIT. The separately retained GDB patch is GPL-3.0-or-later.
import argparse
from datetime import datetime,timezone
import difflib
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile

from msix_qualification import _regular_stream,_reject_link

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'build-observer-gdb'
TOOL=BUILD/'build/gdb/gdb.exe'
RECORD=ROOT/'build-evidence/crash-observer-tool.json'
GNU_SOURCE={'url':'https://ftp.gnu.org/gnu/gdb/gdb-17.2.tar.xz','version':'17.2','bytes':24658624,
    'sha256':'1c036c0d72e4b3d1fb5c94c88632add6f9d76f4d7c4d2ea793c12a9f19a3228c','license':'GPL-3.0-or-later'}
WINDOWS_NAT_SHA256='2723115d9398b71a617348aeb2bc59bd1840a711876d398fc7601cd81d056829'
PATCHED_SHA256='3157427dad93eacd91a5196075d6c76bda81227c2bd79e8c77f0d9f8939c7487'
ATTACH_OLD='      if (!ok)\n\terr = (unsigned) GetLastError ();\n\n      return ok;'
ATTACH_NEW='''      if (!ok)
\terr = (unsigned) GetLastError ();
      else if (!DebugSetProcessKillOnExit (FALSE))
\t{
\t  /* This must run on the same worker that attached above.  */
\t  err = (unsigned) GetLastError ();
\t  DebugActiveProcessStop (pid);
\t  ok = FALSE;
\t}

      return ok;'''
OUTSIDE_OLD='  DebugSetProcessKillOnExit (FALSE);\n\n  target_announce_attach (from_tty, pid);'
OUTSIDE_NEW='  target_announce_attach (from_tty, pid);'


def require(value,message):
    if not value:raise ValueError(message)


def file_record(path):
    with _regular_stream(Path(path)) as stream:
        result=hashlib.sha256();size=0
        for chunk in iter(lambda:stream.read(1048576),b''):result.update(chunk);size+=len(chunk)
    return {'bytes':size,'sha256':result.hexdigest()}


def read_json(path):
    with _regular_stream(Path(path)) as stream:raw=stream.read(1048577)
    require(len(raw)<=1048576,'Diagnostic tool record exceeds bound')
    return json.loads(raw)


def write_json(path,value):
    raw=(json.dumps(value,indent=2)+'\n').encode();require(len(raw)<=1048576,'Diagnostic tool record exceeds bound')
    with Path(path).open('xb') as stream:stream.write(raw)


def patch_worker(text):
    require(text.count(ATTACH_OLD)==1 and text.count(OUTSIDE_OLD)==1,'Exact single-use GDB attach patch boundary differs')
    return text.replace(ATTACH_OLD,ATTACH_NEW).replace(OUTSIDE_OLD,OUTSIDE_NEW)


def build_inputs():
    prefix=Path(sys.executable).parent
    require(prefix.parent.name.lower()=='mingw64','Diagnostic build requires recorded native MINGW64 inputs')
    paths=[prefix/name for name in ('gcc.exe','g++.exe','ld.exe','objdump.exe')]
    paths += [prefix.parent.parent/'usr/bin'/name for name in ('bash.exe','make.exe')]
    paths += [ROOT/'build-evidence'/name for name in ('msys2-installed-packages.txt','msys2-cache-sha256.txt')]
    paths += [Path(__file__).with_name(name) for name in ('observer_gdb_build.py','build-observer-gdb.sh','gdb-17.2-worker-kill-on-exit.patch')]
    return {str(path.resolve()):file_record(path) for path in paths}


def extract_source(archive,destination):
    with tarfile.open(archive,'r:xz') as incoming:
        rows=incoming.getmembers();require(len(rows)<=16000 and sum(row.size for row in rows)<=250000000,'GNU source archive exceeds bound')
        names=set()
        for row in rows:
            name=PurePosixPath(row.name)
            require(row.name not in names and name.parts[0]=='gdb-17.2' and not name.is_absolute()
                and all(p not in ('','.','..') and ':' not in p and '\\' not in p for p in row.name.split('/'))
                and (row.isfile() or row.isdir()),'GNU source has unexpected path/type')
            names.add(row.name);target=destination/row.name
            if row.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with incoming.extractfile(row) as source,target.open('xb') as output:shutil.copyfileobj(source,output,1048576)
                target.chmod(row.mode & 0o777)
                # Preserve GNU's generated-file ordering so the release source
                # does not unnecessarily require bison/autoconf regeneration.
                os.utime(target,(row.mtime,row.mtime))


def prepare():
    require(sys.platform=='win32' and os.environ.get('CI')=='true' and os.environ.get('GITHUB_REPOSITORY')=='hashfunction/inkquay','Diagnostic build requires isolated InkQuay Windows CI')
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==os.environ['GITHUB_SHA'],'Diagnostic build source differs')
    _reject_link(ROOT);BUILD.mkdir();(BUILD/'build').mkdir();(BUILD/'source').mkdir()
    initial={'schema_version':1,'built':False,'diagnostic_only':True,'consumer_acceptance':False,
        'source_commit':os.environ['GITHUB_SHA'],'workflow_run_id':os.environ['GITHUB_RUN_ID'],'workflow_run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
        'gnu_source':GNU_SOURCE,'inputs':build_inputs(),'tool':None,'error':None,'started_at_utc':datetime.now(timezone.utc).isoformat()}
    write_json(BUILD/'request.json',initial)
    archive=BUILD/'gdb-17.2.tar.xz'
    subprocess.run(['curl','--fail','--silent','--show-error','--proto','=https','--max-time','120','--max-filesize','25000000',GNU_SOURCE['url'],'--output',str(archive)],check=True,timeout=125)
    require(file_record(archive)=={k:GNU_SOURCE[k] for k in ('bytes','sha256')},'Pinned GNU source bytes differ')
    extract_source(archive,BUILD/'source')
    native=BUILD/'source/gdb-17.2/gdb/windows-nat.c'
    require(file_record(native)['sha256']==WINDOWS_NAT_SHA256,'Pinned GNU attach source differs')
    before=native.read_text();after=patch_worker(before)
    actual_patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/gdb/windows-nat.c',tofile='b/gdb/windows-nat.c'))
    require(actual_patch==Path(__file__).with_name('gdb-17.2-worker-kill-on-exit.patch').read_text(),'Reviewed diagnostic patch differs')
    with native.open('w',newline='\n') as stream:stream.write(after)
    require(file_record(native)['sha256']==PATCHED_SHA256,'Patched GNU source differs')


def runtime_files():
    prefix=Path(sys.executable).parent;pending=[TOOL];found={};seen=set()
    while pending:
        item=pending.pop();name=item.name.lower()
        if name in seen:continue
        seen.add(name);require(len(seen)<=64,'Diagnostic runtime closure exceeds bound')
        imports=subprocess.check_output([str(prefix/'objdump.exe'),'-p',str(item)],timeout=15)
        require(len(imports)<=1048576,'Diagnostic PE imports exceed bound')
        for raw in re.findall(rb'DLL Name:\s*([^\r\n]+)',imports):
            dll=raw.decode('ascii').strip();require(re.fullmatch(r'[A-Za-z0-9_.+-]+\.dll',dll,re.I),'Diagnostic DLL name differs')
            path=prefix/dll
            if path.is_file():
                found[str(path.resolve())]=file_record(path);pending.append(path)
            else:require(dll.lower().startswith(('api-ms-win-','ext-ms-win-')) or (Path(os.environ['SystemRoot'])/'System32'/dll).is_file(),'Unresolved diagnostic DLL: '+dll)
    return found


def validate_record(value,inputs,tool,commit,run,attempt):
    require(type(value.get('schema_version')) is int and value['schema_version']==1 and value.get('built') is True
        and value.get('diagnostic_only') is True and value.get('consumer_acceptance') is False and value.get('error') is None
        and value.get('source_commit')==commit and value.get('workflow_run_id')==run and value.get('workflow_run_attempt')==attempt
        and value.get('gnu_source')==GNU_SOURCE and value.get('source_before_sha256')==WINDOWS_NAT_SHA256
        and value.get('source_after_sha256')==PATCHED_SHA256 and value.get('inputs')==inputs and value.get('tool')==tool,
        'Diagnostic GDB build/source/patch/dependency/tool receipt differs')


def finish(exit_code):
    value=read_json(BUILD/'request.json') if (BUILD/'request.json').is_file() else {'schema_version':1,'diagnostic_only':True,'consumer_acceptance':False}
    try:
        require(exit_code==0,'Diagnostic configure/build failed with exit '+str(exit_code))
        require(build_inputs()==value['inputs'],'Recorded diagnostic build inputs changed')
        require(file_record(BUILD/'source/gdb-17.2/gdb/windows-nat.c')['sha256']==PATCHED_SHA256,'Built attach source changed')
        value.update(tool=file_record(TOOL),runtime_files=runtime_files(),source_before_sha256=WINDOWS_NAT_SHA256,source_after_sha256=PATCHED_SHA256,
            license_file=file_record(BUILD/'source/gdb-17.2/COPYING3'),built=True,error=None)
    except Exception as error:value.update(built=False,error=str(error)[:2048])
    value['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    for label in ('configure','make'):
        log=BUILD/(label+'.log')
        if log.is_file():
            value[label+'_log']=file_record(log)
            with log.open('rb') as stream:stream.seek(max(0,log.stat().st_size-32768));value[label+'_log_tail']=stream.read(32768).decode('utf-8',errors='replace')
    write_json(RECORD,value)
    require(value['built'],'Diagnostic GDB unavailable: '+value['error'])


def verified_debugger():
    value=read_json(RECORD)
    validate_record(value,build_inputs(),file_record(TOOL),os.environ.get('GITHUB_SHA'),os.environ.get('GITHUB_RUN_ID'),os.environ.get('GITHUB_RUN_ATTEMPT'))
    require(value.get('runtime_files') and len(value['runtime_files'])<=64,'Diagnostic runtime binding is absent')
    prefix=Path(sys.executable).parent.resolve()
    for name,expected in value['runtime_files'].items():
        path=Path(name);require(path.parent.resolve()==prefix and path.suffix.lower()=='.dll' and file_record(path)==expected,'Diagnostic runtime bytes differ')
    return TOOL.resolve()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','finish'));parser.add_argument('--exit-code',type=int,default=0)
    args=parser.parse_args()
    if args.mode=='prepare':prepare()
    else:finish(args.exit_code)
