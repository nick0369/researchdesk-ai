"""Auditable Infosys source-row normalization and optional primary-PDF verification.
The bundled snapshot is web-verified numeric facts, NOT a downloaded PDF. Network
refresh fails closed and never silently changes audited observations. New periods
require a reviewed adapter/source-row mapping.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, math, os, shutil, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
REQUIRED='revenue pat pbt other_income finance_cost da tax equity total_equity total_assets current_assets current_liabilities cash current_investments noncurrent_investments lease_debt receivables payables cfo capex shares_crore minority'.split()

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load_dataset(data_dir=DATA): return json.loads((Path(data_dir)/'dataset.json').read_text(encoding='utf8'))

def validate_reviewed(raw):
    """Validate analyst attestation, explicit source dates and numeric row schema."""
    for key in ('reviewed_by', 'reviewed_at', 'retrieved_at', 'method'):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f'Missing review metadata: {key}')
    for key in ('reviewed_at','retrieved_at'):
        datetime.fromisoformat(raw[key])
    if (raw.get('ticker'),raw.get('currency'),raw.get('unit')) != ('INFY','INR','crore'):
        raise ValueError('This adapter accepts INFY consolidated INR crore observations only')
    source_ids=set()
    for source in raw.get('sources',[]):
        if not source.get('id') or source['id'] in source_ids:
            raise ValueError('Source IDs must be present and unique')
        if not str(source.get('url','')).startswith('https://') or not source.get('title'):
            raise ValueError('Source requires HTTPS URL and title')
        source_ids.add(source['id'])
    metadata=raw.get('period_metadata',{})
    if not metadata or not raw.get('rows'): raise ValueError('Period metadata and rows are required')
    for ident, meta in metadata.items():
        datetime.strptime(meta['end_date'],'%Y-%m-%d')
        if meta.get('kind') not in ('annual','quarter') or meta.get('months') != (12 if meta['kind']=='annual' else 3):
            raise ValueError(f'Unsupported fiscal period: {ident}')
        if meta.get('source_id') not in source_ids or not meta.get('date_label') or not isinstance(meta.get('page'),int) or meta['page']<1:
            raise ValueError(f'Missing source header provenance: {ident}')
    for row in raw['rows']:
        if row.get('source_id') not in source_ids: raise ValueError('Unknown row source_id')
        if not isinstance(row.get('page'),int) or row['page']<1 or not row.get('label') or not row.get('metric'):
            raise ValueError('Missing row provenance')
        if not row.get('periods') or len(row['periods'])!=len(row.get('values',[])):
            raise ValueError('Column count mismatch')
        if any(p not in metadata for p in row['periods']): raise ValueError('Missing explicit period metadata')
        if len(set(row['periods']))!=len(row['periods']): raise ValueError('Duplicate period in row')
        if not isinstance(row.get('scale',1),(int,float)) or not math.isfinite(row.get('scale',1)) or row.get('scale',1)<=0:
            raise ValueError('Invalid scale')
        if any(v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)) for v in row['values']):
            raise ValueError('Non-finite or invalid observation')

def build_dataset(data_dir=DATA):
    data_dir=Path(data_dir)
    source_path=data_dir/'verified_rows.json'
    raw=json.loads(source_path.read_text(encoding='utf8'))
    validate_reviewed(raw)
    sources=[]
    for s in raw['sources']:
        sources.append({**s,'path':'data/verified_rows.json','sha256':sha(source_path),'hash_scope':'reviewed_numeric_snapshot_not_original_pdf','retrieved_at':raw['retrieved_at'],'raw_pdf_available':False})
    periods={}
    checks=[]
    for line,r in enumerate(raw['rows'],1):
        if len(r['periods'])!=len(r['values']): raise ValueError('Column count mismatch')
        for ident,value in zip(r['periods'],r['values']):
            if value is None: continue
            meta=raw['period_metadata'][ident]
            p=periods.setdefault(ident,{'id':ident,'end_date':meta['end_date'],'kind':meta['kind'],'months':meta['months'],'date_evidence':{k:meta[k] for k in ('source_id','page','date_label')},'metrics':{},'evidence':{}})
            v=round(float(value)*r.get('scale',1),8)
            if r['metric'] in p['metrics'] and abs(p['metrics'][r['metric']]-v)>0.001: raise ValueError(f'Conflicting source values: {ident} {r["metric"]}')
            p['metrics'][r['metric']]=v
            p['evidence'][r['metric']]={'source_id':r['source_id'],'page':r['page'],'label':r['label'],'snapshot_row':line,'evidence_type':'fact_source_reported','confidence':'high','unit':'crore shares' if 'shares' in r['metric'] else 'INR per share' if r['metric']=='eps' else 'INR crore'}
    for p in periods.values():
        m=p['metrics']; e=p['evidence']
        for target,a,b in [('tax','current_tax','deferred_tax'),('lease_debt','lease_current','lease_noncurrent')]:
            if a in m and b in m:
                m[target]=m[a]+m[b]; e[target]={**e[a],'label':f'{a} + {b}','evidence_type':'derived_calculation','components':[a,b]}
        if 'total_assets' in m:
            if not all(k in m for k in ('total_equity','current_liabilities','noncurrent_liabilities')):
                raise ValueError('Incomplete balance-sheet tie-out inputs')
            residual=m['total_assets']-m['total_equity']-m['current_liabilities']-m['noncurrent_liabilities']
            checks.append({'period':p['id'],'check':'Balance sheet balances','residual':residual,'passed':abs(residual)<=1})
        if 'group_pat' in m:
            if not all(k in m for k in ('pbt','tax')): raise ValueError('Incomplete tax tie-out inputs')
            residual=m['pbt']-m['tax']-m['group_pat']
            checks.append({'period':p['id'],'check':'PBT less tax equals group PAT','residual':residual,'passed':abs(residual)<=1})
        p['missing']=[k for k in REQUIRED if k not in m]
        for k in p['missing']: m[k]=None; e[k]={'evidence_type':'missing_required_source','confidence':'low','label':'Not present in mapped source table'}
    # Share point-in-time balance observations only when explicit source dates match.
    for p in periods.values():
        if p['kind']=='quarter':
            annual=next((x for x in periods.values() if x['kind']=='annual' and x['end_date']==p['end_date']),None)
            if annual:
                for k in ['equity','total_equity','total_assets','current_assets','current_liabilities','cash','current_investments','noncurrent_investments','lease_debt','receivables','payables','shares_crore','minority']:
                    if p['metrics'].get(k) is not None and annual['metrics'].get(k) is not None and abs(p['metrics'][k]-annual['metrics'][k])>0.001:
                        raise ValueError('Conflicting same-date balance-sheet observation')
                    if p['metrics'].get(k) is None:
                        p['metrics'][k]=annual['metrics'][k]; p['evidence'][k]={**annual['evidence'][k],'balance_date':p['end_date']}
                p['missing']=[k for k in REQUIRED if p['metrics'].get(k) is None]
    if not all(c['passed'] for c in checks): raise ValueError('Financial tie-out failed')
    docs=[]
    transcript=data_dir/'sources'/'q1fy27_call_notes.txt'
    if transcript.exists():
        sources.append({'id':'INFY-CALL-Q1FY27','title':'Infosys Q1 FY27 earnings call: analyst source notes','url':'https://www.infosys.com/investors/reports-filings/quarterly-results/2026-2027/q1/documents/transcripts/earningscall.pdf','path':'data/sources/q1fy27_call_notes.txt','sha256':sha(transcript),'hash_scope':'analyst_notes_not_full_transcript','retrieved_at':raw['retrieved_at'],'published_at':'2026-07-23','raw_pdf_available':False})
        docs.append({'source_id':'INFY-CALL-Q1FY27','text_path':'data/sources/q1fy27_call_notes.txt','kind':'transcript_notes','full_text':False,'page_map':[3,4,5]})
    data={'schema_version':1,'company':{'name':'Infosys Limited','ticker':'INFY','nse':'INFY','bse':'500209','currency':'INR','unit':'crore','basis':'Consolidated Ind AS'},'as_of':'2026-10-04','latest_period':'Q1FY27','sources':sources,'periods':sorted(periods.values(),key=lambda p:(p['end_date'],p['months'])),'documents':docs,'validation_checks':checks,'issues':[{'severity':'warning','code':'RAW_PDF_FETCH_BLOCKED','message':'Infosys returned HTTP 403 to direct download. Snapshot contains reviewed primary-source numeric facts; snapshot hashes are not PDF hashes. Original PDFs remain linked.'},{'severity':'warning','code':'EXCEPTIONAL_ITEM','message':'FY26 reported PBT includes INR 1,289 crore labour-code expense. Historical figures are reported, not management-adjusted.'},{'severity':'warning','code':'CAPEX_BASIS','message':'FY26 and Q1 FY27 capex is net of sale proceeds; FY25 comparative statement labels expenditure without this qualifier. Treat FCF comparability with care.'},{'severity':'warning','code':'COVERAGE_GAPS','message':'Sample quarter coverage is discontinuous. Q1 FY26 balance sheet and Q4 quarterly cash flows are missing; annual cash flow is never used as quarterly cash flow.'},{'severity':'info','code':'TRANSCRIPT_NOTES','message':'Bundled call search uses analyst paraphrases with PDF page anchors, not the complete copyrighted transcript.'}],'normalization_notes':['Amounts are INR crore, shares in crore; EPS INR/share.','PAT is profit attributable to owners; group PAT used for tax tie-out.','Shares are period-end ordinary shares net of treasury in note 2.11; weighted average shares stored separately.','PDF page numbers are physical, one-based; index cover is page 1.','Snapshot is reviewed data, not a general-purpose automatic parser. Refresh verifies existing mapped observations; adding issuers or periods requires reviewed mapping.']}
    data['as_of']=raw['reviewed_at']
    data['latest_period']=max(periods.values(),key=lambda p:(p['end_date'],-p['months']))['id']
    data['review']={k:raw[k] for k in ('reviewed_by','reviewed_at','method')}
    (data_dir/'dataset.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    with (data_dir/'normalized_financials.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.writer(f); writer.writerow(['period','end_date','metric','value','unit','source_id','pdf_page','evidence_type'])
        for p in data['periods']:
            for k,v in p['metrics'].items():
                e=p['evidence'][k];writer.writerow([p['id'],p['end_date'],k,v,e.get('unit','INR crore'),e.get('source_id',''),e.get('page',''),e['evidence_type']])
    return data

def import_reviewed(input_path, data_dir=DATA):
    """Import a complete reviewed snapshot; validate before atomic dataset commit.

    Input replaces the complete source-row snapshot, not an incremental patch.
    The prior dataset stays readable until os.replace commits the validated file.
    Use one writer at a time; source/CSV companion files are replaced before it.
    """
    data_dir=Path(data_dir); data_dir.mkdir(parents=True,exist_ok=True)
    raw=json.loads(Path(input_path).read_text(encoding='utf-8-sig'))
    validate_reviewed(raw)
    with tempfile.TemporaryDirectory(prefix='.review-',dir=data_dir) as tmp:
        stage=Path(tmp)
        (stage/'verified_rows.json').write_text(json.dumps(raw,indent=2),encoding='utf8')
        if (data_dir/'sources').exists(): shutil.copytree(data_dir/'sources',stage/'sources')
        dataset=build_dataset(stage)
        if not dataset['validation_checks']: raise ValueError('Import has no financial tie-outs')
        for name in ('verified_rows.json','normalized_financials.csv','dataset.json'):
            os.replace(stage/name,data_dir/name)
    return dataset

def refresh(data_dir=DATA):
    """Fetch mapped primary PDFs; check expected numeric rows; preserve snapshot on failure."""
    import requests
    from pypdf import PdfReader
    data_dir=Path(data_dir); raw=json.loads((data_dir/'verified_rows.json').read_text(encoding='utf8'))
    result=[]
    for s in raw['sources']:
        try:
            response=requests.get(s['url'],timeout=45); response.raise_for_status()
            if not response.content.startswith(b'%PDF'): raise ValueError('Source response is not a PDF')
            from io import BytesIO
            pages=[p.extract_text(extraction_mode='layout') or '' for p in PdfReader(BytesIO(response.content)).pages]
            for r in [r for r in raw['rows'] if r['source_id']==s['id']]:
                tokens=re.findall(r'\(?\d[\d,]*(?:\.\d+)?\)?',pages[r['page']-1])
                nums=[float(t.replace(',','').replace('(','-').replace(')','')) for t in tokens]
                # Every mapped nonzero observation must be present on its physical source page.
                if any(v != 0 and ((-v if r['metric']=='capex' else v) not in nums) for v in r['values']): raise ValueError(f'Source drift in {r["metric"]}; manual review required')
            path=data_dir/'sources'/f'{s["id"]}.pdf'; path.parent.mkdir(exist_ok=True);path.write_bytes(response.content)
            path.with_suffix('.txt').write_text('\f'.join(pages),encoding='utf8')
            result.append({'source_id':s['id'],'status':'verified','sha256':sha(path),'path':str(path.relative_to(ROOT)),'retrieved_at':datetime.now(timezone.utc).isoformat()})
        except Exception as exc: result.append({'source_id':s['id'],'status':'failed','error':str(exc),'snapshot_retained':True})
    (data_dir/'refresh_log.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    actions=parser.add_mutually_exclusive_group()
    actions.add_argument('--refresh',action='store_true')
    actions.add_argument('--import-reviewed',type=Path,metavar='JSON',help='Validate and import a complete analyst-reviewed source-row snapshot')
    args=parser.parse_args()
    if args.refresh:
        result=refresh();print(json.dumps(result,indent=2));raise SystemExit(0 if all(x['status']=='verified' for x in result) else 1)
    d=import_reviewed(args.import_reviewed) if args.import_reviewed else build_dataset()
    print(f'Built {len(d["periods"])} periods; {len(d["validation_checks"])} passed tie-outs')
