"""Financial integrity, provenance and reviewed-import regression tests."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from researchdesk.data_pipeline import DATA, build_dataset, import_reviewed

@pytest.fixture
def snapshot(tmp_path):
    raw=json.loads((DATA/'verified_rows.json').read_text(encoding='utf8'))
    save(tmp_path,raw)
    return tmp_path,raw

def save(root,raw):
    (root/'verified_rows.json').write_text(json.dumps(raw),encoding='utf8')

def test_financial_tieouts_and_provenance(snapshot):
    root,raw=snapshot
    data=build_dataset(root)
    assert len(data['validation_checks'])==12
    assert all(c['passed'] for c in data['validation_checks'])
    digest=hashlib.sha256((root/'verified_rows.json').read_bytes()).hexdigest()
    assert all(s['sha256']==digest for s in data['sources'])
    known={s['id'] for s in data['sources']}
    for period in data['periods']:
        assert period['date_evidence']['source_id'] in known
        for metric,value in period['metrics'].items():
            if value is not None:
                e=period['evidence'][metric]
                assert e['source_id'] in known and e['page']>=1 and e['snapshot_row']>=1

def test_quarter_cashflows_not_filled_from_annual(snapshot):
    data=build_dataset(snapshot[0]); p={p['id']:p for p in data['periods']}
    assert p['Q4FY26']['metrics']['cfo'] is None
    assert p['Q4FY26']['metrics']['capex'] is None
    assert p['FY26']['metrics']['cfo']==33986
    assert p['Q1FY27']['metrics']['cfo']==9330
    assert p['Q1FY26']['metrics']['total_assets'] is None

def test_conflicting_sources_rejected(snapshot):
    root,raw=snapshot
    duplicate=copy.deepcopy(raw['rows'][0]);duplicate['values'][0]+=100
    raw['rows'].append(duplicate);save(root,raw)
    with pytest.raises(ValueError,match='Conflicting source values'): build_dataset(root)

def test_failed_tieout_rejected(snapshot):
    root,raw=snapshot
    row=next(r for r in raw['rows'] if r['metric']=='total_assets' and 'FY24' in r['periods'])
    row['values'][1]+=100;save(root,raw)
    with pytest.raises(ValueError,match='tie-out failed'): build_dataset(root)

def test_dates_come_from_headers_not_names(snapshot):
    root,raw=snapshot
    raw['period_metadata']['arbitrary-label']=raw['period_metadata'].pop('Q1FY27')
    for row in raw['rows']:
        row['periods']=['arbitrary-label' if x=='Q1FY27' else x for x in row['periods']]
    save(root,raw);data=build_dataset(root)
    period=next(p for p in data['periods'] if p['id']=='arbitrary-label')
    assert period['end_date']=='2026-06-30' and period['months']==3
    assert data['latest_period']=='arbitrary-label'

def test_missing_explicit_date_rejected(snapshot):
    root,raw=snapshot;del raw['period_metadata']['Q1FY27'];save(root,raw)
    with pytest.raises(ValueError,match='explicit period metadata'): build_dataset(root)

def test_import_failure_preserves_dataset_and_companions(snapshot):
    root,raw=snapshot;build_dataset(root)
    original={n:(root/n).read_bytes() for n in ['dataset.json','verified_rows.json','normalized_financials.csv']}
    raw['rows'][0]['source_id']='not-real'
    incoming=root/'incoming.json';incoming.write_text(json.dumps(raw),encoding='utf8')
    with pytest.raises(ValueError,match='Unknown row source'): import_reviewed(incoming,root)
    assert all((root/n).read_bytes()==b for n,b in original.items())

def test_reviewed_period_import(snapshot):
    root,raw=snapshot
    # Existing real observation under new ID tests extensibility without fake actuals.
    raw['period_metadata']['reviewed-period']=raw['period_metadata'].pop('Q1FY27')
    for row in raw['rows']:
        row['periods']=['reviewed-period' if x=='Q1FY27' else x for x in row['periods']]
    incoming=root/'incoming.json';incoming.write_text(json.dumps(raw),encoding='utf8')
    data=import_reviewed(incoming,root)
    assert data['latest_period']=='reviewed-period'
    persisted=json.loads((root/'dataset.json').read_text())
    assert persisted['latest_period']=='reviewed-period'
    assert persisted['sources'][0]['sha256']==hashlib.sha256((root/'verified_rows.json').read_bytes()).hexdigest()

@pytest.mark.parametrize('value',[float('nan'),float('inf'),'48211',True])
def test_invalid_numeric_values_rejected(snapshot,value):
    root,raw=snapshot;raw['rows'][0]['values'][0]=value;save(root,raw)
    with pytest.raises(ValueError,match='Non-finite'): build_dataset(root)
