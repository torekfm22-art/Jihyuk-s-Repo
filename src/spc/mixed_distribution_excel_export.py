"""혼합분포 재구성 결과 — 5시트 Excel보내기."""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from src.spc.mixed_distribution_stratification import (
    GroupMetrics,
    StratificationCandidateResult,
    StratificationStudyResult,
)

logger = logging.getLogger(__name__)

SHEET_ORIGINAL = "Original_Data"
SHEET_SUMMARY = "Split_Summary"
SHEET_RECON = "Reconstructed"
SHEET_SG_STATS = "Subgroup_Stats"
SHEET_SPC = "SPC_Summary"


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    drop_cols = [c for c in out.columns if str(c).startswith("_")]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            ts = pd.to_datetime(out[col], errors="coerce")
            if getattr(ts.dt, "tz", None) is not None:
                ts = ts.dt.tz_localize(None)
            out[col] = ts.dt.strftime("%Y-%m-%d %H:%M:%S")
    return out.where(pd.notnull(out), None)


def build_subgroup_stats_df(reconstructed: pd.DataFrame) -> pd.DataFrame:
    if reconstructed is None or reconstructed.empty:
        return pd.DataFrame(columns=["split_key", "subgroup_id", "n", "Xbar", "S", "R"])
    split_col = "split_key" if "split_key" in reconstructed.columns else "strat_group_key"
    if "subgroup_id" not in reconstructed.columns:
        return pd.DataFrame(columns=["split_key", "subgroup_id", "n", "Xbar", "S", "R"])
    rows: list[dict[str, Any]] = []
    for (sk, sg_id), grp in reconstructed.groupby([split_col, "subgroup_id"], dropna=False):
        vals = pd.to_numeric(grp["value"], errors="coerce").dropna().to_numpy(dtype=float)
        if len(vals) == 0:
            continue
        rows.append({
            "split_key": sk,
            "subgroup_id": int(sg_id),
            "n": len(vals),
            "Xbar": float(np.mean(vals)),
            "S": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
            "R": float(np.max(vals) - np.min(vals)),
        })
    return pd.DataFrame(rows)


def _group_to_spc_row(g: GroupMetrics) -> dict[str, Any]:
    return {
        "split_key": g.group_key,
        "n": g.n,
        "mean": g.mean,
        "sigma_overall": g.stdev_s,
        "sigma_within": g.sigma_within,
        "sigma_ratio": g.sigma_ratio,
        "normality_p_value": g.normality_p,
        "Ppk": g.ppk,
        "Cpk": g.cpk,
        "R/S 관리도 이상": "Y" if g.rs_abnormal else "N",
        "Xbar 관리도 이상": "Y" if g.xbar_abnormal else "N",
    }


def build_split_summary_df(study: StratificationStudyResult) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for c in study.candidates:
        rows.append({
            "순위": c.rank,
            "분리 기준": c.split_basis,
            "그룹 수": c.group_count,
            "정규성 만족 비율": f"{c.normal_group_ratio:.0%}",
            "평균 sigma_ratio": c.mean_sigma_ratio,
            "그룹 평균 차이": c.mean_shift_range,
            "최저 Ppk": c.min_ppk,
            "추천 점수": c.total_score,
            "추천 판단": c.recommendation_judgment,
        })
    return pd.DataFrame(rows)


def prepare_reconstructed_export_df(reconstructed: pd.DataFrame) -> pd.DataFrame:
    out = _sanitize_df(reconstructed)
    if "strat_group_key" in out.columns and "split_key" not in out.columns:
        out = out.rename(columns={"strat_group_key": "split_key"})
    if "original_index" not in out.columns:
        out["original_index"] = out.index
    cols_pref = ["split_key", "subgroup_id", "timestamp", "value", "original_index"]
    front = [c for c in cols_pref if c in out.columns]
    rest = [c for c in out.columns if c not in front]
    return out[front + rest]


def build_reconstructed_excel_bytes(
    *,
    original_df: pd.DataFrame,
    study: StratificationStudyResult,
    reconstructed_df: pd.DataFrame,
    spc_groups: list[GroupMetrics],
) -> tuple[bytes, str]:
    """5시트 Excel bytes와 파일명 반환."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"spc_reconstructed_sample_{ts}.xlsx"

    original = _sanitize_df(original_df)
    summary = build_split_summary_df(study)
    recon = prepare_reconstructed_export_df(reconstructed_df)
    sg_stats = build_subgroup_stats_df(reconstructed_df)
    spc_summary = pd.DataFrame([_group_to_spc_row(g) for g in spc_groups])

    sheets: list[tuple[str, pd.DataFrame]] = [
        (SHEET_ORIGINAL, original),
        (SHEET_SUMMARY, summary),
        (SHEET_RECON, recon),
        (SHEET_SG_STATS, sg_stats),
        (SHEET_SPC, spc_summary),
    ]

    buf = io.BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for sheet_name, frame in sheets:
                safe_name = sheet_name[:31]
                try:
                    if frame is None or frame.empty:
                        pd.DataFrame({"message": ["데이터 없음"]}).to_excel(
                            writer, sheet_name=safe_name, index=False
                        )
                    else:
                        frame.to_excel(writer, sheet_name=safe_name, index=False)
                except Exception as sheet_exc:
                    logger.exception("Excel sheet export failed: %s", safe_name)
                    raise RuntimeError(f"엑셀 생성 실패 (시트: {safe_name}): {sheet_exc}") from sheet_exc
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Excel export failed")
        raise RuntimeError(f"엑셀 생성 실패: {exc}") from exc

    buf.seek(0)
    data = buf.getvalue()
    if not data:
        raise RuntimeError("엑셀 파일이 비어 있습니다.")
    return data, filename
