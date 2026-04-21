# README 

## Purpose
`Europe_PMC_downloader.py` attempts to download full-text XML of papers from a list of PMIDs (one per line) using the Europe PMC SOAP service.

The script is designed to process large lists robustly, writing results in streaming (successes/failures) and saving XML files incrementally.

## Requirements

### Software Requirements
- Python 3.10+ (tested in the project with Python 3.12)
- Active virtual environment (`.venv`)
- Python dependency:
  - `zeep`

### Network Requirements
- HTTP/HTTPS access to:
  - `https://www.ebi.ac.uk/europepmc/webservices/soap?wsdl`
  - `https://www.ebi.ac.uk/europepmc/webservices/soap`

## Installing Dependencies
If not already installed:

```bash
.venv/bin/pip install zeep
```

## Expected Input
- Text/TSV file with one PMID per line.
- Default: `failed_retry_v3.tsv`

Example:

```text
10048327
10052460
10089398
```

## How It Works
For each PMID the script:

1. Executes `searchPublications` with query:
   - `EXT_ID:<PMID> SRC:MED`
2. Extracts useful metadata (`pmcid`, `inPMC`, `isOpenAccess`, etc.).
3. Builds candidate `id/source` pairs for `getFulltextXML` (mainly with `source=PMC`).
4. Calls `getFulltextXML` and attempts to extract XML from:
   - SOAP attachment (`MessagePack`, `Attachment.content`)
   - inline fields (`fullTextXML`, `fullText`) if present
5. If XML is found:
   - saves `output_dir/<PMID>.xml`
   - writes the PMID to the success file
6. If no XML is found:
   - writes the PMID to the failed file

## CLI Parameters

```bash
.venv/bin/python Europe_PMC_downloader.py [options]
```

Main options:
- `--wsdl` WSDL URL (default Europe PMC)
- `--pmid-file` input PMID file (default `failed_retry_v3.tsv`)
- `--output-dir` XML output folder (default `missing_xml`)
- `--success-file` downloaded PMID file (default `downloaded_xml_pmids.tsv`)
- `--failed-file` undownloaded PMID file (default `failed_xml_pmids.tsv`)
- `--limit` limits the number of PMIDs to process (0 = all)
- `--sleep` pause between PMIDs in seconds
- `--timeout` SOAP timeout in seconds
- `--progress-every` print progress every N records
- `--verbose` detailed log record by record

## Usage Examples

### Quick test on few records
```bash
.venv/bin/python Europe_PMC_downloader.py \
  --limit 50 \
  --timeout 5 \
  --sleep 0 \
  --progress-every 10 \
  --output-dir missing_xml_test
```

### Full run
```bash
.venv/bin/python Europe_PMC_downloader.py \
  --pmid-file failed_retry_v3.tsv \
  --timeout 5 \
  --sleep 0 \
  --progress-every 250 \
  --output-dir missing_xml \
  --success-file downloaded_xml_pmids.tsv \
  --failed-file failed_xml_pmids.tsv
```

## Output Files
- XML folder: `missing_xml/`
  - one file per PMID: `<PMID>.xml`
- Success report: `downloaded_xml_pmids.tsv`
- Failure report: `failed_xml_pmids.tsv`

## Resilient Behavior
- Incremental report writing (flush on every line).
- If an XML already exists (`<PMID>.xml` non-empty), it is skipped as already downloaded.
- In case of interruption, work already written to disk remains available.

## Important Limitations
- Europe PMC SOAP `getFulltextXML` is available only for the full-text OA/PMC subset.
- Many PMIDs may not have XML available, so a high number of failures is normal.
- Some SOAP responses arrive as attachments and not as inline text; the script handles both cases.

## Troubleshooting

### Process stuck/slow
- Reduce `--timeout` (e.g., 5 seconds)
- Keep `--sleep 0`
- Use low `--progress-every` for better monitoring

### No XML downloaded
- Verify with a known OA/PMC PMID (e.g., a record with `HAS_FT:Y` via search)
- Check connectivity to the Europe PMC endpoint
