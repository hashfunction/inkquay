"""Prepare original sample files and retain bounded, owned capture output facts.
Copyright 2026 Trieflow LLC. MIT.
"""
import argparse, hashlib, json, os, re, stat, sys, uuid
from pathlib import Path
from demo_note import make_note, validate_note

MARKER='.scriblark-capture-owner'
NOTE='A pocket of green.xopp'
PDF='A pocket of green.pdf'

def require(condition,message):
    if not condition: raise ValueError(message)

def no_links(path):
    for part in (path,*path.parents):
        if os.path.lexists(part):
            value=part.lstat()
            require(not stat.S_ISLNK(value.st_mode) and not getattr(value,'st_file_attributes',0)&0x400,'Linked capture path')

def digest(path):
    no_links(path);value=path.lstat()
    require(stat.S_ISREG(value.st_mode) and value.st_size<=16000000,'Invalid bounded capture file')
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(descriptor,'rb') as stream:
        before=os.fstat(stream.fileno());data=stream.read(16000001);after=os.fstat(stream.fileno())
    no_links(path);final=path.lstat()
    signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    require(stat.S_ISREG(before.st_mode) and len(data)<=16000000 and len(data)==value.st_size and
            signature(value)==signature(before)==signature(after)==signature(final),'Capture file changed while reading')
    return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

def snapshot(root):
    result={}
    for path in root.rglob('*'):
        no_links(path)
        if path.is_dir(): continue
        require(len(result)<256,'Capture tree exceeds bound')
        result[path.relative_to(root).as_posix()]=digest(path)
    require(sum(v['bytes'] for v in result.values())<=64000000,'Capture tree exceeds byte bound')
    return result

def create(root,profiles):
    paths=[Path(root).absolute(),*[Path(p).absolute() for p in profiles]]
    require(len(set(paths))==3 and all(a not in b.parents for a in paths for b in paths if a!=b),'Capture trees overlap')
    for path in paths:
        no_links(path);require(not os.path.lexists(path),'Existing capture tree preserved');require(path.parent.is_dir(),'Capture parent absent')
    token=uuid.uuid4().hex;made=[]
    try:
        for path in paths:
            path.mkdir();made.append(path)
            with (path/MARKER).open('x',encoding='ascii') as stream:stream.write(token)
        data=make_note();document=validate_note(data)
        with (paths[0]/NOTE).open('xb') as stream:stream.write(data)
    except Exception:
        for path in reversed(made):
            if list(path.iterdir())==[path/MARKER] and (path/MARKER).read_text()==token:
                (path/MARKER).unlink();path.rmdir()
        raise
    return dict(schema_version=1,root=str(paths[0]),profiles=[str(p) for p in paths[1:]],token=token,
                original=digest(paths[0]/NOTE),document=document)

def verify(state,complete):
    root=Path(state['root']);paths=[root,*map(Path,state['profiles'])]
    for path in paths:
        no_links(path);require((path/MARKER).read_text(encoding='ascii')==state['token'],'Capture ownership marker changed')
    require(digest(root/NOTE)==state['original'],'Original sample notebook changed')
    files=snapshot(root)
    reports=[n for n in files if re.fullmatch(re.escape(PDF)+r'\.[0-9a-f-]{36}\.inkquay-report\.json',n)]
    allowed={MARKER,NOTE,PDF,*reports}
    require(set(files)<=allowed and len(reports)<=1,'Unexpected demo output preserved')
    result=dict(files=files,profiles={str(p):snapshot(p) for p in paths[1:]},complete=False)
    if complete:
        require(PDF in files and files[PDF]['bytes']>1000 and len(reports)==1,'Actual PDF/report missing')
        report=json.loads((root/reports[0]).read_text(encoding='utf-8-sig'))
        require((root/PDF).read_bytes().startswith(b'%PDF-'),'Export is not a PDF')
        expected={'version':1,'status':'passed','expectedPages':1,'actualPages':1,'outputBytes':files[PDF]['bytes'],'error':'','published':True,'recoveryFiles':[]}
        require(all(type(report.get(k)) is type(v) and report[k]==v for k,v in expected.items()),'Actual application PDF report did not pass')
        require(os.path.normcase(report['output'])==os.path.normcase(str(root/PDF)),'Application reported a different PDF')
        protected=report.get('protectedFiles')
        require(isinstance(protected,list) and len(protected)==1 and protected[0]['sha256Before']==state['original']['sha256'] and
            os.path.normcase(protected[0]['path'])==os.path.normcase(str(root/NOTE)),'Protected original note report differs')
        result.update(complete=True,pdf=files[PDF],report_name=reports[0],application_report=report)
    return result

def cleanup(state,seal,stopped):
    require(stopped,'Owned process must be stopped before cleanup')
    paths=[Path(state['root']),*map(Path,state['profiles'])]
    expected=[seal['files'],*[seal['profiles'][str(p)] for p in paths[1:]]]
    for path,files in zip(paths,expected):
        require((path/MARKER).read_text()==state['token'] and snapshot(path)==files,'Owned tree changed after seal; preserving it')
    for path in paths:
        for item in sorted(path.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if item.is_dir():item.rmdir()
            else:item.unlink()
        path.rmdir()
    return {'removed':all(not os.path.lexists(p) for p in paths)}

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['create','verify','seal','cleanup']);p.add_argument('--state',type=Path,required=True)
    p.add_argument('--root',type=Path);p.add_argument('--profile',action='append');p.add_argument('--stopped',action='store_true');a=p.parse_args()
    if a.mode=='create':
        require(a.root and a.profile and len(a.profile)==2,'Exact demo and two compatibility paths required')
        require(not os.path.lexists(a.state),'Existing state preserved');state=create(a.root,a.profile)
        with a.state.open('x',encoding='utf-8') as f:json.dump(state,f,indent=2)
        result=state
    else:
        digest(a.state);state=json.loads(a.state.read_text(encoding='utf-8'));seal=a.state.with_suffix('.seal.json')
        if a.mode in ('verify','seal'):
            result=verify(state,a.mode=='verify')
            if a.stopped:
                require(not os.path.lexists(seal),'Existing sealed observation preserved')
                with seal.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
        else:result=cleanup(state,json.loads(seal.read_text(encoding='utf-8')),a.stopped)
    print(json.dumps(result))

if __name__=='__main__':main()
