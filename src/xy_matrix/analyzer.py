"""
X-Y 매트릭스 자동 분석 메인 오케스트레이션.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from src.xy_matrix.analysis_engine import (
    calculate_score,
    run_statistical_analysis,
    select_analysis_method,
)
from src.xy_matrix.data_detection import DataSource, auto_detect_data_structure
from src.xy_matrix.multiple_regression import run_multiple_regression
from src.xy_matrix.output import (
    build_pareto_data,
    export_to_excel,
    matrix_to_display_df,
    pareto_to_display_df,
)
from src.xy_matrix.visualization import plot_pareto_chart
from src.xy_matrix.spc_recommendations import generate_spc_recommendations

logger = logging.getLogger(__name__)

OutputFormat = Literal["dict", "dataframe", "excel", "report"]


def analyze_xy_matrix(
    data_source: DataSource,
    y_column: str | None = None,
    x_columns: list[str] | None = None,
    exclude_columns: list[str] | None = None,
    score_thresholds: dict | None = None,
    run_multiple_reg: bool = True,
    controllability: dict[str, bool] | None = None,
    output_format: OutputFormat = "dict",
    output_path: str | Path | None = None,
    sheet_name: str | int = 0,
    save_pareto_chart: bool = True,
    pareto_chart_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Raw 데이터 → 구조 인식 → X별 통계 → 매트릭스·파레토·다중회귀·SPC 권고.
    """
    df, structure = auto_detect_data_structure(data_source, sheet_name=sheet_name)

    if len(structure["y_columns"]) > 1 and y_column is None:
        logger.info(
            "복수 Y인자 탐지: %s — 첫 번째 사용. y_column으로 지정 가능.",
            structure["y_columns"],
        )

    y_col = y_column or structure["y_columns"][0]
    if y_col not in df.columns:
        raise ValueError(f"Y인자 '{y_col}'이 데이터에 없습니다.")

    structure["selected_y"] = y_col
    x_cols = list(x_columns or structure["x_columns"])
    excluded = set(structure.get("excluded_columns", []))
    if exclude_columns:
        excluded.update(exclude_columns)
    x_cols = [c for c in x_cols if c not in excluded and c != y_col]

    if not x_cols:
        raise ValueError("분석할 X인자가 없습니다.")

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for x_col in x_cols:
        x_type = structure["x_types"].get(x_col, "계량형")
        y_type = structure["y_types"].get(y_col)
        if y_type == "분석불가":
            raise ValueError(f"Y인자 '{y_col}' 유형이 분석 불가입니다.")

        try:
            method = select_analysis_method(x_type, y_type)
            stats_result = run_statistical_analysis(df, y_col, x_col, method)
            r_sq = stats_result.get("r_square", 0) or 0
            p_val = stats_result.get("p_value", 1.0)
            score, symbol, interpretation = calculate_score(
                p_val, r_sq, score_thresholds
            )
            results.append({
                "x_column": x_col,
                "x_type": x_type,
                **stats_result,
                "score": score,
                "symbol": symbol,
                "interpretation": interpretation,
            })
        except Exception as exc:
            logger.warning("'%s' 분석 실패: %s", x_col, exc)
            errors.append({"x_column": x_col, "error": str(exc)})

    if not results:
        raise ValueError(
            "모든 X인자 분석에 실패했습니다. "
            + "; ".join(f"{e['x_column']}: {e['error']}" for e in errors[:5])
        )

    matrix_df = pd.DataFrame(results)
    matrix_df = matrix_df.sort_values(
        ["score", "r_square"], ascending=[False, False], na_position="last"
    )
    matrix_df["rank"] = range(1, len(matrix_df) + 1)

    multi_reg_result = None
    if run_multiple_reg:
        top_factors = matrix_df[matrix_df["score"] >= 3]["x_column"].tolist()
        if len(top_factors) >= 2 and structure["y_types"].get(y_col) == "계량형":
            try:
                multi_reg_result = run_multiple_regression(
                    df, y_col, top_factors, structure["x_types"]
                )
            except Exception as exc:
                logger.warning("다중회귀 실패: %s", exc)
                multi_reg_result = {"error": str(exc)}

    pareto_df = build_pareto_data(matrix_df)
    pareto_chart_file = None
    if save_pareto_chart and pareto_df["score"].sum() > 0:
        chart_path = pareto_chart_path or (
            Path(output_path).parent / "charts" / "xy_pareto.png"
            if output_path
            else Path("data/output/charts/xy_pareto.png")
        )
        try:
            pareto_chart_file = plot_pareto_chart(
                pareto_df,
                chart_path,
                title="X-Y 매트릭스 파레토 분석",
                subtitle=f"Y 인자: {y_col} | 점수 기준 80% 구간",
            )
        except Exception as exc:
            logger.warning("파레토 차트 저장 실패: %s", exc)

    recommendations = generate_spc_recommendations(
        matrix_df,
        multi_reg_result,
        controllability,
        structure,
    )

    payload: dict[str, Any] = {
        "data_structure": structure,
        "analysis_data": df.copy(),
        "matrix": matrix_df,
        "matrix_display": matrix_to_display_df(matrix_df),
        "calc_details": results,
        "analysis_errors": errors,
        "multiple_regression": multi_reg_result,
        "pareto_data": pareto_df,
        "pareto_display": pareto_to_display_df(pareto_df),
        "pareto_chart_path": str(pareto_chart_file) if pareto_chart_file else None,
        "recommendations": recommendations,
        "y_column": y_col,
    }

    if output_format == "dataframe":
        payload["matrix"] = payload["matrix_display"]
    elif output_format == "excel":
        if not output_path:
            raise ValueError("output_format='excel'일 때 output_path가 필요합니다.")
        export_to_excel(payload, output_path)
        payload["excel_path"] = str(Path(output_path))
    elif output_format == "report":
        payload["report_text"] = _format_text_report(payload)

    return payload


def _format_text_report(result: dict[str, Any]) -> str:
    lines = ["=== X-Y 매트릭스 분석 보고 ===", ""]
    disp = result.get("matrix_display")
    if disp is not None:
        lines.append(disp.to_string(index=False))
    lines.append("")
    rec = result.get("recommendations", {})
    lines.append(rec.get("summary", ""))
    for ctp in rec.get("ctp_factors", []):
        lines.append(
            f"  CTP: {ctp['factor']} ({ctp['symbol']}) → {ctp['chart_recommendation']}"
        )
    if result.get("multiple_regression") and "vif_warnings" in result["multiple_regression"]:
        for w in result["multiple_regression"]["vif_warnings"]:
            lines.append(f"  [VIF 경고] {w}")
    return "\n".join(lines)
