"""Matplotlib 한글 폰트 설정 (Windows Malgun Gothic)."""
from __future__ import annotations

import platform
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager


def setup_minitab_font() -> str:
    """Minitab 스타일 차트용 폰트. 반환: 사용 폰트명."""
    font_name = "DejaVu Sans"
    if platform.system() == "Windows":
        candidates = [
            Path(r"C:\Windows\Fonts\malgun.ttf"),
            Path(r"C:\Windows\Fonts\malgunbd.ttf"),
        ]
        for fp in candidates:
            if fp.exists():
                font_manager.fontManager.addfont(str(fp))
                font_name = font_manager.FontProperties(fname=str(fp)).get_name()
                break

    plt.rcParams.update({
        "font.family": font_name,
        "axes.unicode_minus": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#333333",
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7,
        "grid.color": "#E0E0E0",
        "grid.linewidth": 0.6,
    })
    return font_name
