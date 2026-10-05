"""Local evidence retrieval: BM25 ranking and transparent keyword review."""
import re, math
from collections import Counter
from pathlib import Path

STOP=set('the a an and or of to in on for is are was were with this that it as at by from be we our you'.split())
TOPICS={'Guidance':['guidance','outlook','expect','growth'], 'Demand':['demand','discretionary','spending','pipeline'], 'Margins':['margin','utilization','pricing','cost'], 'Governance / risks':['litigation','contingent','related party','auditor','qualified opinion','material weakness','tax dispute'], 'AI':['generative','artificial intelligence',' ai ','topaz']}

def tokens(text): return [w for w in re.findall(r'[a-z0-9]+',text.lower()) if w not in STOP and len(w)>1]

def chunks(text, source_id):
    out=[]
    for page_no,page in enumerate(text.split('\f'),1):
        paragraphs=[p.strip() for p in re.split(r'\n\s*\n',page) if p.strip()]
        for para in paragraphs:
            for start in range(0,len(para),1400):
                part=para[start:start+1600]
                if len(part)>35: out.append(dict(source_id=source_id,page=page_no,text=part))
    return out

def load_chunks(data, root):
    result=[]
    for doc in data.get('documents',[]):
        path=Path(doc.get('text_path',''))
        if not path.is_absolute(): path=root/path
        if path.is_file():
            items=chunks(path.read_text(encoding='utf-8'),doc['source_id'])
            for item in items:
                pages=doc.get('page_map',[])
                if pages and item['page']<=len(pages): item['page']=pages[item['page']-1]
                item['kind']=doc.get('kind','source_text')
            result.extend(items)
    # Financial facts are independently searchable even when full PDFs cannot be fetched.
    for period in data['periods']:
        for key,value in period['metrics'].items():
            evidence=period.get('evidence',{}).get(key,{})
            if value is not None and evidence.get('source_id'):
                result.append(dict(source_id=evidence['source_id'],page=evidence.get('page',1),text=f"{period['id']} ended {period['end_date']}: {evidence.get('label',key)} = {value:,.3f} {evidence.get('unit','INR crore')}. Basis: {evidence.get('evidence_type','reported')}.",kind='reviewed_numeric_fact'))
    return result

def search(query, corpus, limit=6):
    q=set(tokens(query))
    if not q or not corpus: return []
    bags=[Counter(tokens(c['text'])) for c in corpus]
    lengths=[sum(b.values()) for b in bags]; avg=sum(lengths)/len(lengths) or 1
    dfs={t:sum(t in b for b in bags) for t in q}
    scored=[]
    for c,b,length in zip(corpus,bags,lengths):
        score=sum(math.log(1+(len(bags)-dfs[t]+.5)/(dfs[t]+.5))*b[t]*2.5/(b[t]+1.5*(.25+.75*length/avg)) for t in q if b[t])
        if score>0: scored.append({**c,'score':round(score,4),'topics':[k for k,v in TOPICS.items() if any(w in c['text'].lower() for w in v)]})
    return sorted(scored,key=lambda c:c['score'],reverse=True)[:limit]

def screen(text):
    matches=[]
    for topic,terms in TOPICS.items():
        for c in chunks(text,'uploaded-document'):
            if any(t in c['text'].lower() for t in terms):
                matches.append({**c,'topic':topic})
    return matches[:30]
