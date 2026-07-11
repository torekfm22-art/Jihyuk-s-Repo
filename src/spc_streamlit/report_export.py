"""Streamlit — 종합보고서 Excel/PDF 바이트 생성."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from src.spc.characteristic_split import COMPOSITE_SPLIT_COLUMN
from src.spc.comprehensive_report import ComprehensiveReportGenerator
from src.spc.decision_models import SpcDecisionResult
from src.spc.minitab_charts import ChartPaths
from src.spc.path_utils import resolve_nested_output_dir
from src.spc.pipeline import SpcPipelineResult
from src.spc.statistics import SpcAnalysisResult
from src.spc.summary_table_export import generate_summary_excel_bytes


def summary_file_tag(pipe: SpcPipelineResult) -> str:
    """판정 요약표 파일명 접미 태그."""
    if pipe.split_column == COMPOSITE_SPLIT_COLUMN:
        return "spc_composite_split"
    return pipe.split_column or "summary"


def save_batch_summary_excel(
    pipe: SpcPipelineResult,
    output_dir: Path,
    *,
    study_info: dict | None = None,
) -> Path:
    """일괄 분석 결과 — 판정 요약표를 output 폴더에 저장."""
    if output_dir is None:
        raise ValueError("output_dir가 필요합니다.")
    info = study_info or pipe.study_info or {}
    tag = summary_file_tag(pipe)
    data, fname = generate_summary_excel_bytes(pipe, study_info=info, file_tag=tag)
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / fname
    dest.write_bytes(data)
    return dest.resolve()


def build_comprehensive_excel(
    analysis: SpcAnalysisResult,
    charts: ChartPaths,
    sample_df: pd.DataFrame,
    study_info: dict,
    report_title: str,
    file_tag: str | None,
    decision: SpcDecisionResult | None,
) -> tuple[bytes, str]:
    gen = ComprehensiveReportGenerator(Path(tempfile.gettempdir()))
    excel_bytes, _, stem = gen.generate_bytes(
        analysis,
        charts=charts,
        raw_sample=sample_df,
        study_info=study_info,
        report_title=report_title,
        decision=decision,
        file_tag=file_tag,
    )
    return excel_bytes, f"{stem}.xlsx"


def build_comprehensive_pdf(
    analysis: SpcAnalysisResult,
    charts: ChartPaths,
    sample_df: pd.DataFrame,
    study_info: dict,
    report_title: str,
    file_tag: str | None,
    decision: SpcDecisionResult | None,
) -> tuple[bytes, str]:
    gen = ComprehensiveReportGenerator(Path(tempfile.gettempdir()))
    _, pdf_bytes, stem = gen.generate_bytes(
        analysis,
        charts=charts,
        raw_sample=sample_df,
        study_info=study_info,
        report_title=report_title,
        decision=decision,
        file_tag=file_tag,
    )
    return pdf_bytes, f"{stem}.pdf"


def report_context(result: SpcPipelineResult) -> dict:
    return {
        "study_info": result.study_info or {},
        "title": result.report_title or "SPC 및 공정능력 연구 보고서",
        "file_tag": result.characteristic,
    }


def build_multi_target_summary_excel(
    pipe: SpcPipelineResult,
    *,
    study_info: dict | None = None,
    title: str = "SPC 분석 대상별 판정 요약",
    file_tag: str | None = None,
) -> tuple[bytes, str]:
    """결론 — 분석 대상별 LCL/CL/UCL·공정능력·관리도 비고 요약표."""
    info = study_info or pipe.study_info or {}
    tag = file_tag or summary_file_tag(pipe)
    return generate_summary_excel_bytes(pipe, study_info=info, title=title, file_tag=tag)
