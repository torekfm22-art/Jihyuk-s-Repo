"""공장별 기본 정보 설정 모델."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from quality_mh.models import RoundingPolicy

PLANT_PRESETS = [
    "김천램프",
    "김천에어백",
    "천안EBS",
    "충주1공장",
    "평택PE",
    "사용자 정의",
]

WORK_HOUR_PRESETS = [10.0, 9.33, 9.23, 8.0]
ALLOWANCE_PRESETS = [0.05, 0.10, 0.15, 0.20]
SHIFT_TYPES = ["주간", "2교대", "3교대"]
WG_CATEGORIES = ["입고", "공정", "완성", "시험", "정성", "표준외"]


class PlantConfig(BaseModel):
    plant_name: str = "김천램프"
    analysis_year: int = 2025
    work_hours_per_day: float = 10.0
    working_days_per_month: float = 20.0
    working_months: float = 12.0
    allowance_rate: float = 0.10
    monthly_production: list[float] = Field(default_factory=lambda: [0.0] * 12)
    current_headcount: dict[str, float] = Field(
        default_factory=lambda: {cat: 0.0 for cat in WG_CATEGORIES}
    )
    non_standard_headcount: dict[str, float] = Field(
        default_factory=lambda: {"그룹장": 0.0, "파트장": 0.0, "지원조": 0.0}
    )
    shift_type: Literal["주간", "2교대", "3교대"] = "주간"
    rounding_policy: RoundingPolicy = RoundingPolicy.STANDARD
    use_even_shift_rounding: bool = False

    @property
    def annual_production(self) -> float:
        return sum(self.monthly_production)

    @property
    def work_hours_per_month(self) -> float:
        return self.work_hours_per_day * self.working_days_per_month

    @property
    def work_hours_per_year(self) -> float:
        return self.work_hours_per_month * self.working_months

    def effective_rounding_policy(self) -> RoundingPolicy:
        if self.use_even_shift_rounding or self.shift_type in ("2교대", "3교대"):
            return RoundingPolicy.EVEN_SHIFT
        return self.rounding_policy

    def calc_params(self) -> dict:
        return {
            "calc_unit": "월",
            "work_hours_per_month": self.work_hours_per_month,
            "work_hours_per_year": self.work_hours_per_year,
        }
