import argparse
import datetime as dt
import gzip
import json
import logging
import shutil
import re
import time
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

LOGGER = logging.getLogger(__name__)
SEC_BASE = "https://www.sec.gov"
DATA_BASE = "https://data.sec.gov"


@dataclass
class Filing:
    form: str
    filing_date: str
    report_date: Optional[str]
    accession: str
    primary_doc: str
    fy: Optional[int]
    fp: Optional[str]


class SecClient:
    def __init__(
        self,
        user_agent: str,
        cache_dir: str = ".cache/sec",
        rate_limit_per_sec: float = 3.0,
        timeout: int = 30,
        max_file_size_mb: float = 25.0,
        max_total_download_mb: float = 200.0,
    ):
        if not user_agent:
            raise ValueError("SEC_USER_AGENT must be set")
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = 1.0 / max(rate_limit_per_sec, 0.1)
        self.timeout = timeout
        self._last_request_ts = 0.0
        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)
        self.max_total_download_bytes = int(max_total_download_mb * 1024 * 1024)
        self.total_downloaded_bytes = 0
        self.request_count = 0
        self.downloaded_artifacts: Dict[str, List[str]] = {}

    def _throttle(self) -> None:
        now = time.time()
        delta = now - self._last_request_ts
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last_request_ts = time.time()

    def _cache_path(self, url: str) -> Path:
        cik = _extract_cik_from_url(url)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", url)
        if cik:
            p = self.cache_dir / cik
            p.mkdir(parents=True, exist_ok=True)
            return p / safe
        return self.cache_dir / safe

    def _decode_response_bytes(self, data: bytes, content_encoding: Optional[str], context: str) -> bytes:
        encoding = (content_encoding or "").strip().lower()
        try:
            if encoding == "gzip":
                return gzip.decompress(data)
            if encoding == "deflate":
                try:
                    return zlib.decompress(data)
                except zlib.error:
                    return zlib.decompress(data, -zlib.MAX_WBITS)
            if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
                return gzip.decompress(data)
            return data
        except (OSError, EOFError, zlib.error) as exc:
            raise RuntimeError(
                f"Failed to decompress SEC response for {context}. Content-Encoding={encoding or 'none'}"
            ) from exc

    def _http_get(self, url: str) -> bytes:
        self._throttle()
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read()
            data = self._decode_response_bytes(body, resp.headers.get("Content-Encoding"), context=f"url={url}")
            size = len(data)
            if size > self.max_file_size_bytes:
                raise RuntimeError(
                    f"SEC artifact too large ({size:,} bytes) for {url}. "
                    f"Per-file cap is {self.max_file_size_bytes:,} bytes. "
                    "Reduce scope or increase max_file_size_mb."
                )
            if self.total_downloaded_bytes + size > self.max_total_download_bytes:
                raise RuntimeError(
                    f"SEC download cap exceeded at {self.total_downloaded_bytes + size:,} bytes. "
                    f"Run cap is {self.max_total_download_bytes:,} bytes. "
                    "Reduce scope (segments_mode/max_quarters) or increase max_total_download_mb."
                )
            self.total_downloaded_bytes += size
            self.request_count += 1
            return data

    def get(self, url: str, use_cache: bool = True) -> bytes:
        cp = self._cache_path(url)
        if use_cache and cp.exists():
            return self._decode_response_bytes(cp.read_bytes(), content_encoding=None, context=f"cache={cp}")
        data = self._http_get(url)
        cp.write_bytes(data)
        return data

    def record_artifact(self, filing_accession: str, artifact_name: str) -> None:
        self.downloaded_artifacts.setdefault(filing_accession, []).append(artifact_name)

    def print_download_summary(self) -> None:
        print(
            f"Download summary: bytes={self.total_downloaded_bytes:,}, requests={self.request_count}"
        )
        for accession, artifacts in sorted(self.downloaded_artifacts.items()):
            print(f"  {accession}: {', '.join(sorted(set(artifacts)))}")

    def get_json(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        raw = self.get(url, use_cache=use_cache)
        text = raw.decode("utf-8")
        return json.loads(text)

    def get_text(self, url: str, use_cache: bool = True) -> str:
        return self.get(url, use_cache=use_cache).decode("utf-8")


def load_ticker_mapping(client: SecClient) -> List[Dict[str, Any]]:
    data = client.get_json(f"{SEC_BASE}/files/company_tickers.json")
    return [{"cik": str(v["cik_str"]).zfill(10), "ticker": v["ticker"], "name": v["title"]} for v in data.values()]


def resolve_company(client: SecClient, company_input: str) -> Dict[str, str]:
    rows = load_ticker_mapping(client)
    exact = [r for r in rows if r["ticker"].upper() == company_input.upper()]
    if exact:
        return exact[0]

    low = company_input.lower().strip()
    candidates = [r for r in rows if low in r["name"].lower()]
    candidates = sorted(candidates, key=lambda r: r["name"])[:5]
    if not candidates:
        raise ValueError(f"Could not resolve company input: {company_input}")
    print("Could not find exact ticker. Choose one candidate by number:")
    for i, c in enumerate(candidates, start=1):
        print(f"{i}. {c['name']} ({c['ticker']}) CIK {c['cik']}")
    choice = input("Enter number: ").strip()
    idx = int(choice) - 1
    if idx < 0 or idx >= len(candidates):
        raise ValueError("Invalid selection")
    return candidates[idx]


def get_submissions(client: SecClient, cik: str) -> Dict[str, Any]:
    return client.get_json(f"{DATA_BASE}/submissions/CIK{cik}.json")


def collect_filings(submissions: Dict[str, Any], years: int = 5) -> List[Filing]:
    recent = submissions.get("filings", {}).get("recent", {})
    current_year = dt.datetime.utcnow().year
    min_year = current_year - years
    out = []
    for i, form in enumerate(recent.get("form", [])):
        if form not in {"10-K", "10-Q"}:
            continue
        filing_date = recent["filingDate"][i]
        fy = recent.get("fy", [None] * 9999)[i]
        if int(filing_date[:4]) < min_year and (fy is not None and fy < min_year):
            continue
        out.append(Filing(
            form=form,
            filing_date=filing_date,
            report_date=recent.get("reportDate", [None] * 9999)[i],
            accession=recent["accessionNumber"][i],
            primary_doc=recent["primaryDocument"][i],
            fy=fy,
            fp=recent.get("fp", [None] * 9999)[i],
        ))
    out.sort(key=lambda f: (f.report_date or f.filing_date, f.form))
    return out


def limit_filings_scope(filings: List[Filing], max_quarters: int = 8) -> List[Filing]:
    annuals = [f for f in filings if f.form == "10-K"]
    quarters = [f for f in filings if f.form == "10-Q"]
    quarters.sort(key=lambda f: (f.report_date or f.filing_date), reverse=True)
    scoped = annuals + quarters[:max_quarters]
    scoped.sort(key=lambda f: (f.report_date or f.filing_date, f.form))
    return scoped


def get_companyfacts(client: SecClient, cik: str) -> Dict[str, Any]:
    return client.get_json(f"{DATA_BASE}/api/xbrl/companyfacts/CIK{cik}.json")


def _duration_days(f: Dict[str, Any]) -> Optional[int]:
    if not f.get("start") or not f.get("end"):
        return None
    return (dt.date.fromisoformat(f["end"]) - dt.date.fromisoformat(f["start"])).days


def _select_fact_for_filing(facts: List[Dict[str, Any]], filing: Filing) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    notes = []
    cands = [f for f in facts if f.get("accn") == filing.accession]
    if not cands and filing.report_date:
        cands = [f for f in facts if f.get("end") == filing.report_date and f.get("form") == filing.form]
    if not cands:
        return None, notes
    if filing.form == "10-Q":
        quarter = [f for f in cands if (_duration_days(f) or 999) <= 105]
        if quarter:
            cands = quarter
        else:
            notes.append("Quarter appears YTD; no safe quarter-only conversion available.")
    cands.sort(key=lambda f: (_duration_days(f) or 9999, f.get("end", "")))
    return cands[0], notes


def extract_primary_metrics(companyfacts: Dict[str, Any], filing: Filing) -> Tuple[Dict[str, Any], List[str], List[Dict[str, str]]]:
    facts = companyfacts.get("facts", {}).get("us-gaap", {})
    notes, missing = [], []

    def metric(name: str, tags: List[str], capex_def: Optional[str] = None):
        for tag in tags:
            entries = facts.get(tag, {}).get("units", {}).get("USD", [])
            fact, ns = _select_fact_for_filing(entries, filing)
            notes.extend(ns)
            if fact and fact.get("val") is not None:
                out = {
                    "value": float(fact["val"]), "unit": "USD", "xbrl_tag": tag,
                    "source": "xbrl", "confidence": 0.95,
                    "provenance": {
                        "filing_type": filing.form, "accession": filing.accession,
                        "filing_date": filing.filing_date, "source_ref": f"us-gaap:{tag}", "unit": "USD"
                    }
                }
                if capex_def:
                    out["capex_definition"] = capex_def
                return out
        missing.append({"field": name, "reason": f"No matching XBRL facts found for tags: {', '.join(tags)}"})
        return None

    cap = metric("capex", ["PaymentsToAcquirePropertyPlantAndEquipment"], "cash_paid_for_ppe")
    if cap is None:
        cap = metric("capex", ["CapitalExpenditures"], "capital_expenditures_fallback")
    return {
        "revenue": metric("revenue", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]),
        "profit_net_income": metric("profit_net_income", ["NetIncomeLoss"]),
        "capex": cap,
    }, notes, missing


