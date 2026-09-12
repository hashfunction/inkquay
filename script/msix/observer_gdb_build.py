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
import struct
import subprocess
import sys
import tarfile

from msix_qualification import _regular_stream,_reject_link

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'build-observer-gdb'
# MinGW Libtool emits build/gdb/gdb.exe as a launcher, not the debugger
# process we must retain. Only these two documented real output names exist.
TOOL_RELATIVE_PATHS=('build/gdb/.libs/gdb.exe','build/gdb/.libs/lt-gdb.exe')
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


def resolve_tool():
    candidates=[]
    for directory in (BUILD,BUILD/'build',BUILD/'build/gdb',BUILD/'build/gdb/.libs'):
        try:_reject_link(directory)
        except FileNotFoundError:pass
    for relative in TOOL_RELATIVE_PATHS:
        path=BUILD/relative
        try:_reject_link(path)
        except FileNotFoundError:continue
        candidates.append(path)
    require(len(candidates)==1,'Expected exactly one real Libtool diagnostic executable; launcher is never selected')
    tool=candidates[0]
    with _regular_stream(tool) as stream:
        dos=stream.read(64)
        require(len(dos)==64 and dos[:2]==b'MZ','Diagnostic executable lacks a native PE header')
        offset=struct.unpack_from('<I',dos,60)[0];require(64<=offset<=1048576,'Diagnostic PE offset exceeds bound')
        stream.seek(offset);header=stream.read(26)
        require(len(header)==26 and header[:4]==b'PE\0\0' and struct.unpack_from('<H',header,4)[0]==0x8664
            and struct.unpack_from('<H',header,24)[0]==0x20b and struct.unpack_from('<H',header,22)[0]&0x2002==2,
            'Diagnostic tool must be a native AMD64 PE executable')
    return tool


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


