from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Literal, Tuple

import pandas as pd


TIDY_COLUMNS = [
    "period_end",
    "period_type",
    "period_label",
    "fiscal_year",
    "fiscal_period",
    "fiscal_period_raw",
    "fiscal_period_norm",
    "metric",
    "segment",
    "value",
    "unit",
    "source",
    "confidence",
]


def normalize_fiscal_period(fiscal_period: Any) -> str:
    period = str(fiscal_period or "").strip().upper()
    compact = period.replace(" ", "").replace("-", "")
    if not compact:
        return ""
    if compact.startswith("FY") or compact in {"Y", "ANNUAL", "YEAR"}:
        return "FY"

    q_aliases = {
        "Q1": {"Q1", "Q01", "QTR1", "QUARTER1", "1"},
        "Q2": {"Q2", "Q02", "QTR2", "QUARTER2", "2"},
        "Q3": {"Q3", "Q03", "QTR3", "QUARTER3", "3"},
        "Q4": {"Q4", "Q04", "QTR4", "QUARTER4", "4"},
    }
    for normalized, aliases in q_aliases.items():
        if compact in aliases:
            return normalized
    return compact


def _normalize_period_type(fiscal_period_norm: Any) -> str:
    if fiscal_period_norm == "FY":
        return "annual"
    if fiscal_period_norm in {"Q1", "Q2", "Q3", "Q4"}:
        return "quarterly"
    return "unknown"


def _period_label(fiscal_year: Any, fiscal_period: Any) -> str:
    fy = str(fiscal_year) if fiscal_year is not None else "Unknown"
    fp = normalize_fiscal_period(fiscal_period)
    if fp == "FY":
        return f"FY{fy}"
    if fp in {"Q1", "Q2", "Q3", "Q4"}:
        return f"{fy} {fp}"
    return f"{fy} {fp}".strip()


def filter_df_by_granularity(df: pd.DataFrame, granularity: Literal["quarterly", "annual"]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    if "fiscal_period_norm" in df.columns:
        if granularity == "annual":
            return df[df["fiscal_period_norm"] == "FY"].copy()
        return df[df["fiscal_period_norm"].isin(["Q1", "Q2", "Q3", "Q4"])].copy()
    if "period_type" not in df.columns:
        return df.copy()
    return df[df["period_type"] == granularity].copy()


def json_to_tidy_df(payload: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    transformations: List[str] = []
    accessions: List[str] = []

    for period in payload.get("periods", []):
        fiscal_period_raw = period.get("fiscal_period")
        fiscal_period_norm = normalize_fiscal_period(fiscal_period_raw)
        base = {
            "period_end": period.get("period_end"),
            "period_type": _normalize_period_type(fiscal_period_norm),
            "period_label": _period_label(period.get("fiscal_year"), fiscal_period_raw),
            "fiscal_year": period.get("fiscal_year"),
            "fiscal_period": fiscal_period_norm,
            "fiscal_period_raw": fiscal_period_raw,
            "fiscal_period_norm": fiscal_period_norm,
        }
        acc = period.get("filing", {}).get("accession")
        if acc:
            accessions.append(acc)

        for metric_key in ("revenue", "profit_net_income", "capex"):
            metric = period.get(metric_key)
            if metric:
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
        missing_data_summary: Dict[str, int] = {}
    else:
        df = pd.DataFrame(rows)
        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
        invalid_period_end = int(df["period_end"].isna().sum())
        missing_metric = int(df["metric"].isna().sum())
        if invalid_period_end:
            transformations.append(f"Parsed period_end to datetime; {invalid_period_end} row(s) had invalid dates and were dropped.")
        if missing_metric:
            transformations.append(f"Found {missing_metric} row(s) missing metric and dropped them.")
        df = df[df["period_end"].notna() & df["metric"].notna()].copy()
        missing_data_summary = {
            str(metric): int(group["value"].isna().sum())
            for metric, group in df.groupby("metric", dropna=False)
        }
        df = df.sort_values(["period_end", "metric", "segment"], kind="mergesort").reset_index(drop=True)

    company = payload.get("company", {})
    meta = {
        "company_name": company.get("name", "Unknown"),
        "ticker": company.get("ticker"),
        "cik": company.get("cik"),
        "accessions": sorted(set(accessions)),
        "as_of": payload.get("generated_at_utc") or dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "transformations": transformations,
        "missing_data_summary": missing_data_summary,
    }
    return df, meta
