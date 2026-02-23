from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from viz.charts import CHART_ORDER, build_all_figures
from viz.transform import json_to_tidy_df


@dataclass
class ChartResult:
    name: str
    generated: bool
    reason: str
    files: List[str]


class ReportGenerator:
    def __init__(self, payload: Dict[str, Any], outdir: Path, formats: Sequence[str]):
        self.payload = payload
        self.outdir = outdir
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.formats = tuple(formats)

    def generate(self) -> List[ChartResult]:
        df, meta = json_to_tidy_df(self.payload)
        meta["period_payloads"] = self.payload.get("periods", [])

        results: List[ChartResult] = []
        all_figures = {stem: (fig, fig_meta) for stem, fig, fig_meta in build_all_figures(df, meta)}

        for stem, _ in CHART_ORDER:
            fig, fig_meta = all_figures[stem]
            files: List[str] = []

            if "html" in self.formats:
                html_path = self.outdir / f"{stem}.html"
                fig.write_html(str(html_path), include_plotlyjs="cdn")
                files.append(html_path.name)

            if "png" in self.formats and fig_meta.get("created"):
                png_path = self.outdir / f"{stem}.png"
                fig.write_image(str(png_path), width=1400, height=900, scale=2)
                files.append(png_path.name)

            reason = "Generated" if fig_meta.get("created") else fig_meta.get("skipped_reason", "Data unavailable")
            results.append(ChartResult(name=stem, generated=bool(fig_meta.get("created")), reason=reason, files=files))

        return results


def load_payload(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)
