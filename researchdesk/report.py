"""Reproducible analyst research PDF from the same calculations as the app."""
import io
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from .engine import SCENARIOS, valuation, deviations, risks

GREEN=colors.HexColor('#176653'); NAVY=colors.HexColor('#152b38'); GRAY=colors.HexColor('#647982')
def make_report(data):
    buffer=io.BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=(595.28,841.89),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=44,title='ResearchDesk AI | Infosys earnings and valuation',author='ResearchDesk AI')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleRD',fontName='Helvetica-Bold',fontSize=25,leading=30,textColor=NAVY,spaceAfter=14))
    styles.add(ParagraphStyle(name='SubRD',fontSize=9,leading=14,textColor=GRAY,spaceAfter=12))
    styles.add(ParagraphStyle(name='BodyRD',fontSize=9,leading=14,textColor=NAVY,spaceAfter=10))
    styles.add(ParagraphStyle(name='SmallRD',fontSize=7,leading=10,textColor=GRAY,spaceAfter=7,wordWrap='CJK'))
    styles['Heading2'].textColor=GREEN; styles['Heading2'].fontSize=13
    story=[]
    def p(text,style='BodyRD'): story.append(Paragraph(text,styles[style]))
    def heading(text):p(text,'Heading2')
    def fmt(x,d=0):return 'N/A' if x is None else f'{x:,.{d}f}'
    def table(headers,rows,widths=None):
        cells=[[Paragraph(escape(str(x)),styles['SmallRD']) for x in row] for row in [headers]+rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f1ec')),('LINEBELOW',(0,0),(-1,0),.7,GREEN),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dce5e6')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.append(t);story.append(Spacer(1,12))
    annual=sorted([p for p in data['periods'] if p['kind']=='annual'],key=lambda p:p['end_date']);latest=next(p for p in data['periods'] if p['id']==data['latest_period']); base=annual[-1]
    prior=next((p for p in data['periods'] if p['kind']==latest['kind'] and p['end_date']==f"{int(latest['end_date'][:4])-1}{latest['end_date'][4:]}"),None)
    p('RESEARCHDESK AI / INDIA EQUITIES','SubRD');p('Infosys Limited','TitleRD');p(f"Earnings intelligence &amp; valuation workbook companion<br/>NSE: INFY | BSE: 500209 | Reviewed {data['as_of']} | Consolidated Ind AS",'SubRD')
    heading('What the latest results show')
    m=latest['metrics']
    p(f"{latest['id']} ended {latest['end_date']}: revenue of INR {fmt(m['revenue'])} crore and owner PAT of INR {fmt(m['pat'])} crore. Derived EBITDA was INR {fmt(m['ebitda'])} crore, with an EBITDA margin of {fmt(m['ebitda_margin'],1)}%. Source: {latest['evidence']['revenue'].get('source_id','missing')}, statement of profit and loss, PDF page {latest['evidence']['revenue'].get('page','missing')}.")
    if prior:
        rows=deviations(latest,prior)
        table(['Metric',latest['id'],prior['id'],'Change'],[[r['metric'].replace('_',' ').upper(),fmt(r['current'],1),fmt(r['reference'],1),f"{fmt(r['delta'],1)} {r['unit']}"] for r in rows[:6]],[170,110,110,121])
    p('Interpretation: compare revenue growth with profitability and cash collection. These mechanical deviations identify review priorities; they do not establish a beat or miss against consensus. No consensus feed or live market price is connected.')
    heading('Annual financial record')
    table(['INR crore unless noted']+[x['id'] for x in annual],[[label]+[fmt(x['metrics'].get(k),d) for x in annual] for k,label,d in [('revenue','Revenue',0),('ebitda','Derived EBITDA',0),('pat','Owner PAT',0),('roe','ROE (%)',1),('roce','ROCE (%)',1),('cfo','Operating cash flow',0),('capex','Reported cash capex',0),('working_capital','Accounting working capital',0)]],[211,100,100,100])
    p('Sources: INFY-FY25 and INFY-FY26. FY26 includes an exceptional INR 1,289 crore labour-code expense. FY26 capex is reported net of sale proceeds; comparative labeling differs. Missing ROE/ROCE require an opening balance sheet and are not filled with guesses.','SmallRD')
    story.append(PageBreak())
    p('Valuation: three explicit scenarios','TitleRD');p(f"Five-year annual FCFF model using {base['id']} reported revenue and fiscal year-end balance sheet. INR per ordinary share.",'SubRD')
    vals={name:valuation(base,a) for name,a in SCENARIOS.items()}
    table(['Assumption / output','Bear','Base','Bull'],[[label]+[fmt(SCENARIOS[n][k]*mult,d) for n in vals] for k,label,mult,d in [('growth','Revenue growth (%)',100,1),('margin','EBIT margin (%)',100,1),('wacc','WACC (%)',100,1),('terminal_growth','Terminal growth (%)',100,1),('pe','P/E assumption (x)',1,1),('ev_ebitda','EV/EBITDA assumption (x)',1,1)]]+[[label]+[fmt(vals[n][k]) for n in vals] for k,label in [('dcf_per_share','DCF value / share'),('pe_per_share','P/E value / share'),('ev_ebitda_per_share','EV/EBITDA value / share')]], [211,100,100,100])
    p('All scenario inputs are illustrative analyst assumptions, not company guidance, observed peer multiples or a recommendation. P/E uses reported annual owner PAT. EV/EBITDA uses first forecast-year derived EBITDA. No percentage upside is shown without an independently dated market quote.')
    heading('Base-case cash-flow model')
    table(['Year','Revenue','NOPAT','D&A','Capex','Change WC','FCFF'],[[f['year']]+[fmt(f[k]) for k in ['revenue','nopat','da','capex','delta_wc','fcff']] for f in vals['Base']['forecasts']],[35,85,80,70,75,83,83])
    v=vals['Base'];p(f"Base enterprise value: INR {fmt(v['enterprise_value'])} crore. Less net debt of INR {fmt(v['net_debt'])} crore and minority interest of INR {fmt(v['minority'])} crore gives equity value of INR {fmt(v['equity_value'])} crore. Divided by {fmt(v['shares_crore'],3)} crore ordinary shares. Terminal value contributes {fmt(v['terminal_share_pct'],1)}% of enterprise value.")
    p('FCFF = EBIT x (1 - tax) + D&A - capex - change in operating working capital. Operating WC is an assumed percentage of revenue; initial WC is normalized to the same ratio. Terminal reinvestment is recalculated at terminal growth. Cash bridge adds cash and current investments only, deducts lease liabilities and book minority interests. Lease treatment requires forecast capex to include ROU additions. Non-current investments are excluded conservatively.','SmallRD')
    heading('Model sensitivity and limitations')
    p('The app exposes both growth/margin and WACC/terminal-growth sensitivity grids. Terminal growth must remain below WACC. Stable margins and reinvestment ratios simplify a complex operating business; terminal-value concentration and share-count changes can materially alter value.')
    story.append(PageBreak());p('Evidence, risks & reproducibility','TitleRD')
    for r in risks(data):
        heading(escape(r['title']));p(escape(r['detail']))
    heading('Primary source register')
    for s in data['sources']:
        p(f"<b>{escape(s['id'])}</b> - {escape(s['title'])}<br/><link href=\"{escape(s['url'])}\" color=\"#176653\">Open original filing / transcript</link>. Published {escape(s.get('published_at','unknown'))}; reviewed {escape(s['retrieved_at'])}.",'SmallRD')
    p('Reproduce with: python run.py data; python run.py test; python run.py report. Full metric-level page provenance, snapshot checksums and validation results are bundled in data/. The local UI and PDF use the same calculation engine. No measured analyst time-saving claim is made.','SmallRD')
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#dce5e6'));canvas.line(42,34,553,34);canvas.setFont('Helvetica',7);canvas.setFillColor(GRAY);canvas.drawString(42,23,'ResearchDesk AI | Research prototype | Historical facts + explicit scenarios');canvas.drawRightString(553,23,str(doc.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer);return buffer.getvalue()

if __name__=='__main__':
    import json
    from .engine import enrich
    root=Path(__file__).resolve().parents[1]
    data=enrich(json.loads((root/'data/dataset.json').read_text(encoding='utf8')))
    target=root/'reports/Infosys_Research_Report.pdf';target.parent.mkdir(exist_ok=True);target.write_bytes(make_report(data));print(target)