def _is_skippable_artifact(name: str, size: int = 0, *, max_size_bytes: int) -> bool:
    low = name.lower()
    blocked_exts = (
        ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx"
    )
    if low.endswith(blocked_exts):
        return True
    if size and size > max_size_bytes:
        return True
    return False


def _choose_instance_from_index(items: List[Dict[str, Any]]) -> Optional[str]:
    candidates = []
    for it in items:
        name = it.get("name")
        if not name or not name.lower().endswith(".xml"):
            continue
        low = name.lower()
        typ = (it.get("type") or "").upper()
        if re.search(r"_(cal|def|lab|pre)\.xml$", low) or low.endswith(".xsd"):
            continue
        score = 0
        if low.endswith("_htm.xml"):
            score += 100
        if "EX-101.INS" in typ or "INSTANCE" in typ:
            score += 50
        score += int(it.get("size") or 0) // 1024
        candidates.append((score, name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _find_instance_doc(client: SecClient, cik: str, accession: str) -> Optional[str]:
    acc = accession.replace("-", "")
    try:
        idx = client.get_json(f"{SEC_BASE}/Archives/edgar/data/{int(cik)}/{acc}/index.json")
    except Exception:
        return None
    items = [x for x in idx.get("directory", {}).get("item", []) if x.get("name")]
    items = [x for x in items if not _is_skippable_artifact(x.get("name", ""), int(x.get("size") or 0), max_size_bytes=client.max_file_size_bytes)]
    chosen = _choose_instance_from_index(items)
    if not chosen:
        return None
    return f"{SEC_BASE}/Archives/edgar/data/{int(cik)}/{acc}/{chosen}"


def extract_segment_metrics(client: SecClient, cik: str, filing: Filing) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, str]]]:
    instance = _find_instance_doc(client, cik, filing.accession)
    if not instance:
        return {"revenue_by_segment": [], "profit_by_segment": [], "capex_by_segment": []}, [{"field": "segment_metrics", "reason": "XBRL instance XML not found for filing."}]

    root = ET.fromstring(client.get_text(instance))
    client.record_artifact(filing.accession, instance.rsplit("/", 1)[-1])
    ns = {
        "xbrli": "http://www.xbrl.org/2003/instance",
        "xbrldi": "http://xbrl.org/2006/xbrldi",
    }
    ctx = {}
    for c in root.findall(".//xbrli:context", ns):
        cid = c.attrib.get("id")
        members = []
        seg = c.find(".//xbrli:segment", ns)
        if seg is not None:
            for em in seg.findall(".//xbrldi:explicitMember", ns):
                members.append({"dimension": em.attrib.get("dimension", ""), "member": (em.text or "").strip()})
        end = c.findtext(".//xbrli:period/xbrli:endDate", default=None, namespaces=ns) or c.findtext(".//xbrli:period/xbrli:instant", default=None, namespaces=ns)
        ctx[cid] = {"members": members, "end": end}

    map_tags = {
        "revenue_by_segment": {"RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"},
        "profit_by_segment": {"NetIncomeLoss"},
        "capex_by_segment": {"PaymentsToAcquirePropertyPlantAndEquipment", "CapitalExpenditures"},
    }
    out = {"revenue_by_segment": [], "profit_by_segment": [], "capex_by_segment": []}
    missing = []

    for f in root.iter():
        tag = f.tag.split("}")[-1]
        ctx_ref = f.attrib.get("contextRef")
        if not ctx_ref or ctx_ref not in ctx:
            continue
        if filing.report_date and ctx[ctx_ref].get("end") and ctx[ctx_ref]["end"] != filing.report_date:
            continue
        members = ctx[ctx_ref]["members"]
        if not members:
            continue
        txt = (f.text or "").strip()
        if not re.match(r"^-?\d+(\.\d+)?$", txt):
            continue
        for key, tags in map_tags.items():
            if tag not in tags:
                continue
            for mem in members:
                out[key].append({
                    "segment": mem["member"].split(":")[-1], "value": float(txt), "unit": "USD",
                    "xbrl_tag": tag, "dimension": mem["dimension"], "member": mem["member"],
                    "source": "xbrl", "confidence": 0.85,
                    "provenance": {
                        "filing_type": filing.form, "accession": filing.accession,
                        "filing_date": filing.filing_date, "source_ref": instance, "unit": "USD"
                    }
                })

    for key in out:
        if not out[key]:
            missing.append({"field": key, "reason": "No dimensional facts found in XBRL instance for this filing."})
    return out, missing


