"""Pure financial calculations. Currency INR crore; shares crore; prices INR.

Reported operating EBIT excludes other income and includes exceptional costs.
Lease liabilities treated as debt; D&A includes ROU depreciation. Forecast capex
therefore includes assumed ROU additions. Cash bridge includes cash + current
investments only, conservatively excluding non-current investments.
"""
from math import isfinite

DEFINITIONS = {
 'ebit': 'PBT + finance cost - other income; includes exceptional operating costs',
 'ebitda': 'EBIT + depreciation/amortization; derived, not company adjusted EBITDA',
 'ebit_margin': 'Operating EBIT / revenue × 100',
 'ebitda_margin': 'Derived EBITDA / revenue × 100',
 'pat_margin': 'PAT attributable to owners / revenue × 100',
 'roe': 'Annual PAT attributable to owners / average opening and closing parent equity × 100',
 'roce': 'Annual operating EBIT / average (total assets - current liabilities) × 100',
 'debt_equity': 'Lease debt / parent equity; Infosys has no separately reported borrowings in this dataset',
 'net_debt': 'Lease debt - cash - current investments; excludes non-current investments',
 'working_capital': 'Current assets - current liabilities (broad accounting working capital)',
 'operating_wc': 'Trade receivables - trade payables (partial operating working capital proxy)',
 'dso': 'Closing receivables / period revenue × days in period; quarter and annual bases differ',
 'fcf': 'Cash from operations less cash capital expenditure; not unlevered FCFF',
}

SCENARIOS = {
 'Bear': dict(growth=.04, margin=.18, wacc=.125, terminal_growth=.035, tax=.27, da=.03, capex=.04, nwc=.18, pe=18., ev_ebitda=12.),
 'Base': dict(growth=.08, margin=.21, wacc=.11, terminal_growth=.04, tax=.26, da=.03, capex=.04, nwc=.18, pe=23., ev_ebitda=16.),
 'Bull': dict(growth=.12, margin=.23, wacc=.10, terminal_growth=.045, tax=.25, da=.03, capex=.04, nwc=.18, pe=28., ev_ebitda=20.),
}

def divide(a, b, scale=1):
    return a / b * scale if a is not None and b is not None and b != 0 else None

def calculate(period, previous=None):
    m = dict(period['metrics'])
    def sumfields(*fields):
        return sum(m[k] for k in fields) if all(m.get(k) is not None for k in fields) else None
    m['ebit'] = m['pbt'] + m['finance_cost'] - m['other_income'] if all(m.get(k) is not None for k in ('pbt','finance_cost','other_income')) else None
    m['ebitda'] = sumfields('ebit','da')
    for key in ('ebit','ebitda','pat'):
        m[key+'_margin'] = divide(m.get(key), m.get('revenue'), 100)
    m['net_debt'] = m['lease_debt']-m['cash']-m['current_investments'] if all(m.get(k) is not None for k in ('lease_debt','cash','current_investments')) else None
    m['debt_equity'] = divide(m.get('lease_debt'), m.get('equity'))
    for target, a, b in [('working_capital','current_assets','current_liabilities'),('operating_wc','receivables','payables'),('fcf','cfo','capex')]:
        m[target] = m[a]-m[b] if m.get(a) is not None and m.get(b) is not None else None
    m['dso'] = divide(m.get('receivables'), m.get('revenue'), 365 if period['kind']=='annual' else 91.25)
    m['roe'] = m['roce'] = None
    if period['kind']=='annual' and previous:
        p = previous['metrics']
        if all(x is not None for x in (m.get('equity'),p.get('equity'))):
            m['roe'] = divide(m.get('pat'), (m['equity']+p['equity'])/2, 100)
        if all(x is not None for x in (m.get('total_assets'),p.get('total_assets'),m.get('current_liabilities'),p.get('current_liabilities'))):
            m['roce'] = divide(m['ebit'], (m['total_assets']-m['current_liabilities']+p['total_assets']-p['current_liabilities'])/2,100)
    return {**period, 'metrics':m}

def enrich(data):
    previous = None
    periods=[]
    for p in sorted(data['periods'], key=lambda x:(x['kind'],x['end_date'])):
        consecutive=previous and int(p['end_date'][:4])-int(previous['end_date'][:4])==1 and p['end_date'][4:]==previous['end_date'][4:]
        periods.append(calculate(p, previous if p['kind']=='annual' and consecutive else None))
        if p['kind']=='annual': previous=p
    return {**data,'periods':periods,'definitions':DEFINITIONS}

def deviations(current, reference, label='YoY', pct_threshold=5., bps_threshold=50.):
    rows=[]
    for k in ('revenue','ebitda','pat','ebit_margin','ebitda_margin','pat_margin','working_capital','net_debt','dso'):
        a,b=current['metrics'].get(k),reference['metrics'].get(k)
        if a is None or b is None: continue
        margin=k.endswith('margin')
        delta=(a-b)*100 if margin else (a-b)/abs(b)*100 if b else None
        rows.append(dict(metric=k,current=a,reference=b,delta=delta,unit='bps' if margin else '%',comparison=label,material=delta is not None and abs(delta)>=(bps_threshold if margin else pct_threshold)))
    return rows

