"""원본·채취 데이터 품질 진단 — 정규성·시계열 해석 전 특이사항 탐지."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.spc.characteristic_split import normalize_split_value


@dataclass
class DataQualityFinding:
    code: str
    severity: str  # info | warning | critical
    title: str
    detail: str
    evidence: str = ""


@dataclass
class DataQualityReport:
    findings: list[DataQualityFinding] = field(default_factory=list)
    follow_up_actions: list[str] = field(default_factory=list)
    value_summary: dict = field(default_factory=dict)

    @property
    def has_issues(self) -> bool:
        return any(f.severity in ("warning", "critical") for f in self.findings)


def _value_series(df: pd.DataFrame) -> pd.Series:
    if "value" not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df["value"], errors="coerce").dropna()


def analyze_data_quality(
    sample_df: pd.DataFrame | None,
    filtered_df: pd.DataFrame | None = None,
) -> DataQualityReport:
    """채취·필터 데이터의 정규성·시계열 해석 방해 요인 진단."""
    report = DataQualityReport()
    df = sample_df if sample_df is not None and not sample_df.empty else filtered_df
    if df is None or df.empty:
        report.findings.append(
            DataQualityFinding("NO_DATA", "critical", "데이터 없음", "분석할 행이 없습니다.")
        )
        return report

    values = _value_series(df)
    if values.empty:
        report.findings.append(
            DataQualityFinding("NO_VALUE", "critical", "측정값 없음", "value 열에 유효 숫자가 없습니다.")
        )
        return report

    n = len(values)
    uniq = sorted(values.unique())
    n_uniq = len(uniq)
    rounded = values.round(2)
    n_uniq_2dp = rounded.nunique()

    report.value_summary = {
        "n": n,
        "n_unique": n_uniq,
        "n_unique_2dp": int(n_uniq_2dp),
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)) if n > 1 else 0.0,
        "top_values": rounded.value_counts().head(5).to_dict(),
    }

    # --- 측정 포인트 혼합 ---
    point_cols = [c for c in ("measurement_point", "네트 갯수", "값 갯수") if c in df.columns]
    for col in point_cols:
        pts = df[col].dropna().apply(normalize_split_value).unique()
        pts = [p for p in pts if p]
        if len(pts) >= 2:
            counts = df[col].apply(normalize_split_value).value_counts().to_dict()
            report.findings.append(
                DataQualityFinding(
                    code="MIXED_MEASUREMENT_POINTS",
                    severity="critical",
                    title="측정 포인트 혼합",
                    detail=(
                        "한 분석 묶음에 서로 다른 측정 포인트(체결부위)가 섞여 있습니다. "
                        "정규확률도에서 계단형 3~4그룹, 시계열에서 값이 왔다 갔다 하는 현상의 "
                        "가장 흔한 원인입니다."
                    ),
                    evidence=f"{col}: {counts}",
                )
            )
            report.follow_up_actions.extend([
                "사이드바에서 측정 포인트를 **하나씩** 선택해 개별 분석하세요.",
                "또는 분석 전 `네트 갯수`(측정 포인트)별로 데이터를 분리해 재실행하세요.",
            ])
            break

    # --- 이산값(반올림·저해상도) ---
    tie_ratio = 1.0 - (n_uniq / n) if n else 0.0
    if n_uniq <= max(5, n // 10) or n_uniq_2dp <= 4:
        report.findings.append(
            DataQualityFinding(
                code="DISCRETE_VALUES",
                severity="warning",
                title="이산(계단형) 측정값",
                detail=(
                    f"고유값 {n_uniq}개(소수 2자리 기준 {n_uniq_2dp}개)로, "
                    "정규확률도에서 수평 계단(3~4단)이 나타날 수 있습니다. "
                    "측정 장비 해상도·반올림·디지털 눈금이 원인인 경우가 많습니다."
                ),
                evidence=f"주요 값: {list(report.value_summary['top_values'].keys())[:6]}",
            )
        )
        report.follow_up_actions.extend([
            "측정 시스템 해상도(최소 눈금)와 MES 반올림 자릿수를 확인하세요.",
            "정규성 검정보다 **개별 포인트·시간순 추이**로 이상 여부를 판단하는 것이 적절할 수 있습니다.",
            "공정능력은 Cp/Cpk보다 **Pp/Ppk·규격 내 비율** 해석을 우선 검토하세요.",
        ])

    # --- 시계열 정렬 ---
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], errors="coerce")
        if ts.notna().sum() >= 3:
            order_idx = ts.sort_values().index
            row_order = list(df.index)
            if list(order_idx) != row_order:
                report.findings.append(
                    DataQualityFinding(
                        code="TIME_ORDER_MISMATCH",
                        severity="warning",
                        title="시간순 정렬 아님",
                        detail=(
                            "채취 표본이 시간순이 아닙니다(서브그룹 랜덤 채취 등). "
                            "시계열 차트에 선을 연결하면 날짜가 뒤섞여 보일 수 있습니다."
                        ),
                        evidence="행 순서 ≠ timestamp 오름차순",
                    )
                )
                report.follow_up_actions.append(
                    "개별값 시계열은 **시간순 정렬 후** 해석하세요(차트는 자동 정렬 적용됨)."
                )

    # --- 다봉(포인트별 평균 차이) ---
    if not any(f.code == "MIXED_MEASUREMENT_POINTS" for f in report.findings) and n_uniq_2dp >= 3:
        vc = rounded.value_counts()
        if len(vc) >= 3 and vc.iloc[0] / n > 0.15:
            report.findings.append(
                DataQualityFinding(
                    code="MULTIMODAL_CLUSTERS",
                    severity="warning",
                    title="다봉(복수 집단) 분포",
                    detail=(
                        "값이 소수의 수준(예: 1.16 / 1.17 / 1.18)에 몰려 있어 "
                        "단일 정규분포 가정이 맞지 않을 수 있습니다. "
                        "공정·설비·측정 포인트·시간대별 평균 차이를 의심하세요."
                    ),
                    evidence=str(dict(vc.head(4))),
                )
            )
            report.follow_up_actions.extend([
                "공정·LOT·설비·측정 포인트별 평균·산포를 교차 비교하세요.",
                "특정 수준으로만 몰린 값이 규격 경계(반올림)에 가깝다면 측정/판정 방식을 점검하세요.",
            ])

    if not report.follow_up_actions and not report.has_issues:
        report.follow_up_actions.append("특이 패턴 없음 — 정규성·관리도 해석을 그대로 진행할 수 있습니다.")

    report.follow_up_actions = list(dict.fromkeys(report.follow_up_actions))
    return report
