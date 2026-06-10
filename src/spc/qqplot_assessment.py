"""QQ plot 정규성 시각 해석 훅 (확장용 인터페이스)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


@dataclass
class QqPlotAssessment:
    """정규확률도 기반 정규성 시각 평가."""

    supported: bool
    fit_r2: float | None
    assessment: str
    state_hint: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "fit_r2": self.fit_r2,
            "assessment": self.assessment,
            "state_hint": self.state_hint,
            "message": self.message,
        }


def assess_qq_plot(data: np.ndarray) -> QqPlotAssessment:
    """
    QQ plot 자동 판정 placeholder.

    향후 이미지 분석·회귀 기반 자동 판정으로 확장 가능.
    현재는 Blom plotting position + R² 기반 휴리스틱.
    """
    x = np.asarray(data, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)

    if n < 3:
        return QqPlotAssessment(
            supported=False,
            fit_r2=None,
            assessment="undetermined",
            state_hint="undetermined",
            message="표본수 부족으로 QQ plot 해석 불가",
        )

    sorted_x = np.sort(x)
    probs = (np.arange(1, n + 1) - 0.375) / (n + 0.25)
    theoretical = stats.norm.ppf(probs, loc=np.mean(x), scale=np.std(x, ddof=1))

    if np.std(theoretical) < 1e-12:
        r2 = 0.0
    else:
        r = np.corrcoef(theoretical, sorted_x)[0, 1]
        r2 = float(r * r)

    if r2 >= 0.97:
        assessment = "linear_fit_good"
        state_hint = "normal"
        message = f"정규확률도 직선성 양호(R²≈{r2:.3f})"
    elif r2 >= 0.93:
        assessment = "moderate_deviation"
        state_hint = "borderline_non_normal"
        message = f"정규확률도에서 미세 이탈(R²≈{r2:.3f}) — 꼬리·이상치 검토"
    else:
        assessment = "poor_fit"
        state_hint = "clearly_non_normal"
        message = f"정규확률도 직선성 저하(R²≈{r2:.3f}) — 비정규 가능성 높음"

    return QqPlotAssessment(
        supported=True,
        fit_r2=r2,
        assessment=assessment,
        state_hint=state_hint,
        message=message,
    )


def calculate_machine_capability(
    data: np.ndarray,
    usl: float | None,
    lsl: float | None,
) -> dict[str, Any]:
    """기계 성능(Cm/Cmk) 계산 인터페이스 — 미구현 확장 포인트."""
    return {
        "supported": False,
        "message": "Cm/Cmk calculation module not implemented yet.",
        "cm": None,
        "cmk": None,
    }
