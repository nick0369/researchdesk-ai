# ResearchDesk AI

**A working Python equity research application with real Infosys financial data, evidence-linked earnings reviews, and editable valuation scenarios.**

The default edition runs locally without API keys. “AI” is the project name: this build uses deterministic financial calculations, BM25 text retrieval and keyword review, not a connected generative model.

## Start here

Requires Python 3.11+ and a browser. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py serve
```

Open **http://127.0.0.1:8765**. API documentation: **http://127.0.0.1:8765/docs**.

On Windows, `powershell -ExecutionPolicy Bypass -File .\start.ps1` creates the environment on first run and starts the server. This is a per-process invocation; it does not change the system execution policy. On macOS/Linux activate with `source .venv/bin/activate`.

Other commands:

```text
python run.py data                 # rebuild normalized dataset and CSV from reviewed source rows
python run.py data --refresh       # fetch mapped source PDFs and check numeric observations
python run.py data --import-reviewed path/to/reviewed_snapshot.json
python run.py test                 # automated tests
python run.py report               # regenerate reports/Infosys_Research_Report.pdf
```

The `run.py` entry point also supports embedded Python installations that omit the current directory from the module path. Standard installations can use `python -m researchdesk.data_pipeline`, `python -m researchdesk.report` and `python -m uvicorn researchdesk.app:app --host 127.0.0.1 --port 8765`.

## What is implemented

| Capability | Implementation |
|---|---|
| Financial dashboard | Annual revenue chart, selectable periods, metric scorecard, source links |
| Normalization | Reviewed source rows → explicit period metadata → validated financials → JSON and CSV |
| Financial metrics | Revenue, EBIT, EBITDA, owner PAT, margins, ROE, ROCE, lease leverage, working capital, DSO, CFO and FCF |
| What changed? | Equal-duration comparisons; materiality at 5% for amounts and 50 bps for margins |
| Investment baselines | SQLite history of analyst assumptions with period, metric, rationale and timestamp |
| DCF | Five-year FCFF, terminal reinvestment, enterprise-to-equity bridge, per-share valuation |
| Relative valuation | P/E and EV/EBITDA using explicitly assumed multiples |
| Scenarios | Bear/Base/Bull presets and editable inputs |
| Sensitivities | Revenue growth × EBIT margin; WACC × terminal growth |
| Evidence retrieval | Local BM25 ranking over financial observations and page-linked call notes |
| Document review | Local UTF-8 text / text-PDF extraction; topic and risk keyword screening |
| Research export | Source-linked PDF generated from the same Python engine; detailed CSV |
| Audit controls | Source IDs, physical PDF pages, evidence types, snapshot SHA-256, missing values, tie-outs |
| Refresh/import | Fixed-source download verification and validated full-snapshot reviewed import |

## Real-data coverage

Issuer: **Infosys Limited**, NSE **INFY**, BSE **500209**. Basis: **consolidated Ind AS**. Amounts: **INR crore**, shares: **crore ordinary shares**, per-share values: **INR**. Review date: **4 October 2026**.

- Annual periods: FY24, FY25 and FY26, each ending 31 March.
- Sample quarters: Q4FY24, Q4FY25, Q4FY26, Q1FY26 and Q1FY27.
- Latest included quarter: Q1FY27, ended 30 June 2026.
- Eight periods, 85 reviewed financial source rows, 12 balance-sheet/tax reconciliation checks in the bundled snapshot.
- Q1FY27 revenue: INR 48,211 crore; owner PAT: INR 7,769 crore. FY26 revenue: INR 178,650 crore; owner PAT: INR 29,440 crore.

The data comes from these primary sources:

1. [Infosys consolidated Ind AS FY25/FY24 financial statements](https://www.infosys.com/investors/reports-filings/quarterly-results/2024-2025/q4/documents/consolidated/consol-fy25-q4-and-12m-finstatement.pdf)
2. [Infosys consolidated Ind AS FY26/FY25 financial statements](https://www.infosys.com/investors/reports-filings/quarterly-results/2025-2026/q4/documents/consolidated/consol-fy26-q4-and-12m-finstatement.pdf)
3. [Infosys consolidated Ind AS Q1FY27 financial statements](https://www.infosys.com/investors/reports-filings/quarterly-results/2026-2027/q1/documents/consolidated/consol-fy27-q1-finstatement.pdf)
4. [Infosys Q1FY27 earnings call](https://www.infosys.com/investors/reports-filings/quarterly-results/2026-2027/q1/documents/transcripts/earningscall.pdf)

**Data-access limitation:** direct issuer and SEC mirror downloads returned HTTP 403 in the build environment. The bundled actuals are reviewed numeric snapshots checked through web-readable primary filings. Their hashes identify the snapshots, not original PDF files. Call search uses short analyst paraphrases with original PDF page anchors; the full transcript is not bundled. Financial facts and source notes are labeled separately. Source copyright remains with its owner.

`--refresh` attempts the existing mapped URLs, validates PDF content and checks numeric presence on cited pages. It preserves reviewed data and exits nonzero when verification fails. It does **not** discover new filings or automatically approve new actuals. Successful page-level numeric matching is not semantic table validation. Read [the import guide](data/IMPORT_GUIDE.md) to add reviewed periods.

## Financial methodology

| Metric | Definition |
|---|---|
| Operating EBIT | PBT + finance cost − other income |
| EBITDA | Operating EBIT + depreciation/amortization |
| Owner PAT | Profit attributable to owners, not profit including non-controlling interests |
| ROE | Annual owner PAT / average opening and closing parent equity |
| ROCE | Annual EBIT / average opening and closing (assets − current liabilities) |
| Lease leverage | Lease liabilities / parent equity; no separately reported borrowings in this snapshot |
| Net debt | Lease liabilities − cash − current investments |
| Accounting working capital | Current assets − current liabilities |
| Operating WC proxy | Receivables − payables; not a complete operating-WC schedule |
| DSO | Closing receivables / period revenue × approximate period days (365 annual; 91.25 quarterly) |
| Reported FCF | CFO − reported cash capex; not unlevered FCFF |

Missing required observations remain null. ROE/ROCE are not annualized from quarterly earnings. The earliest year lacks an opening balance sheet, so its average-denominator ratios remain unavailable. Quarterly balance sheets can reuse annual balance sheets only at exactly the same date; annual cash flow is never labeled quarterly.

FY26 PBT includes an exceptional **INR 1,289 crore labour-code charge**. Derived EBIT/EBITDA retain it. The app does not silently replace statutory earnings with adjusted earnings. FY26 and Q1FY27 capex are net of sale proceeds; comparative presentation differs, which affects FCF comparability.

### DCF mechanics

```text
Revenue(t) = Revenue(t−1) × (1 + growth)
EBIT(t) = Revenue(t) × assumed EBIT margin
NOPAT(t) = EBIT(t) × (1 − assumed tax rate)
FCFF(t) = NOPAT(t) + D&A(t) − capex(t) − change in operating WC(t)
PV FCFF(t) = FCFF(t) / (1 + WACC)^t
Terminal revenue = Revenue(5) × (1 + terminal growth)
Terminal FCFF = terminal NOPAT + terminal D&A − terminal capex − terminal change WC
Terminal value = Terminal FCFF / (WACC − terminal growth)
EV = sum(PV FCFF years 1–5) + PV terminal value
Equity value = EV − net debt − book minority interest
DCF / share = equity value / period-end ordinary shares (crore)
```

Operating working capital is normalized to the scenario revenue ratio in the base year, then projected consistently. This is a simplifying assumption, not the reported accounting working-capital balance. Terminal change in working capital uses terminal growth, not year-five forecast growth. WACC must exceed terminal growth. Non-finite inputs, implausible ranges, missing bridge inputs and non-positive share counts are rejected.

Lease liabilities are treated as debt. D&A includes right-of-use depreciation; forecast capex therefore includes an assumed ROU-additions allowance. The reported FCF metric uses reported cash capex separately. Non-current investments are excluded from the equity bridge. Minority interest uses its book value as a proxy. Shares use fiscal year-end ordinary shares net of treasury rather than weighted-average EPS shares.

P/E values use reported annual owner PAT divided by ending shares; EV/EBITDA values use the first forecast-year EBITDA and the same equity bridge. Multiples are illustrative assumptions, **not** a researched peer-comps dataset. No live stock price, consensus feed or upside-to-current-price calculation is supplied.

### Default assumptions

| Input | Bear | Base | Bull |
|---|---:|---:|---:|
| Revenue growth | 4% | 8% | 12% |
| EBIT margin | 18% | 21% | 23% |
| WACC | 12.5% | 11% | 10% |
| Terminal growth | 3.5% | 4% | 4.5% |
| Tax | 27% | 26% | 25% |
| D&A / revenue | 3% | 3% | 3% |
| Capex incl. ROU / revenue | 4% | 4% | 4% |
| Operating WC / revenue | 18% | 18% | 18% |
| P/E | 18x | 23x | 28x |
| EV/EBITDA | 12x | 16x | 20x |

The PDF uses these presets. Browser edits are temporary and do not change the PDF presets. Saved analyst baselines persist in SQLite; scenario edits do not. There is no investment recommendation or price target endorsed by an analyst.

## Architecture

```text
Primary filings / reviewed snapshot      Uploaded PDF or text
                  |                               |
    explicit metadata + source-row map        text extraction
                  |                               |
    provenance validation + tie-outs         topic screening
                  |                               |
        dataset.json + normalized CSV        review passages
                  |
   financial engine + DCF + deviations + BM25 retrieval
                  |
       FastAPI → local HTML/CSS/JavaScript dashboard
                  |                      |
        SQLite analyst baselines       PDF / CSV exports