def _parse_money(text: str) -> Tuple[Optional[float], Optional[float], str]:
    scale = 1_000_000_000 if re.search(r"billion", text, re.I) else (1_000_000 if re.search(r"million", text, re.I) else 1)
    nums = re.findall(r"\$?\s*(\d+(?:\.\d+)?)", text)
    if not nums:
        return None, None, "USD"
    vals = [float(n) * scale for n in nums[:2]]
    return (vals[0], vals[0], "USD") if len(vals) == 1 else (min(vals), max(vals), "USD")


def extract_forecasted_capex(client: SecClient, cik: str, filing: Filing) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    acc = filing.accession.replace("-", "")
    url = f"{SEC_BASE}/Archives/edgar/data/{int(cik)}/{acc}/{filing.primary_doc}"
    content = re.sub(r"<[^>]+>", " ", client.get_text(url))
    sents = re.split(r"(?<=[.!?])\s+", content)
    out = []
    fwd = re.compile(r"expect|plan|anticipate|estimate|will invest|project|guidance", re.I)
    cap = re.compile(r"capital expenditures|capex", re.I)
    tm = re.compile(r"fiscal\s+\d{4}|FY\d{2,4}|next\s+(?:fiscal\s+)?year|next\s+12\s+months", re.I)
    for s in sents:
        if not cap.search(s) or not fwd.search(s):
            continue
        vmin, vmax, unit = _parse_money(s)
        if vmin is None:
            continue
        t = tm.search(s)
        out.append({
            "value_min": vmin, "value_max": vmax, "unit": unit,
            "timeframe": t.group(0) if t else "unspecified", "source": "text",
            "snippet": s.strip()[:200], "location_hint": "MD&A > Liquidity and Capital Resources",
            "confidence": 0.6,
            "provenance": {
                "filing_type": filing.form, "accession": filing.accession,
                "filing_date": filing.filing_date, "source_ref": url, "unit": unit
            }
        })
    miss = [] if out else [{"field": "forecasted_capex", "reason": "No clearly forward-looking CAPEX guidance sentence found."}]
    return out, miss


