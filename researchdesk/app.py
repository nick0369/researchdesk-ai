import io, json, sqlite3, csv
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .engine import enrich, deviations, valuation, sensitivities, risks, SCENARIOS
from .documents import load_chunks, search, screen

ROOT=Path(__file__).resolve().parents[1]
app=FastAPI(title='ResearchDesk AI',version='1.0.0',description='Local, source-backed equity research. No generative AI API required.')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

def dataset():
    path=ROOT/'data/dataset.json'
    if not path.exists(): raise HTTPException(503,'Dataset unavailable. Run python -m researchdesk.data_pipeline first.')
    return enrich(json.loads(path.read_text(encoding='utf-8')))

def connection():
    db=sqlite3.connect(ROOT/'data/researchdesk.sqlite3')
    db.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, period TEXT, metric TEXT, value REAL, note TEXT, created_at TEXT)')
    return db

class Scenario(BaseModel):
    model_config=ConfigDict(extra='forbid')
    period:str
    assumptions:dict[str,float]

class Baseline(BaseModel):
    model_config=ConfigDict(extra='forbid')
    period:str
    metric:str
    value:float=Field(allow_inf_nan=False)
    note:str=Field(min_length=5,max_length=500)

@app.get('/')
def index(): return FileResponse(ROOT/'static/index.html')

@app.get('/api/health')
def health(): return {'status':'ok','dataset_ready':(ROOT/'data/dataset.json').exists(),'mode':'local evidence retrieval; no LLM'}

@app.get('/api/research')
def research():
    data=dataset()
    return {**data,'risks':risks(data),'scenario_defaults':SCENARIOS}

@app.get('/api/changes')
def changes(period:str,reference:str):
    data=dataset(); lookup={p['id']:p for p in data['periods']}
    if period not in lookup or reference not in lookup: raise HTTPException(404,'Unknown period')
    p,r=lookup[period],lookup[reference]
    if p['kind']!=r['kind'] or p.get('months')!=r.get('months'): raise HTTPException(422,'Compare periods of equal duration')
    rows=deviations(p,r,f'{period} vs {reference}')
    with connection() as db:
        baseline=db.execute('SELECT metric,value,note,created_at FROM baselines WHERE period=? ORDER BY id DESC',(period,)).fetchall()
    seen=set()
    for metric,value,note,created in baseline:
        if metric in seen: continue
        seen.add(metric)
        for row in deviations(p,{'metrics':{metric:value}},'Analyst baseline'):
            rows.append({**row,'note':note,'created_at':created})
    return {'rows':rows}

@app.post('/api/baselines')
def save_baseline(b:Baseline):
    data=dataset(); p=next((p for p in data['periods'] if p['id']==b.period),None)
    allowed={'revenue','ebitda','pat','ebit_margin','ebitda_margin','pat_margin','working_capital','net_debt','dso'}
    if p is None or b.metric not in allowed: raise HTTPException(422,'Unknown period or unsupported baseline metric')
    with connection() as db:
        db.execute('INSERT INTO baselines(period,metric,value,note,created_at) VALUES(?,?,?,?,?)',(b.period,b.metric,b.value,b.note,datetime.now(timezone.utc).isoformat()))
    return {'saved':True,'label':'User-provided analyst assumption; not consensus'}

@app.post('/api/valuation')
def value(s:Scenario):
    p=next((p for p in dataset()['periods'] if p['id']==s.period),None)
    if p is None: raise HTTPException(404,'Unknown period')
    try: return {**valuation(p,s.assumptions),'sensitivities':sensitivities(p,s.assumptions)}
    except ValueError as e: raise HTTPException(422,str(e))

@app.get('/api/search')
def evidence(q:str=Query(default='',max_length=500)):
    data=dataset()
    return {'mode':'BM25 evidence retrieval, not a generated answer','results':search(q,load_chunks(data,ROOT))}

@app.post('/api/documents/review')
async def review(request:Request):
    # Raw file body avoids storing user documents; 10MB streamed cap.
    parts=[]; size=0
    async for part in request.stream():
        size+=len(part)
        if size>10*1024*1024: raise HTTPException(413,'Maximum file size is 10MB')
        parts.append(part)
    raw=b''.join(parts)
    if raw.startswith(b'%PDF'):
        try:
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(raw))
            if len(reader.pages)>200: raise HTTPException(422,'Maximum 200 pages')
            text='\f'.join(p.extract_text() or '' for p in reader.pages)
        except HTTPException: raise
        except Exception: raise HTTPException(422,'PDF could not be read; use an unencrypted text PDF')
    else:
        try: text=raw.decode('utf-8')
        except UnicodeDecodeError: raise HTTPException(422,'Upload a text PDF or UTF-8 text file')
    if len(text.strip())<40: raise HTTPException(422,'No usable text found. Scanned PDFs require OCR before import.')
    return {'characters':len(text),'matches':screen(text),'notice':'Keyword review only. Uploaded material is not persisted or promoted into financial actuals. Review context; a keyword match is not a finding.'}

@app.get('/api/export/financials.csv')
def export_csv():
    out=io.StringIO(); w=csv.writer(out); w.writerow(['period','end_date','kind','metric','value','unit','evidence_type','source_id','page','definition'])
    data=dataset()
    for p in data['periods']:
        for key,val in p['metrics'].items():
            e=p.get('evidence',{}).get(key,{})
            unit='percent' if key.endswith('margin') or key in ('roe','roce') else 'days' if key=='dso' else 'ratio' if key=='debt_equity' else 'crore shares' if 'shares_crore' in key else 'INR per share' if key=='eps' else 'INR crore'
            w.writerow([p['id'],p['end_date'],p['kind'],key,'' if val is None else val,unit,e.get('evidence_type','derived_calculation') if val is not None else 'missing_required_source',e.get('source_id',''),e.get('page',''),data['definitions'].get(key,'')])
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=infosys_financials.csv'})

@app.get('/api/report.pdf')
def report():
    from .report import make_report
    return Response(make_report(dataset()),media_type='application/pdf',headers={'Content-Disposition':'inline; filename=Infosys_Research_Report.pdf'})
