import sqlite3
import pytest
from fastapi.testclient import TestClient
from researchdesk.app import app
from researchdesk.engine import SCENARIOS

client=TestClient(app)

def test_health_and_real_data():
    assert client.get('/api/health').json()['dataset_ready']
    assert len(client.get('/api/research').json()['periods'])>=8
    assert client.get('/').status_code==200

def test_changes_reject_period_mismatch():
    assert client.get('/api/changes?period=FY26&reference=Q1FY27').status_code==422
    assert client.get('/api/changes?period=BAD&reference=FY25').status_code==404

def test_valuation_endpoint():
    r=client.post('/api/valuation',json={'period':'FY26','assumptions':SCENARIOS['Base']})
    assert r.status_code==200 and len(r.json()['forecasts'])==5
    r=client.post('/api/valuation',json={'period':'Q1FY27','assumptions':SCENARIOS['Base']})
    assert r.status_code==422

def test_export_and_report():
    r=client.get('/api/export/financials.csv');assert r.status_code==200 and 'fact_source_reported' in r.text
    r=client.get('/api/report.pdf');assert r.status_code==200 and r.content.startswith(b'%PDF')

def test_search_has_citations():
    r=client.get('/api/search?q=guidance').json()
    assert r['results'] and all(x['source_id'] and x['page']>=1 for x in r['results'])
    assert all(x['page'] in (3,4,5) for x in r['results'] if x['source_id']=='INFY-CALL-Q1FY27')

def test_upload_text_and_empty():
    r=client.post('/api/documents/review',content=b'The company expects demand and margin growth. Review this guidance carefully.')
    assert r.status_code==200 and r.json()['matches']
    assert client.post('/api/documents/review',content=b'').status_code==422

def test_baseline_persistence(tmp_path,monkeypatch):
    import researchdesk.app as module
    def connect():
        db=sqlite3.connect(tmp_path/'test.sqlite3')
        db.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, period TEXT, metric TEXT, value REAL, note TEXT, created_at TEXT)')
        return db
    monkeypatch.setattr(module,'connection',connect)
    payload={'period':'Q1FY27','metric':'revenue','value':44000,'note':'Pre-results thesis assumption'}
    assert client.post('/api/baselines',json=payload).status_code==200
    rows=client.get('/api/changes?period=Q1FY27&reference=Q1FY26').json()['rows']
    assert any(r['comparison']=='Analyst baseline' and r['reference']==44000 for r in rows)
    assert client.post('/api/baselines',json={**payload,'metric':'fake'}).status_code==422
