# Reviewed financial-data imports

The bundled `verified_rows.json` is the template. It contains real Infosys consolidated Ind AS observations reviewed against primary filings. Make a copy, append source metadata and financial rows, and provide explicit period-header evidence in `period_metadata`.

Run from the project directory:

```powershell
python researchdesk/data_pipeline.py --import-reviewed path/to/reviewed_snapshot.json
```

The input is a **complete replacement snapshot**, not a patch. Retain earlier periods when adding new actuals. Each source requires an ID, HTTPS URL and title. Every row needs a known source ID, physical one-based PDF page, label, metric name, period columns and numeric values. Use `null` for missing observations; never substitute zero. `scale` converts the original source value to INR crore, or crore shares for share metrics. Negative tax credits remain negative; capex is a positive cash outflow magnitude.

Each period needs an explicit `end_date`, `kind` (`annual` or `quarter`), `months` (12 or 3), and source header provenance (`source_id`, `page`, `date_label`). Dates are never inferred from period IDs. Provide `reviewed_by`, `reviewed_at`, `retrieved_at`, `method`, `ticker: INFY`, `currency: INR`, and `unit: crore`. This adapter is limited to Infosys consolidated accounts; the reviewer is responsible for confirming accounting basis and source authenticity.

The importer rejects inconsistent columns, missing provenance, invalid/non-finite numbers, conflicting duplicate observations, and failed balance-sheet or tax tie-outs. It builds in a staging directory before replacing the source snapshot, CSV, and lastly the dataset through an atomic file replacement. Run only one importer at a time. This is not a multi-file database transaction; OS interruption between companion-file replacements can require rebuilding from the reviewed snapshot. Validation failures leave the existing files untouched.

The latest period is chosen from explicit period-end dates. Quarter balance-sheet values may reuse annual observations with exactly the same date; income and cash-flow periods are never mixed.

## Automation limits

`--refresh` attempts downloads for existing mapped source URLs and checks whether the mapped numeric observations occur on their cited PDF pages. It is a page-level numeric-presence check, not a semantic cell or table extraction guarantee. It does not discover new filings, infer new periods, or authorize new actuals. It retains the reviewed snapshot on failure. The current environment returned HTTP 403 for direct Infosys PDFs and SEC archive mirrors; `refresh_log.json` records that failure. Original PDF links remain available, but the bundled SHA-256 digests identify reviewed snapshots and analyst call notes, not downloaded originals.

Call search covers page-linked analyst paraphrases, not the full earnings-call transcript. Current sample quarters are discontinuous; absent cash-flow or balance-sheet observations remain missing. New source layouts, companies, accounting bases and currencies require a reviewed adapter extension.
