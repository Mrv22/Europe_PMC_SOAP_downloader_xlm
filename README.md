# README 

## Scopo
`Europe_PMC_downloader.py` tenta di scaricare il full-text XML dei paper a partire da una lista di PMID (uno per riga), usando il servizio SOAP di Europe PMC.

Lo script e progettato per processare grandi liste in modo robusto, scrivendo i risultati in streaming (successi/fallimenti) e salvando i file XML man mano.

## Requisiti

### Requisiti software
- Python 3.10+ (testato nel progetto con Python 3.12)
- Ambiente virtuale attivo (`.venv`)
- Dipendenza Python:
  - `zeep`

### Requisiti di rete
- Accesso HTTP/HTTPS a:
  - `https://www.ebi.ac.uk/europepmc/webservices/soap?wsdl`
  - `https://www.ebi.ac.uk/europepmc/webservices/soap`

## Installazione dipendenze
Se non e gia installata:

```bash
.venv/bin/pip install zeep
```

## Input atteso
- File testo/tsv con un PMID per riga.
- Default: `failed_retry_v3.tsv`

Esempio:

```text
10048327
10052460
10089398
```

## Come funziona
Per ogni PMID lo script:

1. Esegue `searchPublications` con query:
   - `EXT_ID:<PMID> SRC:MED`
2. Estrae metadati utili (`pmcid`, `inPMC`, `isOpenAccess`, ecc.).
3. Costruisce candidati `id/source` per `getFulltextXML` (principalmente con `source=PMC`).
4. Chiama `getFulltextXML` e prova a estrarre XML da:
   - attachment SOAP (`MessagePack`, `Attachment.content`)
   - campi inline (`fullTextXML`, `fullText`) se presenti
5. Se trova XML:
   - salva `output_dir/<PMID>.xml`
   - scrive il PMID nel file successi
6. Se non trova XML:
   - scrive il PMID nel file falliti

## Parametri CLI

```bash
.venv/bin/python Europe_PMC_downloader.py [opzioni]
```

Opzioni principali:
- `--wsdl` URL WSDL (default Europe PMC)
- `--pmid-file` file input PMID (default `failed_retry_v3.tsv`)
- `--output-dir` cartella output XML (default `missing_xml`)
- `--success-file` file PMID scaricati (default `downloaded_xml_pmids.tsv`)
- `--failed-file` file PMID non scaricati (default `failed_xml_pmids.tsv`)
- `--limit` limita il numero di PMID da processare (0 = tutti)
- `--sleep` pausa tra PMID in secondi
- `--timeout` timeout SOAP in secondi
- `--progress-every` stampa progress ogni N record
- `--verbose` log dettagliato record per record

## Esempi d'uso

### Test rapido su pochi record
```bash
.venv/bin/python Europe_PMC_downloader.py \
  --limit 50 \
  --timeout 5 \
  --sleep 0 \
  --progress-every 10 \
  --output-dir missing_xml_test
```

### Run completo
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

## Output prodotti
- Cartella XML: `missing_xml/`
  - un file per PMID: `<PMID>.xml`
- Report successo: `downloaded_xml_pmids.tsv`
- Report fallimento: `failed_xml_pmids.tsv`

## Comportamento resiliente
- Scrittura incrementale dei report (flush ad ogni riga).
- Se un XML esiste gia (`<PMID>.xml` non vuoto), viene saltato come gia scaricato.
- In caso di interruzione, il lavoro gia scritto su disco resta disponibile.

## Limiti importanti
- Europe PMC SOAP `getFulltextXML` e disponibile solo per il sottoinsieme full-text OA/PMC.
- Molti PMID possono non avere XML disponibile, quindi e normale avere un numero di fallimenti elevato.
- Alcune risposte SOAP arrivano come attachment e non come testo inline; lo script gestisce entrambi i casi.

## Troubleshooting

### Processo fermo/lento
- Riduci `--timeout` (es. 5 secondi)
- Mantieni `--sleep 0`
- Usa `--progress-every` basso per monitorare meglio

### Nessun XML scaricato
- Verifica con un PMID noto OA/PMC (es. un record con `HAS_FT:Y` via search)
- Controlla connettivita verso endpoint Europe PMC

### Interruzione con codice 143
- Indica terminazione del processo (signal).
- I file gia scritti restano validi; puoi rilanciare il comando.

