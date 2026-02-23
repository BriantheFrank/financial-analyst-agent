from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Tuple

import pandas as pd


TIDY_COLUMNS = [
    "period_end",
    "fiscal_year",
    "fiscal_period",
    "metric",
    "segment",
    "value",
    "unit",
    "source",
    "confidence",
]


def json_to_tidy_df(payload: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    transformations: List[str] = []
    accessions: List[str] = []

    for period in payload.get("periods", []):
        base = {
            "period_end": period.get("period_end"),
            "fiscal_year": period.get("fiscal_year"),
            "fiscal_period": period.get("fiscal_period"),
        }
        acc = period.get("filing", {}).get("accession")
        if acc:
            accessions.append(acc)

        for metric_key in ("revenue", "profit_net_income", "capex"):
            metric = period.get(metric_key)
            if metric and metric.get("value") is not None:
                rows.append(
                    {
                        **base,
                        "metric": metric_key,
                        "segment": "Total",
                        "value": metric.get("value"),
                        "unit": metric.get("unit", "USD"),
                        "source": metric.get("source"),
                        "confidence": metric.get("confidence"),
                    }
                )

        for metric_key, field in (
            ("revenue", "revenue_by_segment"),
            ("profit_net_income", "profit_by_segment"),
            ("capex", "capex_by_segment"),
        ):
            for seg in period.get(field, []) or []:
                if seg.get("value") is None:
                    continue
                rows.append(
                    {
                        **base,
                        "metric": metric_key,
                        "segment": seg.get("segment") or "Unknown",
                        "value": seg.get("value"),
                        "unit": seg.get("unit", "USD"),
                        "source": seg.get("source"),
                        "confidence": seg.get("confidence"),
                    }
                )

    if not rows:
        df = pd.DataFrame(columns=TIDY_COLUMNS)
        transformations.append("No metric rows found in payload; emitted empty tidy dataframe.")
    else:
        df = pd.DataFrame(rows)
        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
        dropped = int(df["period_end"].isna().sum())
        if dropped:
            transformations.append(f"Parsed period_end to datetime; {dropped} row(s) had invalid dates.")
        df = df.sort_values(["period_end", "metric", "segment"], kind="mergesort").reset_index(drop=True)

    company = payload.get("company", {})
    meta = {
        "company_name": company.get("name", "Unknown"),
        "ticker": company.get("ticker"),
        "cik": company.get("cik"),
        "accessions": sorted(set(accessions)),
        "as_of": payload.get("generated_at_utc") or dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "transformations": transformations,
    }
    return df, meta
