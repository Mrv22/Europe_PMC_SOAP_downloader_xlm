#!/usr/bin/env python3
"""Download full-text XML for missing PMIDs using Europe PMC SOAP.

Default input is failed_retry_v3.tsv, one PMID per line.
The script attempts:
1) getFulltextXML(id=<PMID>, source='MED')
2) searchPublications to resolve PMCID
3) getFulltextXML(id=<PMCID>, source='PMC')
4) getFulltextXML(id=<PMCID numeric>, source='PMC')

Examples:
  python download_missing_xml.py
  python download_missing_xml.py --limit 50 --verbose
  python download_missing_xml.py --pmid-file failed_retry_v3.tsv --output-dir missing_xml
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from zeep import Client
from zeep.transports import Transport
from zeep.exceptions import Fault

DEFAULT_WSDL = "https://www.ebi.ac.uk/europepmc/webservices/soap?wsdl"
DEFAULT_SOAP_ADDRESS = "https://www.ebi.ac.uk/europepmc/webservices/soap"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download Europe PMC XML for missing PMIDs")
    parser.add_argument("--wsdl", default=DEFAULT_WSDL, help="WSDL URL")
    parser.add_argument(
        "--pmid-file",
        default="failed_retry_v3.tsv",
        help="Input TSV/TXT with one PMID per line",
    )
    parser.add_argument(
        "--output-dir",
        default="missing_xml",
        help="Directory where XML files are saved",
    )
    parser.add_argument(
        "--success-file",
        default="downloaded_xml_pmids.tsv",
        help="Output file listing PMIDs with downloaded XML",
    )
    parser.add_argument(
        "--failed-file",
        default="failed_xml_pmids.tsv",
        help="Output file listing PMIDs still missing XML",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of PMIDs to process (0 = all)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Delay in seconds between PMIDs",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="SOAP request timeout in seconds",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="Print progress every N PMIDs even without --verbose",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logs")
    return parser


def build_service_proxy(wsdl_url: str, timeout: float):
    transport = Transport(timeout=timeout, operation_timeout=timeout)
    client = Client(wsdl=wsdl_url, transport=transport)
    binding_name = next(iter(client.wsdl.bindings.keys()))
    return client.create_service(binding_name, DEFAULT_SOAP_ADDRESS)


def read_pmids(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def get_first_result(response: Any) -> Any | None:
    result_list = getattr(response, "__values__", {}).get("resultList") if response is not None else None
    if result_list is None:
        return None

    results = getattr(result_list, "__values__", {}).get("result") or []
    return results[0] if results else None


def extract_fulltext_xml(soap_result: Any) -> str | None:
    if soap_result is None:
        return None

    attachments = getattr(soap_result, "attachments", None)
    if attachments:
        for attachment in attachments:
            content_type = getattr(attachment, "content_type", "") or ""
            content = getattr(attachment, "content", None)
            if isinstance(content, bytes) and content:
                if "xml" in content_type.lower() or content.lstrip().startswith(b"<"):
                    return content.decode("utf-8", errors="replace")

    values = getattr(soap_result, "__values__", {})
    xml_payload = values.get("fullTextXML")
    if isinstance(xml_payload, str) and xml_payload.strip():
        return xml_payload

    full_text = values.get("fullText")
    if isinstance(full_text, str) and full_text.strip():
        return full_text

    return None


def search_publication(service_proxy: Any, pmid: str) -> Any | None:
    response = service_proxy.searchPublications(
        queryString=f"EXT_ID:{pmid} SRC:MED",
        resultType="core",
        cursorMark="*",
        pageSize="1",
    )
    return get_first_result(response)


def try_get_xml(service_proxy: Any, item_id: str, source: str) -> str | None:
    try:
        result = service_proxy.getFulltextXML(id=item_id, source=source)
    except Fault:
        return None
    return extract_fulltext_xml(result)


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() in {"Y", "YES", "TRUE", "1"}
    return False


def process_pmid(service_proxy: Any, pmid: str, verbose: bool = False) -> tuple[bool, str, str | None]:
    # Resolve metadata first and only try sensible getFulltextXML candidates.
    first_result = None
    try:
        first_result = search_publication(service_proxy, pmid)
    except Fault:
        first_result = None

    if first_result is None:
        if verbose:
            print(f"[MISS] PMID {pmid} (no search result)")
        return False, "NO_RESULT", None

    values = getattr(first_result, "__values__", {})
    source = (values.get("source") or "").strip()
    item_id = (values.get("id") or pmid).strip()
    pmcid = (values.get("pmcid") or "").strip()
    has_fulltext_xml = _truthy_flag(values.get("hasFullTextXML"))
    in_pmc = _truthy_flag(values.get("inPMC"))
    is_open_access = _truthy_flag(values.get("isOpenAccess"))

    candidates: list[tuple[str, str, str]] = []

    if pmcid:
        candidates.append((pmcid, "PMC", f"PMC:{pmcid}"))
        if pmcid.upper().startswith("PMC") and len(pmcid) > 3:
            candidates.append((pmcid[3:], "PMC", f"PMC:{pmcid[3:]}"))

    if has_fulltext_xml and source == "PMC":
        candidates.append((item_id, "PMC", f"PMC:{item_id}"))

    if is_open_access and not pmcid:
        candidates.append((item_id, "PMC", f"PMC:{item_id}"))

    seen: set[tuple[str, str]] = set()
    deduped_candidates: list[tuple[str, str, str]] = []
    for candidate_id, candidate_source, label in candidates:
        key = (candidate_id, candidate_source)
        if key in seen:
            continue
        seen.add(key)
        deduped_candidates.append((candidate_id, candidate_source, label))

    for candidate_id, candidate_source, label in deduped_candidates:
        xml_payload = try_get_xml(service_proxy, candidate_id, candidate_source)
        if xml_payload:
            return True, label, xml_payload

    if verbose:
        details = (
            f" (source={source or 'NA'}, pmcid={pmcid or 'NA'}, "
            f"hasFullTextXML={values.get('hasFullTextXML')}, isOpenAccess={values.get('isOpenAccess')})"
        )
        print(f"[MISS] PMID {pmid}{details}")

    return False, "NO_XML", None


def main() -> int:
    args = build_parser().parse_args()

    pmid_file = Path(args.pmid_file)
    output_dir = Path(args.output_dir)
    success_file = Path(args.success_file)
    failed_file = Path(args.failed_file)

    if not pmid_file.exists():
        print(f"Input file not found: {pmid_file}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    pmids = read_pmids(pmid_file)
    if args.limit and args.limit > 0:
        pmids = pmids[: args.limit]

    if not pmids:
        print("No PMIDs to process.")
        return 0

    service_proxy = build_service_proxy(args.wsdl, timeout=args.timeout)

    ok_count = 0
    failed_count = 0

    start = time.time()
    total = len(pmids)

    success_handle = success_file.open("w", encoding="utf-8")
    failed_handle = failed_file.open("w", encoding="utf-8")

    try:
        for index, pmid in enumerate(pmids, start=1):
            try:
                xml_path = output_dir / f"{pmid}.xml"
                if xml_path.exists() and xml_path.stat().st_size > 0:
                    ok_count += 1
                    success_handle.write(f"{pmid}\n")
                    success_handle.flush()
                    if args.verbose:
                        print(f"[SKIP] {index}/{total} PMID {pmid} already downloaded")
                    continue

                ok, source_used, xml_payload = process_pmid(service_proxy, pmid, verbose=args.verbose)
                if ok and xml_payload is not None:
                    xml_path.write_text(xml_payload, encoding="utf-8")
                    ok_count += 1
                    success_handle.write(f"{pmid}\n")
                    success_handle.flush()
                    if args.verbose:
                        print(f"[OK] {index}/{total} PMID {pmid} -> {xml_path} ({source_used})")
                else:
                    failed_count += 1
                    failed_handle.write(f"{pmid}\n")
                    failed_handle.flush()
                    if args.verbose:
                        print(f"[FAIL] {index}/{total} PMID {pmid}")
            except Exception as exc:
                failed_count += 1
                failed_handle.write(f"{pmid}\n")
                failed_handle.flush()
                if args.verbose:
                    print(f"[ERR] {index}/{total} PMID {pmid}: {exc}")

            if not args.verbose and args.progress_every > 0 and index % args.progress_every == 0:
                print(
                    f"Progress: {index}/{total} processed | XML: {ok_count} | Missing: {failed_count}",
                    flush=True,
                )

            if args.sleep > 0:
                time.sleep(args.sleep)
    finally:
        success_handle.close()
        failed_handle.close()

    elapsed = time.time() - start
    print("Done")
    print(f"Total processed: {total}")
    print(f"XML downloaded: {ok_count}")
    print(f"Still missing XML: {failed_count}")
    print(f"Elapsed seconds: {elapsed:.1f}")
    print(f"XML directory: {output_dir}")
    print(f"Success list: {success_file}")
    print(f"Failure list: {failed_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