def fiscal_period_label(filing: Filing) -> str:
    if filing.form == "10-K":
        return "FY"
    return filing.fp if (filing.fp or "").upper() in {"Q1", "Q2", "Q3", "Q4"} else "Q?"


def extract_company_financials(
    company: str,
    years: int,
    user_agent: str | None,
    cache_dir: str = ".cache/sec",
    segments_mode: str = "annual",
    max_quarters: int = 8,
    max_file_size_mb: float = 25.0,
    max_total_download_mb: float = 200.0,
) -> Dict[str, Any]:
    if not user_agent:
        raise ValueError("SEC_USER_AGENT must be set")
    return build_financials(
        company,
        years,
        user_agent,
        cache_dir=cache_dir,
        segments_mode=segments_mode,
        max_quarters=max_quarters,
        max_file_size_mb=max_file_size_mb,
        max_total_download_mb=max_total_download_mb,
    )


def build_financials(
    company_input: str,
    years: int,
    user_agent: str,
    cache_dir: str = ".cache/sec",
    segments_mode: str = "annual",
    max_quarters: int = 8,
    max_file_size_mb: float = 25.0,
    max_total_download_mb: float = 200.0,
) -> Dict[str, Any]:
    if segments_mode not in {"none", "annual", "full"}:
        raise ValueError("segments_mode must be one of: none, annual, full")
    client = SecClient(
        user_agent=user_agent,
        cache_dir=cache_dir,
        max_file_size_mb=max_file_size_mb,
        max_total_download_mb=max_total_download_mb,
    )
    company = resolve_company(client, company_input)
    filings = limit_filings_scope(collect_filings(get_submissions(client, company["cik"]), years), max_quarters=max_quarters)
    companyfacts = get_companyfacts(client, company["cik"])
    periods = []
    for f in filings:
        primary, notes, missing = extract_primary_metrics(companyfacts, f)
        do_segments = segments_mode == "full" or (segments_mode == "annual" and f.form == "10-K")
        if do_segments:
            seg, seg_missing = extract_segment_metrics(client, company["cik"], f)
        else:
            seg = {"revenue_by_segment": [], "profit_by_segment": [], "capex_by_segment": []}
            seg_missing = [{"field": "segment_metrics", "reason": f"Skipped due to segments_mode={segments_mode} for form {f.form}."}]
        fc, fc_missing = [], [{"field": "forecasted_capex", "reason": "Skipped to reduce download volume; textual filing artifacts are not downloaded."}]
        end = f.report_date or f.filing_date
        periods.append({
            "fiscal_year": f.fy or int(end[:4]), "fiscal_period": fiscal_period_label(f),
            "period_start": None, "period_end": end,
            "filing": {"form": f.form, "filing_date": f.filing_date, "accession": f.accession, "primary_doc": f.primary_doc},
            "revenue": primary["revenue"], "revenue_by_segment": seg["revenue_by_segment"],
            "profit_net_income": primary["profit_net_income"], "profit_by_segment": seg["profit_by_segment"],
            "capex": primary["capex"], "capex_by_segment": seg["capex_by_segment"],
            "forecasted_capex": fc, "forecasted_capex_by_segment": [],
            "notes": sorted(set(notes)), "missing_data": missing + seg_missing + fc_missing,
        })
    periods.sort(key=lambda p: (p["fiscal_year"], p["fiscal_period"], p["period_end"]))
    client.print_download_summary()
    return {
        "company": {"input": company_input, "cik": company["cik"], "name": company["name"], "ticker": company["ticker"]},
        "generated_at_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "periods": periods,
    }


