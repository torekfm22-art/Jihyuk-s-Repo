"""SPC 판정 정책 설정 로드."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from config.app_paths import get_project_root

StageType = Literal[
    "development",
    "pilot",
    "pre_mass_production",
    "mass_production",
]


@dataclass
class SpcPolicyConfig:
    """회사 SPC 판정 기준."""

    subgroup_min_groups: int = 25
    recommended_subgroup_sizes: list[int] = field(default_factory=lambda: [3, 4, 5])
    cp_cpk_threshold: float = 1.33
    pp_ppk_threshold: float = 1.67
    run_rule_points: int = 7
    trend_rule_points: int = 7
    center_cluster_pct: float = 0.90
    high_dispersion_pct: float = 0.40
    allow_tool_wear_trend: bool = False
    allow_customer_run: bool = False
    near_limit_2of3: bool = True
    near_limit_4of7: bool = True
    strict_company_mode: bool = True
    advanced_spc_mode: bool = False
    aiag_vda_mode: bool = True
    enable_customer_exception_rule: bool = True
    normality_borderline_p: float = 0.05
    normality_clearly_non_normal_p: float = 0.01
    pre_control_subgroup_max: int = 2
    machine_capability_recommended_stages: list[str] = field(
        default_factory=lambda: ["development", "pilot", "pre_mass_production"]
    )

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> "SpcPolicyConfig":
        if path is None:
            path = get_project_root() / "config" / "spc_policy.yaml"
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def capability_thresholds(self, stage: StageType) -> tuple[float, float]:
        """단계별 (폭 지수 기준, 중심 지수 기준) 반환."""
        if stage == "mass_production":
            return self.cp_cpk_threshold, self.cp_cpk_threshold
        return self.pp_ppk_threshold, self.pp_ppk_threshold

    def interpret_config(self) -> "SpcInterpretConfig":
        from src.spc.spc_interpreter import config_from_rules_catalog

        return config_from_rules_catalog()

    def primary_capability_metrics(self, stage: StageType) -> tuple[str, str]:
        """단계별 주 평가 지수 (폭, 중심)."""
        if stage == "mass_production":
            return "Cp", "Cpk"
        return "Pp", "Ppk"
