"""Non-normal Pp/Ppk — 데이터 검증용 Excel 수식·동치 계산."""
from __future__ import annotations

import numpy as np

from src.spc.non_normal_capability import percentile_capability


def non_normal_metrics_from_values(
    values: np.ndarray,
    usl: float | None,
    lsl: float | None,
):
    """percentile 기반 Non-normal 지표 (프로그램과 동일)."""
    return percentile_capability(values, usl, lsl)


def excel_non_normal_ppk_formula(
    sample_rng: str,
    usl_ref: str,
    lsl_ref: str,
    *,
    spec_type: str = "two_sided",
) -> str:
    """영문 Excel — 경험적 이탈 확률 → Z → Ppk_nn."""
    n = f"COUNT({sample_rng})"
    pa = f"COUNTIF({sample_rng},\">=\"&{usl_ref})/{n}"
    eps = f"0.5/{n}"
    pa_c = f"MAX({eps},MIN({pa},1-{eps}))"
    z_u = f"ABS(_xlfn.NORM.S.INV({pa_c}))"
    if spec_type == "upper_only":
        return z_u
    pb = f"COUNTIF({sample_rng},\"<=\"&{lsl_ref})/{n}"
    pb_c = f"MAX({eps},MIN({pb},1-{eps}))"
    z_l = f"ABS(_xlfn.NORM.S.INV({pb_c}))"
    if spec_type == "lower_only":
        return z_l
    return f"MIN({z_l},{z_u})"


def excel_non_normal_pp_formula(
    sample_rng: str,
    usl_ref: str,
    lsl_ref: str,
    *,
    spec_type: str = "two_sided",
) -> str:
    """영문 Excel — Z 평균 vs 백분위 spread Pp."""
    n = f"COUNT({sample_rng})"
    eps = f"0.5/{n}"
    pa = f"COUNTIF({sample_rng},\">=\"&{usl_ref})/{n}"
    pa_c = f"MAX({eps},MIN({pa},1-{eps}))"
    z_u = f"ABS(_xlfn.NORM.S.INV({pa_c}))"
    spread = (
        f"_xlfn.PERCENTILE.INC({sample_rng},0.99865)"
        f"-_xlfn.PERCENTILE.INC({sample_rng},0.00135)"
    )
    if spec_type == "upper_only":
        return z_u
    pb = f"COUNTIF({sample_rng},\"<=\"&{lsl_ref})/{n}"
    pb_c = f"MAX({eps},MIN({pb},1-{eps}))"
    z_l = f"ABS(_xlfn.NORM.S.INV({pb_c}))"
    if spec_type == "lower_only":
        return z_l
    pp_z = f"({z_l}+{z_u})/2"
    pp_pct = f"IF({spread}=0,0,({usl_ref}-{lsl_ref})/{spread})"
    return f"MAX({pp_z},{pp_pct})"
