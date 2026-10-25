import json, os, tempfile, threading
from app.config.settings import BATCHES
_lock = threading.RLock()
def path(batch_id):
    if not batch_id or any(c not in '0123456789abcdef-' for c in batch_id.lower()): raise ValueError('Invalid batch ID')
    return BATCHES / f'{batch_id}.json'
def save(batch):
    target=path(batch['batch_id'])
    with _lock:
        fd,tmp=tempfile.mkstemp(dir=target.parent,suffix='.tmp')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(batch,f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
def get(batch_id):
    p=path(batch_id)
    with _lock:
        if not p.exists(): return None
        return json.loads(p.read_text(encoding='utf-8'))
def delete(batch_id):
    p=path(batch_id)
    with _lock:
        if p.exists(): p.unlink()
def listing():
    result=[]
    for p in BATCHES.glob('*.json'):
        try:
            b=json.loads(p.read_text(encoding='utf-8')); result.append({'batch_id':b['batch_id'],'created_at':b['created_at'],'status':b['status'],'document_count':len(b['documents'])})
        except Exception: pass
    return sorted(result,key=lambda x:x['created_at'],reverse=True)
