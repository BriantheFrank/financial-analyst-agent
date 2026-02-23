from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from templates.house_style import PALETTE, RC_PARAMS

CHART_ORDER = [
    ("01_kpi_dashboard", "kpi_dashboard"),
    ("02_revenue_trend", "revenue_trend"),
    ("03_revenue_by_segment", "revenue_by_segment"),
    ("04_profit_and_margin", "profit_and_margin"),
    ("05_capex_trend", "capex_trend"),
    ("06_capex_intensity", "capex_intensity"),
    ("07_snapshot_revenue_mix_latest_q", "snapshot_revenue_mix"),
    ("08_waterfall_revenue_yoy_change", "waterfall_revenue_yoy"),
    ("09_forecast_capex", "forecast_capex"),
    ("10_data_coverage", "data_coverage"),
]


@dataclass
class ChartResult:
    name: str
    generated: bool
    reason: str
    files: List[str]


def _stable_color(segment: str) -> str:
    digest = hashlib.md5(segment.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(PALETTE)
    return PALETTE[idx]


def _format_currency_axis(values: pd.Series) -> Tuple[float, str]:
    peak = float(values.abs().max()) if len(values) else 0.0
    if peak >= 1_000_000_000:
        return 1_000_000_000.0, "$B"
    if peak >= 1_000_000:
        return 1_000_000.0, "$M"
    return 1.0, "$"


def _title_subtitle(company: str, periods: Sequence[str], extra: str = "") -> Tuple[str, str]:
    coverage = f"{periods[0]} to {periods[-1]}" if periods else "No period coverage"
    subtitle = f"{company} | {coverage}"
    if extra:
        subtitle = f"{subtitle} | {extra}"
    return company, subtitle


class ReportGenerator:
    def __init__(self, payload: Dict[str, Any], outdir: Path, formats: Sequence[str]):
        plt.rcParams.update(RC_PARAMS)
        self.payload = payload
        self.outdir = outdir
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.formats = tuple(formats)
        self.company = payload.get("company", {}).get("name", "Unknown")
        self.tidy = self._to_tidy(payload)
        self.periods = sorted(self.tidy["period_end"].dropna().astype(str).unique().tolist())
        self.accessions = sorted({p.get("filing", {}).get("accession") for p in payload.get("periods", []) if p.get("filing", {}).get("accession")})

    def _to_tidy(self, payload: Dict[str, Any]) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        for period in payload.get("periods", []):
            base = {
                "period_end": period.get("period_end"),
                "fiscal_year": period.get("fiscal_year"),
                "fiscal_period": period.get("fiscal_period"),
            }
            for metric_key in ("revenue", "profit_net_income", "capex"):
                metric = period.get(metric_key)
                if metric:
                    rows.append({
                        **base,
                        "metric": metric_key,
                        "segment": "Total",
                        "value": metric.get("value"),
                        "unit": metric.get("unit", "USD"),
                        "source": metric.get("source"),
                        "confidence": metric.get("confidence"),
                    })
            for metric_key, field in (
                ("revenue", "revenue_by_segment"),
                ("profit_net_income", "profit_by_segment"),
                ("capex", "capex_by_segment"),
            ):
                for seg in period.get(field, []):
                    rows.append({
                        **base,
                        "metric": metric_key,
                        "segment": seg.get("segment"),
                        "value": seg.get("value"),
                        "unit": seg.get("unit", "USD"),
                        "source": seg.get("source"),
                        "confidence": seg.get("confidence"),
                    })
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=["period_end", "fiscal_year", "fiscal_period", "metric", "segment", "value", "unit", "source", "confidence"])
        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
        df = df.sort_values(["period_end", "metric", "segment"]).reset_index(drop=True)
        return df

    def generate(self) -> List[ChartResult]:
        results: List[ChartResult] = []
        for file_stub, method in CHART_ORDER:
            fn = getattr(self, f"_{method}")
            result = fn(file_stub)
            results.append(result)
        return results

    def _finalize(self, fig: plt.Figure, title: str, subtitle: str, unit: str, file_stub: str, footnote_extra: str = "") -> List[str]:
        fig.suptitle(title, x=0.01, y=0.98, ha="left", fontweight="bold")
        fig.text(0.01, 0.94, subtitle, fontsize=9)
        footnote = f"Units: {unit} | Source: SEC filings (XBRL) | Accessions: {', '.join(self.accessions) if self.accessions else 'N/A'}"
        if footnote_extra:
            footnote = f"{footnote} | {footnote_extra}"
        fig.text(0.01, 0.01, footnote, fontsize=7, color="#444444")
        files = []
        if "png" in self.formats:
            path = self.outdir / f"{file_stub}.png"
            fig.savefig(path, bbox_inches="tight")
            files.append(path.name)
        plt.close(fig)
        return files

    def _write_html(self, file_stub: str, fig: go.Figure) -> List[str]:
        if "html" not in self.formats:
            return []
        path = self.outdir / f"{file_stub}.html"
        fig.write_html(str(path), include_plotlyjs="cdn")
        return [path.name]

    def _metric_total(self, metric: str) -> pd.DataFrame:
        df = self.tidy[(self.tidy["metric"] == metric) & (self.tidy["segment"] == "Total")].copy()
        return df.sort_values("period_end")

    def _metric_segments(self, metric: str) -> pd.DataFrame:
        df = self.tidy[(self.tidy["metric"] == metric) & (self.tidy["segment"] != "Total")].copy()
        return df.sort_values(["period_end", "segment"])

    def _kpi_dashboard(self, file_stub: str) -> ChartResult:
        rev = self._metric_total("revenue")
        prof = self._metric_total("profit_net_income")
        capex = self._metric_total("capex")
        seg = self._metric_segments("revenue")
        if rev.empty and prof.empty and capex.empty:
            return ChartResult(file_stub, False, "No KPI data available.", [])

        fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
        axes = axes.flatten()

        if not rev.empty:
            scale, unit = _format_currency_axis(rev["value"])
            revy = rev.sort_values("period_end")
            revy["yoy"] = revy["value"].pct_change(4) * 100
            axes[0].plot(revy["period_end"], revy["value"] / scale, marker="o", color="#1f77b4")
            ax2 = axes[0].twinx()
            ax2.plot(revy["period_end"], revy["yoy"], color="#d62728", linestyle="--")
            axes[0].set_title(f"Revenue ({unit}) + YoY %")
            ax2.set_ylabel("YoY %")
        else:
            axes[0].text(0.5, 0.5, "Data unavailable", ha="center")

        if not prof.empty and not rev.empty:
            merged = prof[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_p", "_r"))
            scale, unit = _format_currency_axis(merged["value_p"])
            axes[1].bar(merged["period_end"], merged["value_p"] / scale, color="#2ca02c")
            m = merged["value_p"] / merged["value_r"] * 100
            ax2 = axes[1].twinx()
            ax2.plot(merged["period_end"], m, color="#ff7f0e", marker="o")
            axes[1].set_title(f"Net Income ({unit}) + Margin %")
            ax2.set_ylabel("Margin %")
        else:
            axes[1].text(0.5, 0.5, "Data unavailable", ha="center")

        if not capex.empty and not rev.empty:
            merged = capex[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_c", "_r"))
            scale, unit = _format_currency_axis(merged["value_c"])
            axes[2].bar(merged["period_end"], merged["value_c"] / scale, color="#9467bd")
            ax2 = axes[2].twinx()
            ax2.plot(merged["period_end"], merged["value_c"] / merged["value_r"] * 100, color="#8c564b")
            axes[2].set_title(f"CAPEX ({unit}) + Intensity %")
            ax2.set_ylabel("CAPEX/Revenue %")
        else:
            axes[2].text(0.5, 0.5, "Data unavailable", ha="center")

        if not seg.empty:
            latest = seg[seg["period_end"] == seg["period_end"].max()].copy()
            latest = latest.sort_values("value", ascending=False)
            axes[3].barh(latest["segment"], latest["value"], color=[_stable_color(s) for s in latest["segment"]])
            axes[3].set_title("Latest Quarter Revenue Mix")
        else:
            axes[3].text(0.5, 0.5, "Data unavailable", ha="center")

        for ax in axes:
            ax.tick_params(axis="x", labelrotation=45)

        files = self._finalize(fig, "KPI Dashboard", f"{self.company} | Snapshot and trend diagnostics", "Mixed", file_stub)
        if "html" in self.formats:
            hfig = go.Figure()
            hfig.add_annotation(text="See PNG for print-layout dashboard", showarrow=False)
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _revenue_trend(self, file_stub: str) -> ChartResult:
        rev = self._metric_total("revenue")
        if rev.empty:
            return ChartResult(file_stub, False, "Revenue unavailable.", [])
        rev = rev.sort_values("period_end")
        rev["qoq"] = rev["value"].pct_change(1) * 100
        rev["yoy"] = rev["value"].pct_change(4) * 100
        scale, unit = _format_currency_axis(rev["value"])

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8.5), gridspec_kw={"height_ratios": [2, 1]})
        ax1.plot(rev["period_end"], rev["value"] / scale, marker="o", color="#1f77b4")
        ax1.set_ylabel(unit)
        ax1.set_title("Quarterly Revenue")
        ax2.plot(rev["period_end"], rev["qoq"], label="QoQ %", color="#ff7f0e")
        ax2.plot(rev["period_end"], rev["yoy"], label="YoY %", color="#d62728")
        ax2.legend(loc="upper left")
        ax2.set_ylabel("Growth %")
        for ax in (ax1, ax2):
            ax.tick_params(axis="x", labelrotation=45)

        files = self._finalize(fig, "Revenue Trend", f"{self.company} | Quarterly trend with growth overlays", unit, file_stub)
        if "html" in self.formats:
            hfig = go.Figure()
            hfig.add_scatter(x=rev["period_end"], y=rev["value"] / scale, mode="lines+markers", name=f"Revenue ({unit})")
            hfig.add_scatter(x=rev["period_end"], y=rev["qoq"], mode="lines", name="QoQ %", yaxis="y2")
            hfig.update_layout(yaxis2=dict(overlaying="y", side="right", title="Growth %"))
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _revenue_by_segment(self, file_stub: str) -> ChartResult:
        seg = self._metric_segments("revenue")
        if seg.empty:
            return ChartResult(file_stub, False, "Revenue by segment unavailable.", [])
        pivot = seg.pivot_table(index="period_end", columns="segment", values="value", aggfunc="sum").fillna(0).sort_index()
        ordered_cols = pivot.iloc[-1].sort_values(ascending=False).index.tolist()
        pivot = pivot[ordered_cols]
        scale, unit = _format_currency_axis(pivot.max(axis=1))

        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.stackplot(pivot.index, *[pivot[c] / scale for c in pivot.columns], labels=pivot.columns, colors=[_stable_color(c) for c in pivot.columns])
        ax.set_ylabel(unit)
        ax.set_title("Revenue by Segment")
        ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5))
        ax.tick_params(axis="x", labelrotation=45)
        files = self._finalize(fig, "Revenue by Segment", f"{self.company} | Stacked segment mix over time", unit, file_stub)

        if "html" in self.formats:
            hfig = go.Figure()
            for c in pivot.columns:
                hfig.add_scatter(x=pivot.index, y=pivot[c] / scale, stackgroup="one", mode="lines", name=c, line=dict(color=_stable_color(c)))
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _profit_and_margin(self, file_stub: str) -> ChartResult:
        prof = self._metric_total("profit_net_income")
        rev = self._metric_total("revenue")
        if prof.empty:
            return ChartResult(file_stub, False, "Net income unavailable.", [])
        m = prof.merge(rev[["period_end", "value"]], on="period_end", how="left", suffixes=("_p", "_r")).sort_values("period_end")
        m["margin"] = m["value_p"] / m["value_r"] * 100
        scale, unit = _format_currency_axis(m["value_p"])
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.bar(m["period_end"], m["value_p"] / scale, color="#2ca02c")
        ax2 = ax.twinx()
        ax2.plot(m["period_end"], m["margin"], color="#d62728", marker="o")
        ax.set_ylabel(unit)
        ax2.set_ylabel("Margin %")
        ax.tick_params(axis="x", labelrotation=45)
        files = self._finalize(fig, "Net Income and Margin", f"{self.company} | Quarterly profitability", unit, file_stub)
        if "html" in self.formats:
            hfig = go.Figure()
            hfig.add_bar(x=m["period_end"], y=m["value_p"] / scale, name=f"Net income ({unit})")
            hfig.add_scatter(x=m["period_end"], y=m["margin"], yaxis="y2", name="Net margin %")
            hfig.update_layout(yaxis2=dict(overlaying="y", side="right"))
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _capex_trend(self, file_stub: str) -> ChartResult:
        cap = self._metric_total("capex")
        if cap.empty:
            return ChartResult(file_stub, False, "CAPEX unavailable.", [])
        cap = cap.sort_values("period_end")
        cap["rolling4"] = cap["value"].rolling(4, min_periods=1).mean()
        scale, unit = _format_currency_axis(cap["value"])
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.bar(cap["period_end"], cap["value"] / scale, color="#9467bd", label="CAPEX")
        ax.plot(cap["period_end"], cap["rolling4"] / scale, color="#111111", linestyle="--", label="4Q avg")
        ax.legend(loc="upper left")
        ax.set_ylabel(unit)
        ax.tick_params(axis="x", labelrotation=45)
        files = self._finalize(fig, "CAPEX Trend", f"{self.company} | Quarterly CAPEX and 4Q rolling average", unit, file_stub)
        if "html" in self.formats:
            hfig = go.Figure()
            hfig.add_bar(x=cap["period_end"], y=cap["value"] / scale, name="CAPEX")
            hfig.add_scatter(x=cap["period_end"], y=cap["rolling4"] / scale, mode="lines", name="4Q avg")
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _capex_intensity(self, file_stub: str) -> ChartResult:
        cap, rev = self._metric_total("capex"), self._metric_total("revenue")
        if cap.empty or rev.empty:
            return ChartResult(file_stub, False, "CAPEX or revenue unavailable.", [])
        m = cap[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_c", "_r")).sort_values("period_end")
        m["intensity"] = m["value_c"] / m["value_r"] * 100
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.plot(m["period_end"], m["intensity"], marker="o", color="#8c564b")
        ax.set_ylabel("%")
        ax.tick_params(axis="x", labelrotation=45)
        files = self._finalize(fig, "CAPEX Intensity", f"{self.company} | CAPEX as a percent of revenue", "%", file_stub)
        if "html" in self.formats:
            hfig = go.Figure()
            hfig.add_scatter(x=m["period_end"], y=m["intensity"], mode="lines+markers", name="CAPEX intensity %")
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _snapshot_revenue_mix(self, file_stub: str) -> ChartResult:
        seg = self._metric_segments("revenue")
        if seg.empty:
            return ChartResult(file_stub, False, "Revenue segment snapshot unavailable.", [])
        latest = seg[seg["period_end"] == seg["period_end"].max()].sort_values("value", ascending=False)
        scale, unit = _format_currency_axis(latest["value"])
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.barh(latest["segment"], latest["value"] / scale, color=[_stable_color(s) for s in latest["segment"]])
        ax.invert_yaxis()
        ax.set_xlabel(unit)
        files = self._finalize(fig, "Revenue Mix (Latest Quarter)", f"{self.company} | Segment mix ranked by size", unit, file_stub)
        if "html" in self.formats:
            hfig = go.Figure()
            hfig.add_bar(y=latest["segment"], x=latest["value"] / scale, orientation="h", marker_color=[_stable_color(s) for s in latest["segment"]])
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _waterfall_revenue_yoy(self, file_stub: str) -> ChartResult:
        seg = self._metric_segments("revenue")
        if seg.empty:
            return ChartResult(file_stub, False, "Segment history unavailable for waterfall.", [])
        latest_date = seg["period_end"].max()
        prior_date = latest_date - pd.DateOffset(years=1)
        latest = seg[seg["period_end"] == latest_date].groupby("segment")["value"].sum()
        prior = seg[seg["period_end"] == prior_date].groupby("segment")["value"].sum()
        if prior.empty:
            return ChartResult(file_stub, False, "Prior-year quarter segment data missing.", [])
        change = (latest - prior).dropna().sort_values(ascending=False)
        if change.empty:
            return ChartResult(file_stub, False, "Insufficient overlap for YoY segment bridge.", [])
        scale, unit = _format_currency_axis(change)
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.bar(change.index, change.values / scale, color=[_stable_color(s) for s in change.index])
        ax.axhline(0, color="#333333", linewidth=0.8)
        ax.set_ylabel(unit)
        ax.tick_params(axis="x", labelrotation=45)
        files = self._finalize(fig, "Revenue YoY Change Bridge", f"{self.company} | Segment contribution to YoY change", unit, file_stub)
        if "html" in self.formats:
            hfig = go.Figure()
            hfig.add_bar(x=change.index.tolist(), y=(change / scale).tolist(), marker_color=[_stable_color(s) for s in change.index])
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _forecast_capex(self, file_stub: str) -> ChartResult:
        hist = self._metric_total("capex")
        fc_rows = []
        for p in self.payload.get("periods", []):
            for f in p.get("forecasted_capex", []):
                fc_rows.append({"period_end": p.get("period_end"), **f})
        forecast = pd.DataFrame(fc_rows)
        if hist.empty or forecast.empty:
            return ChartResult(file_stub, False, "Forecast CAPEX unavailable.", [])
        hist = hist.sort_values("period_end")
        forecast["period_end"] = pd.to_datetime(forecast["period_end"], errors="coerce")
        forecast = forecast.sort_values("period_end")
        scale, unit = _format_currency_axis(pd.concat([hist["value"], forecast["value_max"]]))

        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.plot(hist["period_end"], hist["value"] / scale, color="#1f77b4", label="Historical CAPEX")
        ax.plot(forecast["period_end"], forecast["value_min"] / scale, color="#d62728", linestyle=":", label="Forecast min")
        ax.plot(forecast["period_end"], forecast["value_max"] / scale, color="#ff7f0e", linestyle=":", label="Forecast max")
        ax.fill_between(forecast["period_end"], forecast["value_min"] / scale, forecast["value_max"] / scale, color="#ff7f0e", alpha=0.2)
        ax.legend(loc="upper left")
        ax.tick_params(axis="x", labelrotation=45)
        files = self._finalize(fig, "CAPEX Forecast Band", f"{self.company} | Historical plus disclosed guidance", unit, file_stub, footnote_extra=f"Timeframes: {', '.join(sorted(set(forecast['timeframe']))) }")
        if "html" in self.formats:
            hfig = go.Figure()
            hfig.add_scatter(x=hist["period_end"], y=hist["value"] / scale, mode="lines", name="Historical")
            hfig.add_scatter(x=forecast["period_end"], y=forecast["value_max"] / scale, mode="lines", line=dict(dash="dot"), name="Forecast max")
            hfig.add_scatter(x=forecast["period_end"], y=forecast["value_min"] / scale, mode="lines", line=dict(dash="dot"), fill="tonexty", name="Forecast min")
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)

    def _data_coverage(self, file_stub: str) -> ChartResult:
        periods = pd.to_datetime(sorted({p.get("period_end") for p in self.payload.get("periods", []) if p.get("period_end")}))
        if len(periods) == 0:
            return ChartResult(file_stub, False, "No periods available for coverage chart.", [])
        metrics = ["revenue", "profit_net_income", "capex", "segment_revenue"]
        matrix = np.zeros((len(metrics), len(periods)))
        for j, dtv in enumerate(periods):
            date_mask = self.tidy["period_end"] == dtv
            matrix[0, j] = int(((self.tidy[date_mask]["metric"] == "revenue") & (self.tidy[date_mask]["segment"] == "Total")).any())
            matrix[1, j] = int(((self.tidy[date_mask]["metric"] == "profit_net_income") & (self.tidy[date_mask]["segment"] == "Total")).any())
            matrix[2, j] = int(((self.tidy[date_mask]["metric"] == "capex") & (self.tidy[date_mask]["segment"] == "Total")).any())
            matrix[3, j] = int(((self.tidy[date_mask]["metric"] == "revenue") & (self.tidy[date_mask]["segment"] != "Total")).any())

        fig, ax = plt.subplots(figsize=(11, 4.5))
        im = ax.imshow(matrix, aspect="auto", cmap="Greens", vmin=0, vmax=1)
        ax.set_yticks(range(len(metrics)))
        ax.set_yticklabels(["Revenue", "Profit", "CAPEX", "Revenue segments"])
        ax.set_xticks(range(len(periods)))
        ax.set_xticklabels([d.strftime("%Y-%m-%d") for d in periods], rotation=45, ha="right")
        fig.colorbar(im, ax=ax, ticks=[0, 1], label="Coverage")

        files = self._finalize(fig, "Data Coverage Heatmap", f"{self.company} | Missingness across reporting periods", "Binary", file_stub)
        if "html" in self.formats:
            hfig = go.Figure(data=go.Heatmap(z=matrix, x=[d.strftime("%Y-%m-%d") for d in periods], y=["Revenue", "Profit", "CAPEX", "Revenue segments"], colorscale="Greens", zmin=0, zmax=1))
            files.extend(self._write_html(file_stub, hfig))
        return ChartResult(file_stub, True, "Generated", files)


def load_payload(path: Path) -> Dict[str, Any]:
    with path.open() as fp:
        return json.load(fp)
