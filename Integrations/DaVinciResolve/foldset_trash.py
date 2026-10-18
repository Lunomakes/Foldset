"""System Trash only. No permanent-delete fallback."""
import json
import traceback
import subprocess
from pathlib import Path
from datetime import datetime
import uuid
from foldset_moves import fingerprint
from foldset_tags import save_json

ROOT=Path.home()/'Library/Application Support/Foldset/Resolve/TrashReports'
HELPER=Path(__file__).with_name('FoldsetTrashFile')

def plan(records):
    entries=[]
    for record in records:
        stamp=fingerprint(record['path'])
        if stamp[0]!=record['identity']:
            raise ValueError('文件已改变，请重新扫描。')
        entries.append({'source':record['path'],'fingerprint':stamp,'state':'planned'})
    if not entries:raise ValueError('请先选择文件。')
    return {'entries':entries,'createdAt':datetime.now().isoformat()}

def execute(batch,root=ROOT,helper=HELPER,progress=None):
    batch['implementation']='trash-utf8-bytes-v2'
    for entry in batch['entries']:
        if fingerprint(entry['source'])!=entry['fingerprint']:
            raise ValueError('文件已改变，未执行，请重新扫描。')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    journal=root/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json')
    save_json(journal,batch)
    for entry in batch['entries']:
        try:
            if progress:progress(sum(e['state']=='trashed' for e in batch['entries']),entry['source'])
            if fingerprint(entry['source'])!=entry['fingerprint']:raise ValueError('文件发生变化')
            result=subprocess.run([str(helper),entry['source']],capture_output=True)
            stdout=result.stdout.decode('utf-8') if isinstance(result.stdout,bytes) else result.stdout
            stderr=result.stderr.decode('utf-8',errors='replace') if isinstance(result.stderr,bytes) else result.stderr
            if result.returncode:raise RuntimeError(stderr.strip() or '系统无法移到废纸篓')
            entry['state']='trashed'
            entry['trashPath']=json.loads(stdout)['path']
            save_json(journal,batch)
        except Exception as error:
            entry['error']=str(error);entry['traceback']=traceback.format_exc();save_json(journal,batch);break
    if progress:progress(sum(e['state']=='trashed' for e in batch['entries']),'')
    return journal,batch
