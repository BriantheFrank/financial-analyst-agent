import argparse
import datetime as dt
import gzip
import json
import logging
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
    def __init__(self, user_agent: str, cache_dir: str = ".cache/sec", rate_limit_per_sec: float = 3.0, timeout: int = 30):
        if not user_agent:
            raise ValueError("SEC_USER_AGENT must be set")
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = 1.0 / max(rate_limit_per_sec, 0.1)
        self.timeout = timeout
        self._last_request_ts = 0.0

    def _throttle(self) -> None:
        now = time.time()
        delta = now - self._last_request_ts
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last_request_ts = time.time()

    def _cache_path(self, url: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", url)
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
            return self._decode_response_bytes(body, resp.headers.get("Content-Encoding"), context=f"url={url}")

    def get(self, url: str, use_cache: bool = True) -> bytes:
        cp = self._cache_path(url)
        if use_cache and cp.exists():
            return self._decode_response_bytes(cp.read_bytes(), content_encoding=None, context=f"cache={cp}")
        data = self._http_get(url)
        cp.write_bytes(data)
        return data

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


def _find_instance_doc(client: SecClient, cik: str, accession: str) -> Optional[str]:
    acc = accession.replace("-", "")
    try:
        idx = client.get_json(f"{SEC_BASE}/Archives/edgar/data/{int(cik)}/{acc}/index.json")
    except Exception:
        return None
    names = [x.get("name") for x in idx.get("directory", {}).get("item", []) if x.get("name")]
    xmls = [n for n in names if n.endswith(".xml") and not re.search(r"_(cal|def|lab|pre)\.xml$", n)]
    if not xmls:
        return None
    chosen = sorted(xmls, key=lambda n: ("htm.xml" not in n, len(n)))[0]
    return f"{SEC_BASE}/Archives/edgar/data/{int(cik)}/{acc}/{chosen}"


def extract_segment_metrics(client: SecClient, cik: str, filing: Filing) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, str]]]:
    instance = _find_instance_doc(client, cik, filing.accession)
    if not instance:
        return {"revenue_by_segment": [], "profit_by_segment": [], "capex_by_segment": []}, [{"field": "segment_metrics", "reason": "XBRL instance XML not found for filing."}]

    root = ET.fromstring(client.get_text(instance))
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


def build_financials(company_input: str, years: int, user_agent: str, cache_dir: str = ".cache/sec") -> Dict[str, Any]:
    client = SecClient(user_agent=user_agent, cache_dir=cache_dir)
    company = resolve_company(client, company_input)
    filings = collect_filings(get_submissions(client, company["cik"]), years)
    companyfacts = get_companyfacts(client, company["cik"])
    periods = []
    for f in filings:
        primary, notes, missing = extract_primary_metrics(companyfacts, f)
        seg, seg_missing = extract_segment_metrics(client, company["cik"], f)
        fc, fc_missing = extract_forecasted_capex(client, company["cik"], f)
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
    return {
        "company": {"input": company_input, "cik": company["cik"], "name": company["name"], "ticker": company["ticker"]},
        "generated_at_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "periods": periods,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--user-agent", default=None)
    ap.add_argument("--cache-dir", default=".cache/sec")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ua = args.user_agent or __import__("os").environ.get("SEC_USER_AGENT")
    out = build_financials(args.company, args.years, ua, cache_dir=args.cache_dir)
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
