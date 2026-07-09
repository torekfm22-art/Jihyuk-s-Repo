"""종합 Excel/PDF 보고서 생성 — 편측·양측 공차 회귀."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.spc.comprehensive_report import ComprehensiveReportGenerator
from src.spc.minitab_charts import ChartPaths
from src.spc.statistics import SpcAnalyzer


def _fake_charts(tmp: Path) -> ChartPaths:
    """존재하지 않는 경로 — 차트 삽입은 건너뛰고 Excel 본문·시트만 검증."""
    return ChartPaths(
        tmp / "h.png",
        tmp / "r.png",
        tmp / "p.png",
        tmp / "c.png",
    )


def _sample_df(n: int = 125) -> pd.DataFrame:
    vals = np.linspace(0.2, 0.25, n)
    return pd.DataFrame({
        "value": vals,
        "subgroup_id": [i // 5 + 1 for i in range(n)],
    })


@pytest.mark.parametrize(
    "usl,lsl,expect_labels",
    [
        (5.0, None, ["Cpu (CWU)", "P% > USL"]),
        (None, 0.1, ["Cpl (CWL)", "P% < LSL"]),
        (5.0, 0.1, ["Cp", "P% > USL", "P% < LSL"]),
    ],
)
def test_capability_rows_one_sided_and_two_sided(usl, lsl, expect_labels):
    vals = np.linspace(0.2, 0.25, 125)
    subgroups = np.array([vals[i : i + 5] for i in range(0, 125, 5)])
    analyzer = SpcAnalyzer()
    analysis = analyzer.analyze_xbar_r(subgroups, usl=usl, lsl=lsl)

    with tempfile.TemporaryDirectory() as td:
        gen = ComprehensiveReportGenerator(Path(td))
        rows = dict(gen._capability_rows(analysis))

    assert rows["USL"] == "—" if usl is None else f"{usl:g}"
    assert rows["LSL"] == "—" if lsl is None else f"{lsl:g}"
    for label in expect_labels:
        assert label in rows
    if usl is None:
        assert "P% > USL" not in rows
    if lsl is None:
        assert "P% < LSL" not in rows


def test_generate_bytes_upper_only_spec():
    vals = np.linspace(0.2, 0.25, 125)
    subgroups = np.array([vals[i : i + 5] for i in range(0, 125, 5)])
    analyzer = SpcAnalyzer()
    analysis = analyzer.analyze_xbar_r(subgroups, usl=5.0, lsl=None)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        charts = _fake_charts(td_path)
        gen = ComprehensiveReportGenerator(td_path)
        excel_bytes, pdf_bytes, stem = gen.generate_bytes(
            analysis,
            charts=charts,
            raw_sample=_sample_df(),
            study_info={"process": "P1", "characteristic": "X"},
            decision=None,
            file_tag="upper_only",
        )

    assert len(excel_bytes) > 5000
    assert stem.startswith("SPC_종합보고서")
    assert excel_bytes[:2] == b"PK"
    try:
        import reportlab  # noqa: F401
    except ImportError:
        pytest.skip("reportlab not installed")
    else:
        assert len(pdf_bytes) > 100