def validate_assumptions(a):
    required=set(SCENARIOS['Base'])
    if required-set(a): raise ValueError('Missing scenario inputs: '+', '.join(sorted(required-set(a))))
    if any(not isinstance(a[k],(float,int)) or not isfinite(a[k]) for k in required): raise ValueError('Inputs must be finite numbers')
    ranges={'growth':(-.5,.5),'margin':(0,.5),'wacc':(.01,.4),'terminal_growth':(-.02,.1),'tax':(0,.6),'da':(0,.2),'capex':(0,.3),'nwc':(0,.8),'pe':(1,80),'ev_ebitda':(1,60)}
    for k,(lo,hi) in ranges.items():
        if not lo<=a[k]<=hi: raise ValueError(f'{k} must be between {lo} and {hi}')
    if a['wacc']<=a['terminal_growth']: raise ValueError('WACC must exceed terminal growth')

def valuation(period, assumptions):
    validate_assumptions(assumptions)
    a=assumptions; m=period['metrics']
    if period['kind']!='annual': raise ValueError('DCF requires an annual base period')
    required=('revenue','shares_crore','lease_debt','cash','current_investments','minority')
    missing=[k for k in required if m.get(k) is None]
    if missing: raise ValueError('Missing valuation inputs: '+', '.join(missing))
    if m['shares_crore']<=0 or m['revenue']<=0: raise ValueError('Positive shares and revenue required')
    revenue=m['revenue']; wc=revenue*a['nwc']; forecasts=[]; pv=0
    for year in range(1,6):
        revenue*=1+a['growth']; ebit=revenue*a['margin']; nopat=ebit*(1-a['tax'])
        da=revenue*a['da']; capex=revenue*a['capex']; new_wc=revenue*a['nwc']; delta_wc=new_wc-wc; wc=new_wc
        fcff=nopat+da-capex-delta_wc; discounted=fcff/(1+a['wacc'])**year; pv+=discounted
        forecasts.append(dict(year=year,revenue=revenue,ebit=ebit,nopat=nopat,da=da,capex=capex,delta_wc=delta_wc,fcff=fcff,pv=discounted))
    # Recompute terminal reinvestment at terminal growth, not year-5 growth.
    terminal_revenue=revenue*(1+a['terminal_growth'])
    terminal_fcff=terminal_revenue*(a['margin']*(1-a['tax'])+a['da']-a['capex'])-(terminal_revenue-revenue)*a['nwc']
    tv=terminal_fcff/(a['wacc']-a['terminal_growth']); pv_tv=tv/(1+a['wacc'])**5
    ev=pv+pv_tv; net_debt=m['lease_debt']-m['cash']-m['current_investments']; equity=ev-net_debt-m['minority']
    forward_ebitda=forecasts[0]['ebit']+forecasts[0]['da']
    # P/E on reported annual owner PAT; no unsupported forward PAT forecast.
    pe_value=divide(m.get('pat'),m['shares_crore'])
    return dict(assumptions=a,forecasts=forecasts,enterprise_value=ev,net_debt=net_debt,minority=m['minority'],equity_value=equity,shares_crore=m['shares_crore'],dcf_per_share=equity/m['shares_crore'],terminal_share_pct=pv_tv/ev*100,terminal_fcff=terminal_fcff,pe_per_share=pe_value*a['pe'] if pe_value is not None else None,ev_ebitda_per_share=(forward_ebitda*a['ev_ebitda']-net_debt-m['minority'])/m['shares_crore'])

def sensitivities(period, a):
    growth=[a['growth']-.02,a['growth'],a['growth']+.02]
    margins=[a['margin']-.02,a['margin'],a['margin']+.02]
    wacc=[a['wacc']-.01,a['wacc'],a['wacc']+.01]
    terminal=[a['terminal_growth']-.005,a['terminal_growth'],a['terminal_growth']+.005]
    def grid(xs,ys,xk,yk):
        rows=[]
        for y in ys:
            row=[]
            for x in xs:
                try: row.append(valuation(period,{**a,xk:x,yk:y})['dcf_per_share'])
                except ValueError: row.append(None)
            rows.append(row)
        return {'columns':xs,'rows':ys,'values':rows,'column_key':xk,'row_key':yk}
    return {'growth_margin':grid(growth,margins,'growth','margin'),'wacc_terminal':grid(wacc,terminal,'wacc','terminal_growth')}

def risks(data):
    annual=sorted([p for p in data['periods'] if p['kind']=='annual'],key=lambda p:p['end_date'])
    flags=[dict(severity='Review',title='Governance coverage is incomplete',detail='Keyword screening cannot establish governance quality. Read auditor opinions, related-party notes, litigation, pledges and exchange disclosures.'),dict(severity='Assumption',title='Valuation inputs are analyst scenarios',detail='WACC, growth, margins and valuation multiples are illustrative assumptions, not market consensus. No live market quote is supplied.')]
    if annual:
        p=annual[-1]; m=p['metrics']
        if m.get('cfo') is not None and m.get('pat') and m['cfo']<m['pat']:
            flags.append(dict(severity='Watch',title='Cash conversion below PAT',detail=f"{p['id']}: operating cash flow is below owner PAT; review working capital and non-cash items."))
        if len(annual)>1:
            old=annual[-2]['metrics']
            if m.get('dso') is not None and old.get('dso') is not None and m['dso']-old['dso']>5:
                flags.append(dict(severity='Watch',title='Receivables days increased',detail=f"Closing-balance DSO rose {m['dso']-old['dso']:.1f} days. Review collection timing and contract assets."))
    for issue in data.get('issues',[])[:8]:
        flags.append(dict(severity='Data',title=issue.get('code','Source / normalization note').replace('_',' ').capitalize() if isinstance(issue,dict) else 'Source / normalization note',detail=issue.get('message',str(issue)) if isinstance(issue,dict) else str(issue)))
    return flags
