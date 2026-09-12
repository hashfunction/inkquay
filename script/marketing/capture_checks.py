"""Require one reviewed existing unsigned Store package for marketing captures.
Copyright 2026 Trieflow LLC. MIT. This does not run the release qualification again.
"""
import argparse,json,os,re,subprocess,sys
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'msix'))
import msix_qualification as msix
from source_publication import require,load
from store_workflow_evidence import EVENTS

REPOSITORY='hashfunction/inkquay'
PACKAGE_NAME='Scriblark_1.0.1.0_x64.msix'
BINDING=Path(__file__).with_name('binding.json')
digest=msix.file_record
read_json=load

def relative_path(value):
    require(isinstance(value,str) and value and '\\' not in value and ':' not in value and not value.startswith('/') and
        all(x not in ('','.','..') for x in value.split('/')) and str(PurePosixPath(value))==value,'Unsafe artifact path')
    return value

def validate_binding(value):
    require(value.get('schema_version')==1 and value.get('product')=='Scriblark' and isinstance(value.get('qualified'),dict),'Capture needs a reviewed successful Store package')
    b=value['qualified']
    require(set(b)=={'source_commit','workflow_run_id','workflow_run_attempt','package','readiness_receipt','store_artifact_id','metadata_artifact_id'},'Exact capture binding fields required')
    require(isinstance(b['source_commit'],str) and re.fullmatch('[0-9a-f]{40}',b['source_commit']) and
        all(isinstance(b[k],str) and re.fullmatch('[1-9][0-9]*',b[k]) for k in ('workflow_run_id','workflow_run_attempt')),'Invalid exact source/run')
    for key in ('package','readiness_receipt'):
        v=b[key];require(set(v)=={'bytes','sha256'} and type(v['bytes']) is int and v['bytes']>0 and re.fullmatch('[0-9a-f]{64}',v['sha256']),'Invalid exact byte binding')
    require(all(type(b[k]) is int and b[k]>0 for k in ('store_artifact_id','metadata_artifact_id')),'Exact artifact IDs required')
    return b

def binding():return validate_binding(load(BINDING))

def assert_checkout(source,commit):
    def git(*args):return subprocess.check_output(['git','-C',str(source),*args],timeout=30).decode().strip()
    require(git('rev-parse','HEAD')==commit and not git('status','--porcelain=v1','--untracked-files=all'),'Exact clean source checkout required')

def assert_capture_checkout():assert_checkout(BINDING.parents[2],os.environ.get('GITHUB_SHA'))
def assert_qualified_checkout(source,bound):assert_checkout(source,bound['source_commit'])

