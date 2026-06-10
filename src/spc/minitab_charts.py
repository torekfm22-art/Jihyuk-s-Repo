"""Minitab 스타일 SPC 차트 생성."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

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
    data: np.ndarray, usl: float, lsl: float, mean: float, std: float, path: Path
) -> Path:
    setup_minitab_font()
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    bins = min(25, max(8, len(data) // 4))
    ax.hist(data, bins=bins, color="#B8D4E8", edgecolor=MT_BLUE, linewidth=0.8, density=True, alpha=0.9)

    x = np.linspace(data.min() - std, data.max() + std, 200)
    if std > 0:
        ax.plot(x, stats.norm.pdf(x, mean, std), color=MT_RED, linewidth=1.8, label="정규분포")

    ax.axvline(usl, color=MT_RED, linestyle="--", linewidth=1.2, label=f"USL={usl:g}")
    ax.axvline(lsl, color=MT_RED, linestyle="--", linewidth=1.2, label=f"LSL={lsl:g}")
    ax.axvline(mean, color=MT_GREEN, linestyle="-", linewidth=1.2, label=f"Mean={mean:.4f}")
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


def _draw_control_panel(ax, x, y, cl, ucl, lcl, ylabel: str):
    ax.plot(x, y, "o-", color=MT_BLUE, markersize=3.5, linewidth=0.9)
    ax.axhline(cl, color=MT_GREEN, linewidth=1.2, label=f"CL={cl:.4f}")
    ax.axhline(ucl, color=MT_RED, linestyle="--", linewidth=1.0, label=f"UCL={ucl:.4f}")
    ax.axhline(lcl, color=MT_RED, linestyle="--", linewidth=1.0, label=f"LCL={lcl:.4f}")
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, linestyle="-", alpha=0.7)
    ax.legend(loc="upper right", fontsize=7, framealpha=0.9)


def plot_xbar_s_minitab(result: SpcAnalysisResult, path: Path) -> Path:
    setup_minitab_font()
    limits = result.control_limits
    df = result.subgroup_stats
    x = df["subgroup"].to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 4.5), sharex=True)
    _draw_control_panel(
        axes[0], x, df["Xbar"].to_numpy(),
        limits.xbar_limits["CL"], limits.xbar_limits["UCL"], limits.xbar_limits["LCL"], "Xbar",
    )
    axes[0].set_title("14. Xbar-S Control Chart", fontsize=10, fontweight="bold")
    _draw_control_panel(
        axes[1], x, df["S"].to_numpy(),
        limits.s_limits["CL"], limits.s_limits["UCL"], limits.s_limits["LCL"], "S",
    )
    axes[1].set_xlabel("Subgroup", fontsize=9)
    fig.tight_layout()
    return _save(fig, path)


def plot_xbar_r_minitab(result: SpcAnalysisResult, path: Path) -> Path:
    setup_minitab_font()
    limits = result.control_limits
    df = result.subgroup_stats
    x = df["subgroup"].to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 4.5), sharex=True)
    _draw_control_panel(
        axes[0], x, df["Xbar"].to_numpy(),
        limits.xbar_limits["CL"], limits.xbar_limits["UCL"], limits.xbar_limits["LCL"], "Xbar",
    )
    axes[0].set_title("14. Xbar-R Control Chart", fontsize=10, fontweight="bold")
    _draw_control_panel(
        axes[1], x, df["R"].to_numpy(),
        limits.r_limits["CL"], limits.r_limits["UCL"], limits.r_limits["LCL"], "R",
    )
    axes[1].set_xlabel("Subgroup", fontsize=9)
    fig.tight_layout()
    return _save(fig, path)


def plot_imr_minitab(result: SpcAnalysisResult, path: Path) -> Path:
    setup_minitab_font()
    limits = result.control_limits
    df = result.individual_stats
    x = df["point"].to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 4.5), sharex=True)
    _draw_control_panel(
        axes[0], x, df["I"].to_numpy(),
        limits.i_limits["CL"], limits.i_limits["UCL"], limits.i_limits["LCL"], "I",
    )
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
    usl: float,
    lsl: float,
    output_dir: Path,
    prefix: str,
) -> ChartPaths:
    mean = float(np.mean(raw_data))
    std = float(np.std(raw_data, ddof=1)) if len(raw_data) > 1 else 0.0
    d = output_dir

    if result.chart_type == "xbar_s":
        ctrl = plot_xbar_s_minitab(result, d / f"{prefix}_control.png")
    elif result.chart_type == "xbar_r":
        ctrl = plot_xbar_r_minitab(result, d / f"{prefix}_control.png")
    else:
        ctrl = plot_imr_minitab(result, d / f"{prefix}_control.png")

    return ChartPaths(
        histogram=plot_histogram_minitab(raw_data, usl, lsl, mean, std, d / f"{prefix}_histogram.png"),
        raw_chart=plot_raw_values(raw_data, mean, d / f"{prefix}_raw.png"),
        prob_plot=plot_probability_normal(raw_data, d / f"{prefix}_probplot.png"),
        control_chart=ctrl,
    )
