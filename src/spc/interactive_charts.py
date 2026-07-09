"""Streamlit용 Plotly 인터랙티브 SPC 차트 (hover tooltip)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats

from src.spc.chart_sigma_zones import iter_sigma_zone_lines
from src.spc.pipeline import SpcPipelineResult
from src.spc.sample_ordering import resolve_sort_timestamp_series, sort_sample_dataframe
from src.spc.statistics import SpcAnalysisResult, SpcAnalyzer


# 이상점 마커 색 — 평균(Xbar/I) vs 산포(S/R/MR)
ANOMALY_MEAN_COLOR = "#C71585"   # 다홍색 (MediumVioletRed)
ANOMALY_DISP_COLOR = "#d62728"   # 빨간색


def _fmt_ts(val: Any) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "-"
    try:
        ts = pd.Timestamp(val)
        if pd.isna(ts):
            return str(val)
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(val)


def _hover_fields(row: pd.Series) -> str:
    labels = [
        ("timestamp", "일시"),
        ("measure_time", "검사시간"),
        ("measure_date", "측정일"),
        ("value", "측정값"),
        ("measurement_point", "측정 포인트"),
        ("lot", "LOT"),
        ("machine", "설비"),
        ("process", "공정"),
        ("process_name", "공정명"),
        ("item", "품번"),
        ("subgroup_id", "Subgroup"),
    ]
    lines: list[str] = []
    for key, label in labels:
        if key not in row.index:
            continue
        val = row[key]
        if pd.isna(val):
            continue
        if key == "timestamp":
            lines.append(f"{label}: {_fmt_ts(val)}")
        elif key in ("measure_time", "measure_date"):
            lines.append(f"{label}: {_fmt_ts(val)}")
        elif key == "value":
            try:
                lines.append(f"{label}: {float(val):.4f}")
            except (TypeError, ValueError):
                lines.append(f"{label}: {val}")
        else:
            lines.append(f"{label}: {val}")
    return "<br>".join(lines) if lines else ""


def _subgroup_hover(
    sample_df: pd.DataFrame,
    sg_id: int,
    y_val: float,
    *,
    point_labels: dict[int, list[str]] | None = None,
    extra_labels: list[str] | None = None,
) -> str:
    if sample_df is None or sample_df.empty or "subgroup_id" not in sample_df.columns:
        lines = [f"Subgroup {sg_id}", f"평균/대표값: {y_val:.4f}"]
        _append_violation_lines(lines, sg_id, point_labels, extra_labels)
        return "<br>".join(lines)

    chunk = sample_df.loc[sample_df["subgroup_id"] == sg_id]
    if chunk.empty:
        lines = [f"Subgroup {sg_id}", f"평균/대표값: {y_val:.4f}"]
        _append_violation_lines(lines, sg_id, point_labels, extra_labels)
        return "<br>".join(lines)

    lines = [f"Subgroup {sg_id}", f"평균/대표값: {y_val:.4f}", f"n={len(chunk)}"]

    if "sampling_date" in chunk.columns:
        dates = chunk["sampling_date"].dropna().astype(str).unique().tolist()
        if dates and dates != ["SEQUENCE"]:
            lines.append("채취일: " + ", ".join(dates[:3]))

    ts = resolve_sort_timestamp_series(chunk)
    if ts.notna().any():
        tmin, tmax = ts.min(), ts.max()
        if tmin.normalize() == tmax.normalize():
            lines.append(f"검사일: {tmin.strftime('%Y-%m-%d')}")
            if tmin != tmax:
                lines.append(f"시간: {_fmt_ts(tmin)} ~ {_fmt_ts(tmax)}")
            else:
                lines.append(f"검사시간: {_fmt_ts(tmin)}")
        else:
            lines.append(
                f"검사기간: {tmin.strftime('%Y-%m-%d %H:%M')} ~ {tmax.strftime('%Y-%m-%d %H:%M')}"
            )

    if "lot" in chunk.columns:
        lots = chunk["lot"].dropna().astype(str).unique().tolist()[:3]
        if lots:
            lines.append("LOT: " + ", ".join(lots))
    if "value" in chunk.columns:
        vals = chunk["value"].astype(float)
        lines.append(f"군 내 범위: {vals.min():.4f} ~ {vals.max():.4f}")

    _append_violation_lines(lines, sg_id, point_labels, extra_labels)
    return "<br>".join(lines)


def _append_violation_lines(
    lines: list[str],
    point_id: int,
    point_labels: dict[int, list[str]] | None,
    extra_labels: list[str] | None,
) -> None:
    names: list[str] = []
    if point_labels and point_id in point_labels:
        names.extend(point_labels[point_id])
    if extra_labels:
        for lbl in extra_labels:
            if lbl not in names:
                names.append(lbl)
    if names:
        lines.append("<b>이상 유형:</b> " + ", ".join(names))


def _point_hover(
    point_id: int,
    y_val: float,
    *,
    sample_df: pd.DataFrame | None = None,
    row: pd.Series | None = None,
    point_labels: dict[int, list[str]] | None = None,
    extra_labels: list[str] | None = None,
    label: str = "Point",
) -> str:
    if row is not None:
        base = _hover_fields(row)
        if base:
            lines = base.split("<br>")
        else:
            lines = [f"{label} {point_id}", f"값: {y_val:.4f}"]
    else:
        lines = [f"{label} {point_id}", f"값: {y_val:.4f}"]
    _append_violation_lines(lines, point_id, point_labels, extra_labels)
    return "<br>".join(lines)


def _apply_control_chart_legend(fig: go.Figure) -> None:
    """범례 — 차트 우상단 가로 배치 (UCL/LCL 오른쪽 라벨과 겹치지 않음)."""
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1.0,
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="#cccccc",
            borderwidth=1,
            font=dict(size=10),
            tracegroupgap=12,
        ),
        margin=dict(t=72, r=110, b=48),
    )


def _control_trace(
    x,
    y,
    name: str,
    hover: list[str],
    color: str = "#1f77b4",
) -> go.Scatter:
    return go.Scatter(
        x=x,
        y=y,
        mode="lines+markers",
        name=name,
        line=dict(color=color, width=1.2),
        marker=dict(size=7, color=color),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover,
    )


def _yaxis_name(row: int) -> str:
    return "y" if row == 1 else f"y{row}"


def _add_right_y_labels(
    fig: go.Figure,
    row: int,
    col: int,
    items: list[tuple[float, str, str]],
) -> None:
    """Y값을 차트 오른쪽에 텍스트로 표기 (선 없음)."""
    yref = _yaxis_name(row)
    for y_val, text, color in items:
        fig.add_annotation(
            xref="x domain",
            yref=yref,
            x=1.02,
            y=y_val,
            text=text,
            showarrow=False,
            xanchor="left",
            font=dict(color=color, size=10),
            row=row,
            col=col,
        )


def _control_y_range(
    y_data: np.ndarray,
    ucl: float,
    cl: float,
    lcl: float,
    *,
    pad_ratio: float = 0.12,
) -> tuple[float, float]:
    """관리한계·데이터 기준 Y축 (규격한은 범위에 포함하지 않음)."""
    ys = [float(np.nanmin(y_data)), float(np.nanmax(y_data)), ucl, cl, lcl]
    y_min, y_max = min(ys), max(ys)
    span = max(y_max - y_min, 1e-9)
    pad = span * pad_ratio
    return y_min - pad, y_max + pad


def _apply_control_y_range(
    fig: go.Figure,
    row: int,
    y_data: np.ndarray,
    ucl: float,
    cl: float,
    lcl: float,
) -> None:
    y0, y1 = _control_y_range(y_data, ucl, cl, lcl)
    fig.update_yaxes(range=[y0, y1], autorange=False, row=row, col=1)


def _spec_limit_labels_right(
    fig: go.Figure,
    row: int,
    col: int,
    usl: float | None,
    lsl: float | None,
) -> None:
    """규격 상·하한 — 선 없이 오른쪽에 값만 표기."""
    spec_color = "#7030A0"
    items: list[tuple[float, str, str]] = []
    if usl is not None:
        items.append((usl, f"USL={usl:.4f}", spec_color))
    if lsl is not None:
        items.append((lsl, f"LSL={lsl:.4f}", spec_color))
    if items:
        _add_right_y_labels(fig, row, col, items)


def _limit_lines(fig, row: int, col: int, cl: float, ucl: float, lcl: float) -> None:
    _sigma_zone_lines(fig, row, col, cl, ucl, lcl)
    for val, dash, color in (
        (ucl, "dash", "#d62728"),
        (cl, "solid", "#2ca02c"),
        (lcl, "dash", "#d62728"),
    ):
        fig.add_hline(
            y=val,
            line_dash=dash,
            line_color=color,
            line_width=1.2,
            row=row,
            col=col,
        )
    _add_right_y_labels(
        fig,
        row,
        col,
        [
            (ucl, f"UCL={ucl:.4f}", "#d62728"),
            (cl, f"CL={cl:.4f}", "#2ca02c"),
            (lcl, f"LCL={lcl:.4f}", "#d62728"),
        ],
    )


def _sigma_zone_lines(fig, row: int, col: int, cl: float, ucl: float, lcl: float) -> None:
    """σ 1·2·3 구간선 (CL 기준, 상·하한 비대칭 시 각각 절대 거리/3)."""
    for y_val, label in iter_sigma_zone_lines(cl, ucl, lcl):
        fig.add_hline(
            y=y_val,
            line_dash="dot",
            line_color="rgba(120, 120, 120, 0.55)",
            line_width=0.9,
            annotation_text=label,
            annotation_position="top left" if label.startswith("+") else "bottom left",
            annotation_font_size=9,
            annotation_font_color="rgba(80, 80, 80, 0.9)",
            row=row,
            col=col,
        )


def _add_violation_markers(
    fig: go.Figure,
    x,
    y,
    point_ids: list[int],
    violation_points: set[int],
    *,
    row: int = 1,
    col: int = 1,
    name: str = "이상점",
    color: str = ANOMALY_MEAN_COLOR,
    hover_texts: list[str] | None = None,
) -> None:
    if not violation_points:
        return
    xs, ys, hover = [], [], []
    for i, pid in enumerate(point_ids):
        if int(pid) not in violation_points:
            continue
        xs.append(x[i] if hasattr(x, "__getitem__") else list(x)[i])
        ys.append(y[i] if hasattr(y, "__getitem__") else list(y)[i])
        if hover_texts and i < len(hover_texts):
            hover.append(hover_texts[i])
        else:
            hover.append(f"{name} #{pid}")
    if not xs:
        return
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            name=name,
            marker=dict(size=13, color=color, symbol="x", line=dict(width=2, color="white")),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
        ),
        row=row,
        col=col,
    )


def _resolve_violation_sets(
    analysis: SpcAnalysisResult,
    violation_points: set[int] | None,
    decision: Any | None,
) -> tuple[set[int], set[int], dict[int, list[str]]]:
    """평균·산포 이상점 및 포인트별 유형 라벨."""
    from src.spc.chart_violations import (
        collect_chart_violation_points,
        collect_dispersion_violation_points,
        collect_point_violation_labels,
    )

    if decision is not None:
        mean_vio = collect_chart_violation_points(decision, analysis)
        point_labels = collect_point_violation_labels(decision, analysis)
    else:
        mean_vio = set(violation_points or [])
        point_labels = {}

    disp_vio = collect_dispersion_violation_points(analysis)
    for pid in disp_vio:
        labels = point_labels.setdefault(pid, [])
        if not any("산포" in lbl for lbl in labels):
            labels.append("산포 관리한계 이탈")
    return mean_vio, disp_vio, point_labels


def build_control_chart_figure(
    analysis: SpcAnalysisResult,
    sample_df: pd.DataFrame | None = None,
    violation_points: set[int] | None = None,
    decision: Any | None = None,
) -> go.Figure | None:
    """관리도 Plotly figure (hover 지원)."""
    limits = analysis.control_limits
    chart = analysis.chart_type
    mean_vio, disp_vio, point_labels = _resolve_violation_sets(
        analysis, violation_points, decision,
    )
    cap = analysis.capability
    usl = cap.usl if cap else None
    lsl = cap.lsl if cap else None

    if chart == "xbar_s" and analysis.subgroup_stats is not None:
        df = analysis.subgroup_stats
        x = df["subgroup"].to_numpy()
        pids = df["subgroup"].astype(int).tolist()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                            subplot_titles=("Xbar", "S"))
        hover_x = [
            _subgroup_hover(sample_df, int(i), float(v), point_labels=point_labels)
            for i, v in zip(x, df["Xbar"])
        ]
        hover_s = [
            _subgroup_hover(
                sample_df, int(i), float(v), point_labels=point_labels,
                extra_labels=["산포 관리한계 이탈"] if int(i) in disp_vio else None,
            )
            for i, v in zip(x, df["S"])
        ]
        fig.add_trace(_control_trace(x, df["Xbar"], "Xbar", hover_x), row=1, col=1)
        _add_violation_markers(
            fig, x, df["Xbar"], pids, mean_vio, row=1, col=1,
            color=ANOMALY_MEAN_COLOR,
            hover_texts=[hover_x[i] for i, pid in enumerate(pids) if int(pid) in mean_vio],
        )
        fig.add_trace(_control_trace(x, df["S"], "S", hover_s, color="#ff7f0e"), row=2, col=1)
        _add_violation_markers(
            fig, x, df["S"], pids, disp_vio, row=2, col=1,
            name="이상점 (산포)", color=ANOMALY_DISP_COLOR,
            hover_texts=[hover_s[i] for i, pid in enumerate(pids) if int(pid) in disp_vio],
        )
        _limit_lines(fig, 1, 1, limits.xbar_limits["CL"], limits.xbar_limits["UCL"], limits.xbar_limits["LCL"])
        _spec_limit_labels_right(fig, 1, 1, usl, lsl)
        _limit_lines(fig, 2, 1, limits.s_limits["CL"], limits.s_limits["UCL"], limits.s_limits["LCL"])
        _apply_control_y_range(fig, 1, df["Xbar"].to_numpy(), limits.xbar_limits["UCL"], limits.xbar_limits["CL"], limits.xbar_limits["LCL"])
        _apply_control_y_range(fig, 2, df["S"].to_numpy(), limits.s_limits["UCL"], limits.s_limits["CL"], limits.s_limits["LCL"])
        fig.update_xaxes(title_text="Subgroup", row=2, col=1)
        fig.update_layout(title="Xbar-S Control Chart", height=520)
        _apply_control_chart_legend(fig)
        return fig

    if chart == "xbar_r" and analysis.subgroup_stats is not None:
        df = analysis.subgroup_stats
        x = df["subgroup"].to_numpy()
        pids = df["subgroup"].astype(int).tolist()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                            subplot_titles=("Xbar", "R"))
        hover_x = [
            _subgroup_hover(sample_df, int(i), float(v), point_labels=point_labels)
            for i, v in zip(x, df["Xbar"])
        ]
        hover_r = [
            _subgroup_hover(
                sample_df, int(i), float(v), point_labels=point_labels,
                extra_labels=["산포 관리한계 이탈"] if int(i) in disp_vio else None,
            )
            for i, v in zip(x, df["R"])
        ]
        fig.add_trace(_control_trace(x, df["Xbar"], "Xbar", hover_x), row=1, col=1)
        _add_violation_markers(
            fig, x, df["Xbar"], pids, mean_vio, row=1, col=1,
            color=ANOMALY_MEAN_COLOR,
            hover_texts=[hover_x[i] for i, pid in enumerate(pids) if int(pid) in mean_vio],
        )
        fig.add_trace(_control_trace(x, df["R"], "R", hover_r, color="#ff7f0e"), row=2, col=1)
        _add_violation_markers(
            fig, x, df["R"], pids, disp_vio, row=2, col=1,
            name="이상점 (산포)", color=ANOMALY_DISP_COLOR,
            hover_texts=[hover_r[i] for i, pid in enumerate(pids) if int(pid) in disp_vio],
        )
        _limit_lines(fig, 1, 1, limits.xbar_limits["CL"], limits.xbar_limits["UCL"], limits.xbar_limits["LCL"])
        _spec_limit_labels_right(fig, 1, 1, usl, lsl)
        _limit_lines(fig, 2, 1, limits.r_limits["CL"], limits.r_limits["UCL"], limits.r_limits["LCL"])
        _apply_control_y_range(fig, 1, df["Xbar"].to_numpy(), limits.xbar_limits["UCL"], limits.xbar_limits["CL"], limits.xbar_limits["LCL"])
        _apply_control_y_range(fig, 2, df["R"].to_numpy(), limits.r_limits["UCL"], limits.r_limits["CL"], limits.r_limits["LCL"])
        fig.update_xaxes(title_text="Subgroup", row=2, col=1)
        fig.update_layout(title="Xbar-R Control Chart", height=520)
        _apply_control_chart_legend(fig)
        return fig

    if chart == "imr" and analysis.individual_stats is not None:
        df = analysis.individual_stats
        x = df["point"].to_numpy()
        pids = df["point"].astype(int).tolist()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                            subplot_titles=("I", "MR"))
        sorted_sample = sort_sample_dataframe(sample_df) if sample_df is not None else None
        hover_i: list[str] = []
        if sorted_sample is not None and not sorted_sample.empty:
            for idx, (_, row) in enumerate(sorted_sample.iterrows()):
                pid = idx + 1
                hover_i.append(
                    _point_hover(
                        pid, float(row.get("value", df["I"].iloc[idx] if idx < len(df) else 0)),
                        row=row, point_labels=point_labels, label="Point",
                    )
                )
        else:
            for p, v in zip(x, df["I"]):
                hover_i.append(
                    _point_hover(int(p), float(v), point_labels=point_labels, label="Point")
                )
        fig.add_trace(_control_trace(x, df["I"], "I", hover_i), row=1, col=1)
        _add_violation_markers(
            fig, x, df["I"], pids, mean_vio, row=1, col=1,
            color=ANOMALY_MEAN_COLOR,
            hover_texts=[hover_i[i] for i, pid in enumerate(pids) if int(pid) in mean_vio],
        )
        mr = df["MR"].to_numpy()
        valid = ~np.isnan(mr)
        x_mr = x[valid]
        pids_mr = df["point"].astype(int).to_numpy()[valid].tolist()
        hover_mr = [
            _point_hover(
                int(p), float(v), point_labels=point_labels,
                extra_labels=["MR 관리한계 이탈"] if int(p) in disp_vio else None,
                label="Point",
            )
            for p, v in zip(x_mr, mr[valid])
        ]
        fig.add_trace(
            _control_trace(x_mr, mr[valid], "MR", hover_mr, color="#ff7f0e"),
            row=2, col=1,
        )
        _add_violation_markers(
            fig, x_mr, mr[valid], pids_mr, disp_vio,
            row=2, col=1, name="이상점 (MR)", color=ANOMALY_DISP_COLOR,
            hover_texts=[hover_mr[i] for i, pid in enumerate(pids_mr) if int(pid) in disp_vio],
        )
        _limit_lines(fig, 1, 1, limits.i_limits["CL"], limits.i_limits["UCL"], limits.i_limits["LCL"])
        _spec_limit_labels_right(fig, 1, 1, usl, lsl)
        _limit_lines(fig, 2, 1, limits.mr_limits["CL"], limits.mr_limits["UCL"], 0.0)
        _apply_control_y_range(fig, 1, df["I"].to_numpy(), limits.i_limits["UCL"], limits.i_limits["CL"], limits.i_limits["LCL"])
        mr_valid = mr[valid]
        _apply_control_y_range(fig, 2, mr_valid, limits.mr_limits["UCL"], limits.mr_limits["CL"], max(0.0, limits.mr_limits["LCL"]))
        fig.update_xaxes(title_text="Point", row=2, col=1)
        fig.update_layout(title="I-MR Control Chart", height=520)
        _apply_control_chart_legend(fig)
        return fig

    return None


def _sort_sample_for_chart(df: pd.DataFrame) -> pd.DataFrame:
    """시계열 차트용 — 시간순(또는 subgroup 순) 정렬."""
    return sort_sample_dataframe(df)


def _raw_chart_x_axis(plot_df: pd.DataFrame) -> tuple[np.ndarray, str, pd.Series | None]:
    """
    Raw Value 차트 x축 — 시간순 1..n (왼→오).
    일별 datetime 축 대신 순번 + 눈금에 시·분 표기로 같은 날 내 순서도 구분.
    """
    n = len(plot_df)
    x = np.arange(1, n + 1, dtype=float)
    ts = resolve_sort_timestamp_series(plot_df)
    if ts.notna().sum() >= max(2, n // 3):
        return x, "측정 순서 (시간순 →)", ts
    return x, "순번", None


def _apply_raw_chart_time_ticks(fig: go.Figure, ts: pd.Series, n: int) -> None:
    """x축 눈금 — 월/일 시:분 (시간대별 순서 표시)."""
    if ts is None or n <= 0 or not ts.notna().any():
        return
    max_ticks = 14
    step = max(1, n // max_ticks)
    tickvals = list(range(1, n + 1, step))
    if tickvals[-1] != n:
        tickvals.append(n)
    ticktext: list[str] = []
    for i in tickvals:
        t = ts.iloc[i - 1]
        if pd.isna(t):
            ticktext.append(str(i))
        else:
            ticktext.append(pd.Timestamp(t).strftime("%m/%d %H:%M"))
    fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)


def _build_raw_chart_figure_impl(
    sample_df: pd.DataFrame | None,
    raw_values: np.ndarray | None = None,
    mean: float | None = None,
    violation_points: set[int] | None = None,
    *,
    anomaly_subgroups: set[int] | None = None,
    rule_labels_by_point: dict[int, list[str]] | None = None,
    chart_type: str | None = None,
    title: str = "Raw Value Chart",
    height: int = 420,
) -> go.Figure | None:
    plot_df: pd.DataFrame | None = None
    ts_series: pd.Series | None = None
    if sample_df is not None and not sample_df.empty and "value" in sample_df.columns:
        plot_df = _sort_sample_for_chart(sample_df)
        y = plot_df["value"].astype(float).to_numpy()
        hover: list[str] = []
        subgroup_per_pos: list[int | None] = []
        x, x_title, ts_series = _raw_chart_x_axis(plot_df)
        for idx, (_, row) in enumerate(plot_df.iterrows()):
            pos = idx + 1
            if chart_type in ("xbar_s", "xbar_r") and "subgroup_id" in row.index and pd.notna(row["subgroup_id"]):
                sg_key = int(row["subgroup_id"])
            else:
                sg_key = pos
            subgroup_per_pos.append(sg_key)
            lines = _hover_fields(row).split("<br>") if _hover_fields(row) else [f"순번: {pos}"]
            if ts_series is not None and idx < len(ts_series) and pd.notna(ts_series.iloc[idx]):
                ts_line = f"일시: {_fmt_ts(ts_series.iloc[idx])}"
                if not any(ts_line.split(": ", 1)[-1] in ln for ln in lines):
                    lines.insert(0, ts_line)
            if anomaly_subgroups and sg_key in anomaly_subgroups:
                lines.append(f"<b>⚠ 이상 Subgroup: {sg_key}</b>")
                rules = (rule_labels_by_point or {}).get(sg_key, [])
                if rules:
                    lines.append("이상 Rule: " + ", ".join(rules))
            if pos in (violation_points or set()):
                lines.append("<b>⚠ 이상점</b>")
            hover.append("<br>".join(lines))
    elif raw_values is not None and len(raw_values):
        y = np.asarray(raw_values, dtype=float)
        x = np.arange(1, len(y) + 1)
        hover = [f"순번: {i}<br>측정값: {v:.4f}" for i, v in zip(x, y)]
        subgroup_per_pos = list(range(1, len(y) + 1))
        x_title = "순번"
    else:
        return None

    m = mean if mean is not None else float(np.mean(y))
    vio = violation_points or set()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            name="측정값",
            line=dict(color="#1f77b4"),
            marker=dict(size=6),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
        )
    )
    if vio:
        vx, vy, vhover = [], [], []
        for idx in range(len(y)):
            pid = idx + 1
            if pid in vio:
                xv = x[idx] if hasattr(x, "__getitem__") else list(x)[idx]
                vx.append(xv)
                vy.append(y[idx])
                vhover.append(hover[idx])
        if vx:
            fig.add_trace(
                go.Scatter(
                    x=vx,
                    y=vy,
                    mode="markers",
                    name="이상점",
                    marker=dict(size=12, color=ANOMALY_MEAN_COLOR, symbol="x", line=dict(width=2, color="white")),
                    hovertemplate="%{customdata}<extra></extra>",
                    customdata=vhover,
                )
            )
        if anomaly_subgroups and plot_df is not None:
            seen: set[int] = set()
            for idx in range(len(y)):
                sg_key = subgroup_per_pos[idx] if idx < len(subgroup_per_pos) else idx + 1
                if sg_key not in anomaly_subgroups or sg_key in seen:
                    continue
                seen.add(sg_key)
                xv = x[idx] if hasattr(x, "__getitem__") else list(x)[idx]
                fig.add_annotation(
                    x=xv,
                    y=float(y[idx]),
                    text=f"SG {sg_key}",
                    showarrow=True,
                    arrowhead=2,
                    ay=-28,
                    bgcolor="rgba(255,192,203,0.85)",
                    bordercolor="#C71585",
                    font=dict(size=11, color="#9C0006"),
                )
    fig.add_hline(y=m, line_color="#2ca02c", annotation_text=f"Mean={m:.4f}")
    fig.update_layout(title=title, xaxis_title=x_title, yaxis_title="측정값", height=height)
    if ts_series is not None and plot_df is not None:
        _apply_raw_chart_time_ticks(fig, ts_series, len(plot_df))
    return fig


def build_raw_chart_figure(
    sample_df: pd.DataFrame | None,
    raw_values: np.ndarray | None = None,
    mean: float | None = None,
    violation_points: set[int] | None = None,
    **kwargs: Any,
) -> go.Figure | None:
    """Raw Value 시계열 차트 (기존 호출부 호환)."""
    return _build_raw_chart_figure_impl(
        sample_df,
        raw_values,
        mean,
        violation_points,
        anomaly_subgroups=kwargs.get("anomaly_subgroups"),
        rule_labels_by_point=kwargs.get("rule_labels_by_point"),
        chart_type=kwargs.get("chart_type"),
        title=kwargs.get("title", "Raw Value Chart"),
        height=int(kwargs.get("height", 420)),
    )


def build_traceability_raw_chart_figure(
    sample_df: pd.DataFrame,
    *,
    mean: float | None = None,
    violation_points: set[int] | None = None,
    anomaly_subgroups: set[int] | None = None,
    rule_labels_by_point: dict[int, list[str]] | None = None,
    chart_type: str | None = None,
    title: str = "Raw Value Chart — 추적성 (이상 Subgroup 표기)",
    height: int = 460,
) -> go.Figure | None:
    """추적성 관리 — Subgroup 라벨·hover 강화 Raw Value 차트."""
    return _build_raw_chart_figure_impl(
        sample_df,
        mean=mean,
        violation_points=violation_points,
        anomaly_subgroups=anomaly_subgroups,
        rule_labels_by_point=rule_labels_by_point,
        chart_type=chart_type,
        title=title,
        height=height,
    )


def individual_control_limits_for_histogram(
    analysis: SpcAnalysisResult,
    raw_values: np.ndarray,
) -> tuple[float | None, float | None, float | None]:
    """히스토그램용 I-chart 관리한계 (개별 측정값 기준)."""
    cl = analysis.control_limits
    if cl.i_limits:
        lim = cl.i_limits
        return lim["UCL"], lim["CL"], lim["LCL"]
    arr = np.asarray(raw_values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return None, None, None
    limits = SpcAnalyzer().imr_limits(arr)
    lim = limits.i_limits
    return lim["UCL"], lim["CL"], lim["LCL"]


def _histogram_x_range(
    values: np.ndarray,
    ucl: float | None,
    lcl: float | None,
    cl: float | None,
    *,
    pad_ratio: float = 0.12,
) -> tuple[float, float]:
    xs = [float(np.min(values)), float(np.max(values))]
    for v in (ucl, lcl, cl):
        if v is not None:
            xs.append(float(v))
    x_min, x_max = min(xs), max(xs)
    span = max(x_max - x_min, 1e-9)
    pad = span * pad_ratio
    return x_min - pad, x_max + pad


def _add_histogram_spec_labels(
    fig: go.Figure,
    usl: float | None,
    lsl: float | None,
) -> None:
    """규격한 — 선 없이 차트 상단에 텍스트만."""
    parts: list[str] = []
    if usl is not None:
        parts.append(f"USL={usl:.4f}")
    if lsl is not None:
        parts.append(f"LSL={lsl:.4f}")
    if not parts:
        return
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=1.0,
        y=1.0,
        xanchor="right",
        yanchor="top",
        text="  ".join(parts),
        showarrow=False,
        font=dict(color="#7030A0", size=11),
    )


def _histogram_values_close(a: float, b: float, *, span: float) -> bool:
    tol = max(abs(span) * 0.01, 1e-5)
    return abs(float(a) - float(b)) <= tol


def _histogram_reference_lines(
    mean: float,
    ucl: float | None,
    lcl: float | None,
    cl: float | None,
    x_span: float,
) -> list[dict[str, Any]]:
    """히스토그램 기준선 — 겹치는 Mean/CL 병합, 라벨 위치 분리."""
    lines: list[dict[str, Any]] = []
    if ucl is not None:
        lines.append({
            "x": float(ucl),
            "label": f"UCL={ucl:.4f}",
            "color": "#d62728",
            "dash": "dash",
            "pos": "top left",
        })
    if lcl is not None:
        lines.append({
            "x": float(lcl),
            "label": f"LCL={lcl:.4f}",
            "color": "#d62728",
            "dash": "dash",
            "pos": "top right",
        })

    cl_val = float(cl) if cl is not None else None
    mean_val = float(mean)
    if cl_val is not None and _histogram_values_close(cl_val, mean_val, span=x_span):
        lines.append({
            "x": mean_val,
            "label": f"Mean/CL={mean_val:.4f}",
            "color": "#2ca02c",
            "dash": "solid",
            "pos": "top",
        })
    else:
        if cl_val is not None:
            lines.append({
                "x": cl_val,
                "label": f"CL={cl_val:.4f}",
                "color": "#2ca02c",
                "dash": "solid",
                "pos": "top",
            })
        lines.append({
            "x": mean_val,
            "label": f"Mean={mean_val:.4f}",
            "color": "#1f77b4",
            "dash": "dot",
            "pos": "bottom",
        })
    return lines


def build_histogram_figure(
    raw_values: np.ndarray,
    mean: float,
    std: float,
    *,
    ucl: float | None = None,
    lcl: float | None = None,
    cl: float | None = None,
    usl: float | None = None,
    lsl: float | None = None,
    violation_values: list[float] | None = None,
) -> go.Figure:
    """히스토그램 — X축 범위는 UCL/LCL·데이터 기준, USL/LSL은 텍스트만."""
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=raw_values, nbinsx=min(25, max(8, len(raw_values) // 4)), name="빈도"))

    x0, x1 = _histogram_x_range(raw_values, ucl, lcl, cl)
    curve_lo, curve_hi = x0, x1
    if std > 0:
        xs = np.linspace(curve_lo, curve_hi, 100)
        ys = stats.norm.pdf(xs, mean, std)
        bin_w = (x1 - x0) / min(25, max(8, len(raw_values) // 4))
        fig.add_trace(
            go.Scatter(x=xs, y=ys * len(raw_values) * bin_w, name="정규분포", line=dict(color="red"))
        )

    for line in _histogram_reference_lines(mean, ucl, lcl, cl, x1 - x0):
        fig.add_vline(
            x=line["x"],
            line_dash=line["dash"],
            line_color=line["color"],
            line_width=1.2,
            annotation_text=line["label"],
            annotation_position=line["pos"],
            annotation_font_color=line["color"],
            annotation_font_size=10,
        )

    _add_histogram_spec_labels(fig, usl, lsl)

    if violation_values:
        for i, val in enumerate(violation_values):
            fig.add_vline(
                x=val,
                line_dash="dot",
                line_color="#d62728",
                line_width=2,
                annotation_text=f"이상 {val:.4f}",
                annotation_position="bottom left" if i % 2 == 0 else "bottom right",
                annotation_font_color="#d62728",
                annotation_font_size=9,
            )

    fig.update_xaxes(range=[x0, x1], autorange=False)
    fig.update_layout(
        title="Histogram",
        xaxis_title="측정값",
        yaxis_title="빈도",
        height=400,
        margin=dict(t=64, b=56, l=48, r=24),
    )
    return fig


def build_prob_plot_figure(raw_values: np.ndarray) -> go.Figure:
    sorted_data = np.sort(raw_values)
    n = len(sorted_data)
    probs = (np.arange(1, n + 1) - 0.375) / (n + 0.25)
    theoretical = stats.norm.ppf(probs, loc=np.mean(raw_values), scale=np.std(raw_values, ddof=1))
    hover = [f"실측: {v:.4f}<br>이론분위: {t:.4f}" for v, t in zip(sorted_data, theoretical)]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=theoretical,
            y=sorted_data,
            mode="markers",
            name="데이터",
            marker=dict(size=6, color="#1f77b4"),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
        )
    )
    lims = [min(theoretical.min(), sorted_data.min()), max(theoretical.max(), sorted_data.max())]
    fig.add_trace(go.Scatter(x=lims, y=lims, mode="lines", name="이론 직선", line=dict(color="red")))
    fig.update_layout(title="Normal Probability Plot", xaxis_title="이론 분위수", yaxis_title="실측값", height=380)
    return fig