def verify_inputs(package,ready_path,metadata,source,run,bound):
    assert_qualified_checkout(source,bound)
    require(digest(package)==bound['package'] and digest(ready_path)==bound['readiness_receipt'],'Original MSIX/readiness bytes changed')
    ready=load(ready_path)
    require(run.get('id')==int(bound['workflow_run_id']) and run.get('run_attempt')==int(bound['workflow_run_attempt']) and
        run.get('head_sha')==bound['source_commit'] and run.get('conclusion')=='success' and
        run.get('repository',{}).get('full_name')==REPOSITORY and run.get('path')=='.github/workflows/windows.yml','Original successful Windows run differs')
    require(ready.get('unsigned') is True and ready.get('both_installed_workflows_passed') is True and
        ready.get('store_identity_used') is True and ready.get('identity')==msix.STORE_IDENTITY and
        ready.get('store_package')==bound['package'] and ready.get('diagnostic_observer') is False,'Original unsigned release receipt differs')
    require(all(ready.get(k)==bound[k] for k in ('source_commit','workflow_run_id','workflow_run_attempt')),'Original receipt source/run differs')
    roots=list(Path(metadata).rglob('msix-store-package-record.json'))
    require(len(roots)==1,'Exact original Store metadata missing');root=roots[0].parent
    evidence=ready['qualification_evidence'];require(isinstance(evidence,dict) and evidence,'Original evidence hashes missing')
    # Native archives are intentionally absent from the metadata-only artifact.
    # Their exact names/hashes must be present in its original hash-bound cache list.
    cache={}
    cache_file=root/'msys2-cache-sha256.txt'
    if cache_file.exists():
        require(digest(cache_file)==evidence['msys2-cache-sha256.txt'],'Original cache inventory changed')
        for line in cache_file.read_text(encoding='utf-8-sig').splitlines():
            parts=line.split(maxsplit=1);require(len(parts)==2 and re.fullmatch('[0-9a-f]{64}',parts[0]),'Invalid original cache hash')
            path=parts[1].lstrip('*');require(path.startswith('build-evidence/package-cache/'),'Unexpected cache path')
            name=relative_path(path.removeprefix('build-evidence/'))
            require(name not in cache and name.endswith(('.pkg.tar.zst','.pkg.tar.zst.sig')),'Unexpected cached archive')
            cache[name]=parts[0]
    require(set(cache)=={n for n in evidence if n.startswith('package-cache/')},'Original cache evidence membership differs')
    for name,value in evidence.items():
        relative_path(name)
        if name in cache:
            require(value['sha256']==cache[name] and type(value['bytes']) is int and value['bytes']>0,'Cache hash differs')
        else:require(digest(root/name)==value,'Retained original qualification evidence changed: '+name)
    for mode,prefix in [('qualification','msix'),('store','msix-store')]:
        record=load(root/(prefix+'-package-record.json'));receipt=load(root/(prefix+'-install/installation-qualification.json'))
        require(record['sourceCommit']==bound['source_commit'] and record['identityMode']==mode and record['identity']==msix.identity_for_mode(mode),'Original package identity differs')
        require(receipt['identity_mode']==mode and receipt['identity']==record['identity'] and
            all(receipt[k]==bound[k] for k in ('source_commit','workflow_run_id','workflow_run_attempt')),'Original installation context differs')
        for key in ('installation_qualification_passed','workflow_acceptance','clean_close_verified','uninstall_verified','unsigned_package_unchanged'):
            require(receipt[key] is True,'Original installed workflow did not pass: '+key)
        require(receipt['primary_error'] is None and receipt['cleanup_errors']==[] and receipt['evidence_errors']==[] and
            receipt['residual_package_full_names']==[] and receipt['diagnostic_observer_requested'] is False,'Original installation contains errors')
        workflow=load(root/(prefix+'-install/workflow/workflow-result.json'))
        require(workflow==receipt['workflow'] and workflow['passed'] is True and workflow['diagnostic_observer'] is False and
            [e['action'] for e in workflow['events']]==[e[0] for e in EVENTS],'Original complete consumer sequence differs')
        for name,value in receipt['qualification_helpers'].items():
            relative_path(name);require(digest(Path(source)/'script/msix'/name)==value,'Original qualified helper changed')
        for name in ('process_exit','cleanup_process_exit'):
            v=receipt[name];require(v['normal_exit'] is True and v['wait_completed'] is True and type(v['exit_code']) is int and v['exit_code']==0,'Original process exit differs')
    require(msix.verify_msix(package,record['payload'],'store')==record['containerVerification'],'Original unsigned payload differs')
    return record

def main():
    p=argparse.ArgumentParser();p.add_argument('--binding-output',type=Path);p.add_argument('--inputs',type=Path);p.add_argument('--qualified-source',type=Path);a=p.parse_args();b=binding()
    if a.binding_output:
        with a.binding_output.open('a',encoding='utf-8') as f:f.write('qualified_source='+b['source_commit']+'\n')
    else:
        assert_capture_checkout();require(a.inputs and a.qualified_source,'Prepared exact inputs required')
        verify_inputs(a.inputs/'store'/PACKAGE_NAME,a.inputs/'store/release-ready.json',a.inputs/'metadata',a.qualified_source,load(a.inputs/'qualified-run.json'),b)
        print('Exact original unsigned Store package and original native evidence verified; capture only.')
if __name__=='__main__':main()