def clear_company_cache(cik: str, cache_dir: str = ".cache/sec") -> None:
    company_path = Path(cache_dir) / str(int(cik)).zfill(10)
    if company_path.exists():
        shutil.rmtree(company_path)


def prune_cache(cache_dir: str = ".cache/sec", max_age_days: int = 30, max_total_gb: float = 2.0) -> None:
    root = Path(cache_dir)
    if not root.exists():
        return
    now = time.time()
    age_cutoff = now - (max_age_days * 86400)
    files = [p for p in root.rglob("*") if p.is_file()]

    for p in files:
        if p.stat().st_mtime < age_cutoff:
            p.unlink(missing_ok=True)

    files = [p for p in root.rglob("*") if p.is_file()]
    max_total_bytes = int(max_total_gb * 1024 * 1024 * 1024)
    total = sum(p.stat().st_size for p in files)
    if total <= max_total_bytes:
        return
    files.sort(key=lambda p: p.stat().st_mtime)
    for p in files:
        if total <= max_total_bytes:
            break
        size = p.stat().st_size
        p.unlink(missing_ok=True)
        total -= size


def company_cache_size_bytes(cik: str, cache_dir: str = ".cache/sec") -> int:
    company_path = Path(cache_dir) / str(int(cik)).zfill(10)
    if not company_path.exists():
        return 0
    return sum(p.stat().st_size for p in company_path.rglob("*") if p.is_file())


def _extract_cik_from_url(url: str) -> Optional[str]:
    m = re.search(r"CIK(\d{10})\.json", url)
    if m:
        return m.group(1)
    m = re.search(r"/edgar/data/(\d+)/", url)
    if m:
        return str(int(m.group(1))).zfill(10)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--user-agent", default=None)
    ap.add_argument("--cache-dir", default=".cache/sec")
    ap.add_argument("--segments-mode", choices=["none", "annual", "full"], default="annual")
    ap.add_argument("--max-quarters", type=int, default=8)
    ap.add_argument("--max-file-size-mb", type=float, default=25.0)
    ap.add_argument("--max-total-download-mb", type=float, default=200.0)
    ap.add_argument("--clear-company-cache", default=None, help="CIK to clear in cache and exit")
    ap.add_argument("--prune-cache", action="store_true", help="Prune cache using configured policy and exit")
    ap.add_argument("--prune-max-age-days", type=int, default=30)
    ap.add_argument("--prune-max-total-gb", type=float, default=2.0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.clear_company_cache:
        clear_company_cache(args.clear_company_cache, cache_dir=args.cache_dir)
        return
    if args.prune_cache:
        prune_cache(cache_dir=args.cache_dir, max_age_days=args.prune_max_age_days, max_total_gb=args.prune_max_total_gb)
        return
    ua = args.user_agent or __import__("os").environ.get("SEC_USER_AGENT")
    out = build_financials(
        args.company,
        args.years,
        ua,
        cache_dir=args.cache_dir,
        segments_mode=args.segments_mode,
        max_quarters=args.max_quarters,
        max_file_size_mb=args.max_file_size_mb,
        max_total_download_mb=args.max_total_download_mb,
    )
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
