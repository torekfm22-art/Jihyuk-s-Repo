"""
X-Y 매트릭스 파레토 차트 생성 (클래식 막대 + 누적선 + 80% 기준).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.spc.font_setup import setup_minitab_font

PARETO_BAR_KEY = "#4A7EBB"
PARETO_BAR_80 = "#2E7D32"
PARETO_BAR_OTHER = "#B0BEC5"
CUM_LINE = "#C0392B"
LINE_80 = "#1565C0"


def plot_pareto_chart(
    pareto_df: pd.DataFrame,
    output_path: str | Path,
    title: str = "X-Y 매트릭스 파레토 분석",
    subtitle: str | None = None,
    dpi: int = 140,
) -> Path:
    """
    클래식 파레토: 점수 내림차순 막대, 누적 % 꺾은선, 80% 기준선, 80% 구간 강조.
    """
    setup_minitab_font()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    x_col = "X 인자명" if "X 인자명" in pareto_df.columns else pareto_df.columns[0]
    df = pareto_df.copy()
    if "순위" not in df.columns:
        df.insert(0, "순위", range(1, len(df) + 1))

    labels = df[x_col].astype(str).tolist()
    scores = df["score"].to_numpy(dtype=float)
    cum = df["cumulative_pct"].to_numpy(dtype=float)
    p80 = (
        df["pareto_80"].to_numpy()
        if "pareto_80" in df.columns
        else np.ones(len(df), dtype=bool)
    )

    n = len(labels)
    x_pos = np.arange(n)

    fig, ax1 = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor("white")

    colors = [
        PARETO_BAR_80 if bool(p80[i]) and scores[i] > 0 else PARETO_BAR_OTHER
        for i in range(n)
    ]
    bars = ax1.bar(
        x_pos,
        scores,
        color=colors,
        edgecolor="#37474F",
        linewidth=0.6,
        zorder=2,
        label="점수",
    )
    ax1.set_ylabel("점수 (1·3·9)", fontsize=10, fontweight="bold")
    ax1.set_xlabel("X 인자", fontsize=10)
    ax1.set_xticks(x_pos)
    ax1.set_xticklabels(labels, rotation=40, ha="right", fontsize=9)
    ax1.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    ax1.set_axisbelow(True)

    full_title = title
    if subtitle:
        full_title = f"{title}\n{subtitle}"
    ax1.set_title(full_title, fontsize=12, fontweight="bold", pad=12)

    ax2 = ax1.twinx()
    ax2.plot(
        x_pos,
        cum,
        color=CUM_LINE,
        marker="o",
        markersize=6,
        linewidth=2.2,
        label="누적 기여 (%)",
        zorder=4,
    )
    ax2.axhline(80, color=LINE_80, linestyle="--", linewidth=1.5, label="80% 기준", zorder=3)
    ax2.fill_between(x_pos, 0, 80, alpha=0.06, color=LINE_80, zorder=1)
    ax2.set_ylabel("누적 기여 (%)", fontsize=10, fontweight="bold")
    ax2.set_ylim(0, 105)

    for i, (bar, val, cump) in enumerate(zip(bars, scores, cum)):
        if val > 0:
            ax1.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.15,
                str(int(val)),
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )
        ax2.annotate(
            f"{cump:.0f}%",
            (i, cump),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=8,
            color=CUM_LINE,
        )

    if p80.any() and scores.sum() > 0:
        last_ix = int(np.where(p80)[0][-1])
        ax1.axvline(last_ix + 0.5, color=PARETO_BAR_80, linestyle=":", linewidth=1.2, alpha=0.8)

    lines1, lab1 = ax1.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, lab1 + lab2, loc="upper right", fontsize=8, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path