def pe_import_names(path):
    """Read only bounded AMD64 PE32+ import/delay descriptors, never full private tables.

    Microsoft PE format: optional-header directories 1 and 13, 20/32-byte
    descriptors, and NUL-terminated ASCII DLL names. All reads use file-backed
    RVAs from the same retained regular-file handle; section names are irrelevant.
    """
    size=None
    try:
        with _regular_stream(path) as stream:
            before=os.fstat(stream.fileno());size=before.st_size;read_bytes=0
            def read(offset,count):
                nonlocal read_bytes
                require(0<=offset<=size and 0<=count<=size-offset,
                    f'Truncated PE range offset={offset} bytes={count} file_bytes={size}')
                read_bytes+=count;require(read_bytes<=65536,'PE import reads exceed 65536 bytes')
                stream.seek(offset);raw=stream.read(count)
                require(len(raw)==count,'PE changed/truncated during read');return raw
            dos=read(0,64);require(dos[:2]==b'MZ','Missing DOS header')
            offset=struct.unpack_from('<I',dos,60)[0];require(64<=offset<=1048576,'PE header offset exceeds bound')
            coff=read(offset,24)
            require(coff[:4]==b'PE\0\0' and struct.unpack_from('<H',coff,4)[0]==0x8664
                and struct.unpack_from('<H',coff,22)[0]&2,'Expected native AMD64 PE image')
            count=struct.unpack_from('<H',coff,6)[0];optional_size=struct.unpack_from('<H',coff,20)[0]
            require(1<=count<=96 and 112<=optional_size<=4096,'PE section/optional-header bounds differ')
            optional=read(offset+24,optional_size)
            require(struct.unpack_from('<H',optional)[0]==0x20b,'Expected PE32+ optional header')
            headers_size=struct.unpack_from('<I',optional,60)[0]
            directories=struct.unpack_from('<I',optional,108)[0]
            require(directories<=16 and 112+8*directories<=optional_size,'PE directory count exceeds optional header')
            section_start=offset+24+optional_size
            require(section_start+40*count<=headers_size<=size,'PE headers exceed file bounds')
            sections=[]
            for index in range(count):
                section=read(section_start+40*index,40)
                virtual_size,rva,raw_size,raw_offset=struct.unpack_from('<IIII',section,8)
                extent=max(virtual_size,raw_size)
                require(rva+extent<=0x100000000 and (not raw_size or
                    headers_size<=raw_offset<=size and raw_size<=size-raw_offset),'PE section range exceeds file/RVA bounds')
                if extent:sections.append((rva,extent,raw_offset,raw_size))
            def location(rva,needed):
                require(0<rva<0x100000000 and rva+needed<=0x100000000,'Import RVA exceeds bounds')
                matches=[(raw+rva-start,raw_size-(rva-start)) for start,extent,raw,raw_size in sections
                    if start<=rva<start+extent]
                if rva<headers_size:matches.append((rva,headers_size-rva))
                require(len(matches)==1 and matches[0][1]>=needed,'Import RVA is ambiguous or not file-backed')
                return matches[0]
            names=[]
            for index,width,label in ((1,20,'import'),(13,32,'delay import')):
                if directories<=index:continue
                rva,table_size=struct.unpack_from('<II',optional,112+8*index)
                if rva==table_size==0:continue
                require(rva and width<=table_size<=1048576,
                    f'{label} directory size={table_size} exceeds descriptor bounds')
                location(rva,table_size)
                terminated=False
                for entry in range(min(table_size//width,65)):
                    at,_=location(rva+entry*width,width);descriptor=read(at,width)
                    if not any(descriptor):terminated=True;break
                    require(len(names)<64,'PE imports exceed 64 DLL descriptors')
                    if index==13:
                        require(struct.unpack_from('<I',descriptor)[0]==1,'Delay import must use RVAs with no reserved flags')
                        name_rva=struct.unpack_from('<I',descriptor,4)[0]
                    else:name_rva=struct.unpack_from('<I',descriptor,12)[0]
                    at,available=location(name_rva,1);raw=read(at,min(available,256))
                    end=raw.find(b'\0');require(0<end<256,'DLL name is empty/unterminated or exceeds 255 bytes')
                    name=raw[:end].decode('ascii')
                    require(re.fullmatch(r'[A-Za-z0-9_.+-]+\.dll',name,re.I),'Diagnostic DLL name differs')
                    names.append(name)
                require(terminated,f'{label} directory has no bounded null descriptor')
            after=os.fstat(stream.fileno())
            require((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
                (after.st_size,after.st_mtime_ns,after.st_ctime_ns),'PE file changed during import reads')
            return names
    except (ValueError,OSError) as error:
        raise ValueError(f'Diagnostic PE imports: {str(path)[:512]} (file_bytes={size}): {str(error)[:1024]}') from error


def runtime_files(tool):
    prefix=Path(sys.executable).parent;pending=[tool];found={};seen=set()
    while pending:
        item=pending.pop();name=item.name.lower()
        if name in seen:continue
        seen.add(name);require(len(seen)<=64,'Diagnostic runtime closure exceeds bound')
        for dll in pe_import_names(item):
            path=prefix/dll
            if path.is_file():
                found[str(path.resolve())]=file_record(path);pending.append(path)
            else:require(dll.lower().startswith(('api-ms-win-','ext-ms-win-')) or (Path(os.environ['SystemRoot'])/'System32'/dll).is_file(),'Unresolved diagnostic DLL: '+dll)
    return found


def validate_record(value,inputs,tool,commit,run,attempt,relative_tool):
    require(type(value.get('schema_version')) is int and value['schema_version']==1 and value.get('built') is True
        and value.get('diagnostic_only') is True and value.get('consumer_acceptance') is False and value.get('error') is None
        and value.get('source_commit')==commit and value.get('workflow_run_id')==run and value.get('workflow_run_attempt')==attempt
        and value.get('gnu_source')==GNU_SOURCE and value.get('source_before_sha256')==WINDOWS_NAT_SHA256
        and value.get('source_after_sha256')==PATCHED_SHA256 and value.get('inputs')==inputs and value.get('tool')==tool
        and relative_tool in TOOL_RELATIVE_PATHS and value.get('tool_relative_path')==relative_tool,
        'Diagnostic GDB build/source/patch/dependency/tool receipt differs')


def finish(exit_code):
    value=read_json(BUILD/'request.json') if (BUILD/'request.json').is_file() else {'schema_version':1,'diagnostic_only':True,'consumer_acceptance':False}
    try:
        require(exit_code==0,'Diagnostic configure/build failed with exit '+str(exit_code))
        require(build_inputs()==value['inputs'],'Recorded diagnostic build inputs changed')
        require(file_record(BUILD/'source/gdb-17.2/gdb/windows-nat.c')['sha256']==PATCHED_SHA256,'Built attach source changed')
        tool=resolve_tool();runtime=runtime_files(tool)
        require(runtime and len(runtime)<=64,'Diagnostic runtime binding is absent or exceeds bound')
        value.update(tool=file_record(tool),tool_relative_path=tool.relative_to(BUILD).as_posix(),runtime_files=runtime,source_before_sha256=WINDOWS_NAT_SHA256,source_after_sha256=PATCHED_SHA256,
            license_file=file_record(BUILD/'source/gdb-17.2/COPYING3'),built=True,error=None)
    except Exception as error:value.update(built=False,error=str(error)[:2048])
    value['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    for label in ('configure','make'):
        log=BUILD/(label+'.log')
        if log.is_file():
            value[label+'_log']=file_record(log)
            with log.open('rb') as stream:stream.seek(max(0,log.stat().st_size-32768));value[label+'_log_tail']=stream.read(32768).decode('utf-8',errors='replace')
    write_json(RECORD,value)
    if not value['built']:raise ValueError('Diagnostic GDB unavailable: '+value['error'])


def verified_debugger():
    value=read_json(RECORD);tool=resolve_tool()
    validate_record(value,build_inputs(),file_record(tool),os.environ.get('GITHUB_SHA'),os.environ.get('GITHUB_RUN_ID'),os.environ.get('GITHUB_RUN_ATTEMPT'),tool.relative_to(BUILD).as_posix())
    require(value.get('runtime_files') and len(value['runtime_files'])<=64,'Diagnostic runtime binding is absent')
    prefix=Path(sys.executable).parent.resolve()
    for name,expected in value['runtime_files'].items():
        path=Path(name);require(path.parent.resolve()==prefix and path.suffix.lower()=='.dll' and file_record(path)==expected,'Diagnostic runtime bytes differ')
    return tool.resolve()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','finish'));parser.add_argument('--exit-code',type=int,default=0)
    args=parser.parse_args()
    if args.mode=='prepare':prepare()
    else:finish(args.exit_code)
