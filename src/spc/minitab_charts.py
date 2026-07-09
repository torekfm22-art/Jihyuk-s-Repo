"""Minitab 스타일 SPC 차트 생성."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from src.spc.chart_sigma_zones import iter_sigma_zone_lines
from src.spc.constants import MT_BLUE, MT_GREEN, MT_RED
from src.spc.font_setup import setup_minitab_font
from src.spc.statistics import SpcAnalysisResult


@dataclass
class ChartPaths:
    histogram: Path
    raw_chart: Path
    prob_plot: Path
    control_chart: Path


def _style_axes(ax, title: str, xlabel: str = "", ylabel: str = ""):
    ax.set_title(title, fontsize=10, fontweight="bold", pad=6)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, linestyle="-", alpha=0.7)
    for spine in ax.spines.values():
        spine.set_color("#333333")


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def plot_histogram_minitab(
    data: np.ndarray,
    mean: float,
    std: float,
    path: Path,
    *,
    ucl: float | None = None,
    lcl: float | None = None,
    cl: float | None = None,
    usl: float | None = None,
    lsl: float | None = None,
) -> Path:
    setup_minitab_font()
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    bins = min(25, max(8, len(data) // 4))
    ax.hist(data, bins=bins, color="#B8D4E8", edgecolor=MT_BLUE, linewidth=0.8, density=True, alpha=0.9)

    xs = [float(data.min()), float(data.max())]
    for v in (ucl, lcl, cl):
        if v is not None:
            xs.append(float(v))
    x_min, x_max = min(xs), max(xs)
    span = max(x_max - x_min, 1e-9)
    pad = span * 0.12
    x0, x1 = x_min - pad, x_max + pad

    x = np.linspace(x0, x1, 200)
    if std > 0:
        ax.plot(x, stats.norm.pdf(x, mean, std), color=MT_RED, linewidth=1.8, label="정규분포")

    for val, label, color, ls in (
        (ucl, "UCL", MT_RED, "--"),
        (lcl, "LCL", MT_RED, "--"),
        (cl, "CL", MT_GREEN, "-"),
        (mean, "Mean", MT_GREEN, "-"),
    ):
        if val is not None:
            ax.axvline(val, color=color, linestyle=ls, linewidth=1.2, label=f"{label}={val:.4f}")

    spec_parts: list[str] = []
    if usl is not None:
        spec_parts.append(f"USL={usl:g}")
    if lsl is not None:
        spec_parts.append(f"LSL={lsl:g}")
    if spec_parts:
        ax.text(0.98, 0.98, "  ".join(spec_parts), transform=ax.transAxes,
                ha="right", va="top", fontsize=8, color="#7030A0")

    ax.set_xlim(x0, x1)
    _style_axes(ax, "11. Histogram", "측정값", "밀도")
    ax.legend(loc="upper right", framealpha=0.9)
    return _save(fig, path)


def plot_raw_values(data: np.ndarray, mean: float, path: Path) -> Path:
    setup_minitab_font()
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    x = np.arange(1, len(data) + 1)
    ax.plot(x, data, "o-", color=MT_BLUE, markersize=3, linewidth=0.9, markerfacecolor=MT_BLUE)
    ax.axhline(mean, color=MT_GREEN, linestyle="-", linewidth=1.2, label=f"Mean={mean:.4f}")
    _style_axes(ax, "12. Raw Value Chart", "순번", "측정값")
    ax.legend(loc="best")
    return _save(fig, path)


def plot_probability_normal(data: np.ndarray, path: Path) -> Path:
    setup_minitab_font()
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    sorted_data = np.sort(data)
    n = len(sorted_data)
    probs = (np.arange(1, n + 1) - 0.375) / (n + 0.25)
    theoretical = stats.norm.ppf(probs, loc=np.mean(data), scale=np.std(data, ddof=1))

    ax.plot(theoretical, sorted_data, "o", color=MT_BLUE, markersize=3.5, label="데이터")
    lims = [min(theoretical.min(), sorted_data.min()), max(theoretical.max(), sorted_data.max())]
    ax.plot(lims, lims, color=MT_RED, linestyle="-", linewidth=1.2, label="이론 정규선")
    _style_axes(ax, "13. Normal Probability Plot", "이론 분위수", "실측값")
    ax.legend(loc="best")
    return _save(fig, path)


def _draw_sigma_zones(ax, cl: float, ucl: float, lcl: float) -> None:
    for y_val, label in iter_sigma_zone_lines(cl, ucl, lcl):
        ax.axhline(
            y_val,
            color="#9ca3af",
            linestyle=":",
            linewidth=0.8,
            alpha=0.85,
            zorder=1,
        )



def _draw_control_panel(ax, x, y, cl, ucl, lcl, ylabel: str):
    _draw_sigma_zones(ax, cl, ucl, lcl)
    ax.plot(x, y, "o-", color=MT_BLUE, markersize=3.5, linewidth=0.9, zorder=3)
    ax.axhline(cl, color=MT_GREEN, linewidth=1.2, label=f"CL={cl:.4f}")
    ax.axhline(ucl, color=MT_RED, linestyle="--", linewidth=1.0, label=f"UCL={ucl:.4f}")
    ax.axhline(lcl, color=MT_RED, linestyle="--", linewidth=1.0, label=f"LCL={lcl:.4f}")
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, linestyle="-", alpha=0.7)
    ax.legend(loc="upper right", fontsize=7, framealpha=0.9)


def plot_xbar_s_minitab(
    result: SpcAnalysisResult,
    path: Path,
) -> Path:
    setup_minitab_font()
    limits = result.control_limits
    df = result.subgroup_stats
    x = df["subgroup"].to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 4.5), sharex=True)
    _draw_control_panel(
        axes[0], x, df["Xbar"].to_numpy(),
        limits.xbar_limits["CL"], limits.xbar_limits["UCL"], limits.xbar_limits["LCL"], "Xbar",
    )
    axes[0].legend(loc="upper right", fontsize=7, framealpha=0.9)
    axes[0].set_title("14. Xbar-S Control Chart", fontsize=10, fontweight="bold")
    _draw_control_panel(
        axes[1], x, df["S"].to_numpy(),
        limits.s_limits["CL"], limits.s_limits["UCL"], limits.s_limits["LCL"], "S",
    )
    axes[1].set_xlabel("Subgroup", fontsize=9)
    fig.tight_layout()
    return _save(fig, path)


def plot_xbar_r_minitab(
    result: SpcAnalysisResult,
    path: Path,
) -> Path:
    setup_minitab_font()
    limits = result.control_limits
    df = result.subgroup_stats
    x = df["subgroup"].to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 4.5), sharex=True)
    _draw_control_panel(
        axes[0], x, df["Xbar"].to_numpy(),
        limits.xbar_limits["CL"], limits.xbar_limits["UCL"], limits.xbar_limits["LCL"], "Xbar",
    )
    axes[0].legend(loc="upper right", fontsize=7, framealpha=0.9)
    axes[0].set_title("14. Xbar-R Control Chart", fontsize=10, fontweight="bold")
    _draw_control_panel(
        axes[1], x, df["R"].to_numpy(),
        limits.r_limits["CL"], limits.r_limits["UCL"], limits.r_limits["LCL"], "R",
    )
    axes[1].set_xlabel("Subgroup", fontsize=9)
    fig.tight_layout()
    return _save(fig, path)


def plot_imr_minitab(
    result: SpcAnalysisResult,
    path: Path,
) -> Path:
    setup_minitab_font()
    limits = result.control_limits
    df = result.individual_stats
    x = df["point"].to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 4.5), sharex=True)
    _draw_control_panel(
        axes[0], x, df["I"].to_numpy(),
        limits.i_limits["CL"], limits.i_limits["UCL"], limits.i_limits["LCL"], "I",
    )
    axes[0].legend(loc="upper right", fontsize=7, framealpha=0.9)
    axes[0].set_title("14. I-MR Control Chart", fontsize=10, fontweight="bold")
    mr = df["MR"].to_numpy()
    valid = ~np.isnan(mr)
    _draw_control_panel(
        axes[1], x[valid], mr[valid],
        limits.mr_limits["CL"], limits.mr_limits["UCL"], 0.0, "MR",
    )
    axes[1].set_xlabel("Point", fontsize=9)
    fig.tight_layout()
    return _save(fig, path)


def generate_all_minitab_charts(
    result: SpcAnalysisResult,
    raw_data: np.ndarray,
    usl: float | None,
    lsl: float | None,
    output_dir: Path,
    prefix: str,
) -> ChartPaths:
    mean = float(np.mean(raw_data))
    std = float(np.std(raw_data, ddof=1)) if len(raw_data) > 1 else 0.0
    d = output_dir

    i_lim = result.control_limits.i_limits
    if i_lim:
        hist_ucl, hist_cl, hist_lcl = i_lim["UCL"], i_lim["CL"], i_lim["LCL"]
    else:
        from src.spc.statistics import SpcAnalyzer
        imr = SpcAnalyzer().imr_limits(raw_data)
        hist_ucl, hist_cl, hist_lcl = imr.i_limits["UCL"], imr.i_limits["CL"], imr.i_limits["LCL"]

    if result.chart_type == "xbar_s":
        ctrl = plot_xbar_s_minitab(result, d / f"{prefix}_control.png")
    elif result.chart_type == "xbar_r":
        ctrl = plot_xbar_r_minitab(result, d / f"{prefix}_control.png")
    else:
        ctrl = plot_imr_minitab(result, d / f"{prefix}_control.png")

    return ChartPaths(
        histogram=plot_histogram_minitab(
            raw_data, mean, std, d / f"{prefix}_histogram.png",
            ucl=hist_ucl, lcl=hist_lcl, cl=hist_cl, usl=usl, lsl=lsl,
        ),
        raw_chart=plot_raw_values(raw_data, mean, d / f"{prefix}_raw.png"),
        prob_plot=plot_probability_normal(raw_data, d / f"{prefix}_probplot.png"),
        control_chart=ctrl,
    )
