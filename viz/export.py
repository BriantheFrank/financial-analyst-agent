from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from zipfile import ZIP_DEFLATED, ZipFile


def export_report_pack(outdir: Path, json_payload: Dict[str, Any], figures: List[Tuple[str, Any, Dict[str, Any]]], meta: Dict[str, Any]) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    json_path = outdir / "extracted_financials.json"
    json_path.write_text(json.dumps(json_payload, indent=2, sort_keys=True), encoding="utf-8")

    missing = []
    for stem, fig, chart_meta in figures:
        html_path = outdir / f"{stem}.html"
        fig.write_html(str(html_path), include_plotlyjs="cdn")
        if chart_meta.get("created"):
            png_path = outdir / f"{stem}.png"
            try:
                fig.write_image(str(png_path), width=1400, height=900, scale=2)
            except Exception:
                missing.append(f"{stem}: PNG export unavailable (kaleido missing or failed)")
        else:
            missing.append(f"{stem}: {chart_meta.get('skipped_reason', 'Data unavailable')}")

    summary_lines = [
        f"company: {meta.get('company_name', 'Unknown')}",
        f"years: {meta.get('years', 'N/A')}",
        f"generated_at: {generated_at}",
        f"accessions_used: {', '.join(meta.get('accessions', [])) or 'N/A'}",
        "missing_data_summary:",
    ]
    summary_lines.extend([f"- {item}" for item in (missing or ["none"])])
    summary_path = outdir / "run_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    zip_path = outdir / "report_pack.zip"
    with ZipFile(zip_path, mode="w", compression=ZIP_DEFLATED) as zf:
        for p in sorted(outdir.glob("*")):
            if p.name == zip_path.name or p.is_dir():
                continue
            zf.write(p, arcname=p.name)
    return zip_path
