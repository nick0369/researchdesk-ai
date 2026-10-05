import math
from copy import deepcopy
import pytest
from researchdesk.engine import *
from researchdesk.data_pipeline import load_dataset

@pytest.fixture
def data():return enrich(load_dataset())

def test_actual_reconciliation_and_lease_bridge(data):
    p=next(p for p in data['periods'] if p['id']=='FY26');m=p['metrics']
    assert m['revenue']==178650
    assert m['pat']==29440
    assert m['ebit']==39995+416-4322
    assert m['ebitda']==m['ebit']+4902
    assert m['net_debt']==9176-22201-12950
    assert m['roe']==pytest.approx(29440/((92852+95818)/2)*100)

def test_missing_opening_equity_is_not_zero(data):
    p=next(p for p in data['periods'] if p['id']=='FY24')
    assert p['metrics']['roe'] is None
    q=next(p for p in data['periods'] if p['id']=='Q1FY26')
    assert q['metrics']['working_capital'] is None

def test_terminal_value_independent_hand_calculation():
    p={'kind':'annual','metrics':{'revenue':100,'shares_crore':10,'lease_debt':5,'cash':10,'current_investments':0,'minority':2,'pat':12}}
    a={**SCENARIOS['Base'],'growth':0,'margin':.2,'tax':.25,'da':.03,'capex':.03,'nwc':.1,'wacc':.1,'terminal_growth':0}
    r=valuation(p,a)
    # Constant 15 FCFF forever at 10% = 150 EV; add 5 net cash, deduct 2 minority.
    assert r['enterprise_value']==pytest.approx(150)
    assert r['dcf_per_share']==pytest.approx(15.3)
    assert r['terminal_fcff']==pytest.approx(15)

def test_bad_assumptions_rejected(data):
    p=next(p for p in data['periods'] if p['id']=='FY26')
    for patch in ({'wacc':.04,'terminal_growth':.04},{'growth':float('nan')},{'tax':1.1}):
        with pytest.raises(ValueError):valuation(p,{**SCENARIOS['Base'],**patch})
    p=deepcopy(p);p['metrics']['shares_crore']=0
    with pytest.raises(ValueError):valuation(p,SCENARIOS['Base'])

def test_sensitivity_monotonicity(data):
    p=next(p for p in data['periods'] if p['id']=='FY26')
    g=sensitivities(p,SCENARIOS['Base'])
    assert g['growth_margin']['values'][2][1]>g['growth_margin']['values'][1][1]
    assert g['wacc_terminal']['values'][1][0]>g['wacc_terminal']['values'][1][2]

def test_bps_and_zero_reference():
    rows=deviations({'metrics':{'ebit_margin':21,'revenue':2}},{'metrics':{'ebit_margin':20,'revenue':0}})
    assert next(r for r in rows if r['metric']=='ebit_margin')['delta']==100
    assert next(r for r in rows if r['metric']=='revenue')['delta'] is None

def test_nonconsecutive_years_do_not_form_average_denominators():
    raw=load_dataset();raw['periods']=[p for p in raw['periods'] if p['id']!='FY25']
    p=next(p for p in enrich(raw)['periods'] if p['id']=='FY26')
    assert p['metrics']['roe'] is None and p['metrics']['roce'] is None