```

- `researchdesk/engine.py`: pure financial calculations, scenarios, sensitivities and rules.
- `researchdesk/data_pipeline.py`: source normalization, validation, imports and refresh verification.
- `researchdesk/documents.py`: BM25 retrieval, page mapping, topic review.
- `researchdesk/app.py`: typed FastAPI endpoints, limits and local baseline storage.
- `researchdesk/report.py`: reproducible ReportLab PDF.
- `static/`: responsive frontend; no build tooling required.
- `data/verified_rows.json`: source-row snapshot and explicit period-header metadata.
- `data/dataset.json`: normalized values, evidence and QA notes.
- `data/refresh_log.json`: last attempted network-verification results.
- `tests/`: finance, data integrity and application tests.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Availability and mode |
| GET | `/api/research` | Enriched data, source register, default scenarios and risks |
| GET | `/api/changes?period=Q1FY27&reference=Q1FY26` | Historical and saved-baseline deviations |
| POST | `/api/baselines` | Save period, metric, numeric value and rationale |
| POST | `/api/valuation` | Annual period and validated assumption dictionary |
| GET | `/api/search?q=guidance` | Ranked source-linked passages |
| POST | `/api/documents/review` | Raw PDF/text bytes, up to 10MB / 200 pages |
| GET | `/api/export/financials.csv` | Metric-level data and evidence export |
| GET | `/api/report.pdf` | Research report with default scenarios |

Uploads stay in memory for the request and are not sent to an AI service or persisted. Scanned PDFs require OCR before upload. Keyword matches require human review and cannot establish governance quality. Baselines are local analyst assumptions, not external consensus.

## Validation and deployment

Build validation: **26 automated tests passed**. Tests cover accounting reconciliations, conflict rejection, null handling, source hashes, explicit dates, atomic dataset replacement, an independently hand-calculated DCF case, sensitivity monotonicity, bad inputs, baseline persistence, evidence page anchors, uploads and PDF/CSV routes. Browser checks verify real-data rendering and scenario recalculation. The generated PDF is visually checked after rendering.

Docker packaging is provided:

```text
docker build -t researchdesk .
docker run --rm -p 127.0.0.1:8765:8765 researchdesk
```

Docker was not run in this environment. The default Python launcher binds to localhost. This is a single-user research prototype without authentication or multi-user authorization. Before internet hosting, add access control, rate limits, resource isolation for untrusted PDFs, production logging and durable storage. Source repository: https://github.com/nick0369/researchdesk-ai. A public application deployment has not been created.

## Extending responsibly

For another issuer, build a separate reviewed adapter with correct consolidated/standalone basis, currency, units and period definitions. Do not relabel Infosys rows. For a new quarter, obtain the primary filing, add reviewed source rows and explicit source-header dates to a full snapshot, import it, run tests, and inspect the report. Add a licensed market-data provider for quotes/consensus and researched peers for market-derived multiples. A production unattended feed requires official/licensed access, discovery, parsing, schema-change alerts and human exception review.

## Portfolio description you can substantiate

> Built a Python/FastAPI equity-research prototype using real Infosys consolidated financial disclosures. Implemented provenance-aware normalization, financial KPI calculations, material-deviation checks, editable DCF and relative-valuation scenarios, local evidence retrieval, and source-linked PDF exports with automated financial and API tests.

Analyst processing-time reduction has **not** been measured. Validate it with a timed manual-vs-assisted study before adding a quantified impact claim. Local demo and source archive are ready; add genuine repository and hosted-demo URLs only after publication.
