"""SPC 관리도 차트 생성 (matplotlib)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.spc.statistics import ControlLimits, SpcAnalysisResult

# 한글 폰트 (Windows)
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def _draw_limits(ax, cl: float, ucl: float, lcl: float, title: str, ylabel: str, x: np.ndarray, y: np.ndarray):
    ax.plot(x, y, "o-", color="#2563eb", markersize=5, linewidth=1.2, label="측정값")
    ax.axhline(cl, color="#16a34a", linestyle="-", linewidth=1.5, label=f"CL={cl:.4f}")
    ax.axhline(ucl, color="#dc2626", linestyle="--", linewidth=1.2, label=f"UCL={ucl:.4f}")
    ax.axhline(lcl, color="#dc2626", linestyle="--", linewidth=1.2, label=f"LCL={lcl:.4f}")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)


def plot_xbar_r(result: SpcAnalysisResult, output_path: Path, title_prefix: str = "") -> Path:
    limits = result.control_limits
    df = result.subgroup_stats
    x = df["subgroup"].to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    prefix = f"{title_prefix} " if title_prefix else ""

    _draw_limits(
        axes[0], limits.xbar_limits["CL"], limits.xbar_limits["UCL"], limits.xbar_limits["LCL"],
        f"{prefix}Xbar 관리도", "Xbar", x, df["Xbar"].to_numpy(),
    )
    _draw_limits(
        axes[1], limits.r_limits["CL"], limits.r_limits["UCL"], limits.r_limits["LCL"],
        f"{prefix}R 관리도", "R", x, df["R"].to_numpy(),
    )
    axes[1].set_xlabel("Subgroup")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_imr(result: SpcAnalysisResult, output_path: Path, title_prefix: str = "") -> Path:
    limits = result.control_limits
    df = result.individual_stats
    x = df["point"].to_numpy()
    prefix = f"{title_prefix} " if title_prefix else ""

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    _draw_limits(
        axes[0], limits.i_limits["CL"], limits.i_limits["UCL"], limits.i_limits["LCL"],
        f"{prefix}I 관리도 (개별값)", "I", x, df["I"].to_numpy(),
    )
    mr = df["MR"].to_numpy()
    mr_valid = mr[~np.isnan(mr)]
    x_mr = x[~np.isnan(mr)]
    _draw_limits(
        axes[1], limits.mr_limits["CL"], limits.mr_limits["UCL"], 0.0,
        f"{prefix}MR 관리도 (이동범위)", "MR", x_mr, mr_valid,
    )
    axes[1].set_xlabel("Point")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_capability_histogram(
    data: np.ndarray,
    usl: float,
    lsl: float,
    mean: float,
    output_path: Path,
    title: str = "공정능력 히스토그램",
) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(data, bins=min(30, max(10, len(data) // 5)), color="#93c5fd", edgecolor="#1e40af", alpha=0.85)
    ax.axvline(usl, color="#dc2626", linestyle="--", linewidth=2, label=f"USL={usl}")
    ax.axvline(lsl, color="#dc2626", linestyle="--", linewidth=2, label=f"LSL={lsl}")
    ax.axvline(mean, color="#16a34a", linestyle="-", linewidth=2, label=f"Mean={mean:.4f}")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("측정값")
    ax.set_ylabel("빈도")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path
