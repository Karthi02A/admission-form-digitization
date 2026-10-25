from fastapi.testclient import TestClient
from app-old.main import app
client=TestClient(app)
def test_health():assert client.get('/health').json()['status']=='healthy'
def test_batch_export_and_delete():
    r=client.post('/api/batches');assert r.status_code==200;bid=r.json()['batch_id']
    assert client.get(f'/api/batches/{bid}').status_code==200
    x=client.get(f'/api/batches/{bid}/export.xlsx');assert x.status_code==200 and x.content[:2]==b'PK'
    c=client.get(f'/api/batches/{bid}/export.csv');assert c.status_code==200 and b'Document ID' in c.content
    assert client.delete(f'/api/batches/{bid}').status_code==200
    assert client.get(f'/api/batches/{bid}').status_code==404
