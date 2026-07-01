"""MH Program.xlsx 양식 파싱 (종합/정량/정성 시트)."""
from __future__ import annotations

import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from quality_mh.models import FrequencyDB, FrequencyMethod, QualitativeRecord, QuantitativeRecord
from quality_mh.plant_config import PlantConfig, WG_CATEGORIES
from quality_mh.rule_master import RuleMasterRegistry, build_rule_master

_FREQ_MAP = {
    "3개년 가중평균": FrequencyMethod.WEIGHTED_AVG,
    "3개년가중평균": FrequencyMethod.WEIGHTED_AVG,
    "생산계획 (연동)": FrequencyMethod.PLAN_LINKED,
    "생산계획연동": FrequencyMethod.PLAN_LINKED,
    "수행주기": FrequencyMethod.PERIODIC,
}

_TASK_NAME_ALIASES: dict[str, str] = {
    "[입고] 정기 점검": "정기 점검",
    "[입고] 정기 검사": "정기 검사",
    "[입고] 외주품 입고검사": "외주품 입고검사",
    "[입고] 4M/EO 관리": "4M/EO 관리",
    "[입고] 4M / EO 관리": "4M/EO 관리",
    "[입고] 검사기준/대상 변경": "검사기준/대상 변경",
}


def _safe_float(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_str(val) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s else None


def _find_sheet(sheet_names: list[str], keyword: str) -> str | None:
    for name in sheet_names:
        if keyword in name:
            return name
    return None


def _resolve_task_code(registry: RuleMasterRegistry, wg: str, task_item: str) -> str:
    task_item = task_item.strip()
    normalized = _TASK_NAME_ALIASES.get(task_item, task_item)
    for prefix in ("[입고] ", "[공정] ", "[완성] ", "[시험] ", "[공통] "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    rule = registry.get_by_wg_and_task_name(wg, normalized)
    if rule:
        return rule.task_code
    for rule in registry.get_quantitative_rules():
        if rule.task_name in task_item or task_item in f"[{rule.wg}] {rule.task_name}":
            return rule.task_code
    slug = re.sub(r"[^\w가-힣]", "", task_item)[:12] or "UNK"
    return f"IMP-{wg[:2]}-{slug}"


def _parse_work_hours_from_summary(df: pd.DataFrame, sheet_name: str = "") -> float:
    m = re.search(r"([\d.]+)\s*hrs?", sheet_name, re.I)
    if m:
        return float(m.group(1))
    for r in range(min(10, len(df))):
        for c in range(df.shape[1]):
            val = _safe_str(df.iloc[r, c])
            if val and "/" in val and re.match(r"^\d+\.?\d*/\d+\.?\d*$", val):
                try:
                    return float(val.split("/")[0])
                except ValueError:
                    pass
    return 10.0


def _parse_title_year(df: pd.DataFrame) -> tuple[str, int]:
    for r in range(min(6, len(df))):
        for c in range(min(6, df.shape[1])):
            text = _safe_str(df.iloc[r, c])
            if text and "M/H" in text:
                m = re.search(r"\((\d{4})\)", text)
                year = int(m.group(1)) if m else 2025
                plant = text.replace("■", "").split("품질")[0].strip()
                return plant, year
    return "김천램프", 2025


def import_mh_program(
    source: str | Path | BinaryIO | BytesIO,
    registry: RuleMasterRegistry | None = None,
) -> tuple[PlantConfig, list[QuantitativeRecord], list[QualitativeRecord], list[FrequencyDB]]:
    """MH Program.xlsx 4시트 일괄 파싱."""
    registry = registry or RuleMasterRegistry(build_rule_master())
    xl = pd.ExcelFile(source)
    names = xl.sheet_names

    sum_sheet = _find_sheet(names, "종합") or names[0]
    quant_sheet = _find_sheet(names, "정량") or names[1]
    qual_sheet = _find_sheet(names, "정성") or names[2]

    df_sum = pd.read_excel(source, sheet_name=sum_sheet, header=None)
    plant_name, year = _parse_title_year(df_sum)
    work_hrs = _parse_work_hours_from_summary(df_sum, sum_sheet)

    config = PlantConfig(
        plant_name=plant_name,
        analysis_year=year,
        work_hours_per_day=work_hrs,
    )

    wg_map = {"입고": "입고", "공정": "공정", "완성": "완성", "시험": "시험"}
    for r in range(len(df_sum)):
        cat = _safe_str(df_sum.iloc[r, 5])
        if cat in wg_map:
            cur = _safe_float(df_sum.iloc[r, 7])
            if cur is not None:
                config.current_headcount[wg_map[cat]] = cur
        if _safe_str(df_sum.iloc[r, 4]) == "정 성 合":
            cur = _safe_float(df_sum.iloc[r, 7])
            if cur is not None:
                config.current_headcount["정성"] = cur
        if _safe_str(df_sum.iloc[r, 4]) == "그룹장":
            cur = _safe_float(df_sum.iloc[r, 8])
            if cur is not None:
                config.non_standard_headcount["그룹장"] = cur
        if _safe_str(df_sum.iloc[r, 4]) == "파트장":
            cur = _safe_float(df_sum.iloc[r, 8])
            if cur is not None:
                config.non_standard_headcount["파트장"] = cur

    quantitative: list[QuantitativeRecord] = []
    freq_db: list[FrequencyDB] = []
    df_q = pd.read_excel(source, sheet_name=quant_sheet, header=None)
    for r in range(9, len(df_q)):
        plant = _safe_str(df_q.iloc[r, 2])
        wg = _safe_str(df_q.iloc[r, 3])
        task_item = _safe_str(df_q.iloc[r, 5])
        sub_task = _safe_str(df_q.iloc[r, 6])
        if not plant or not wg or not task_item:
            continue
        unit_min = _safe_float(df_q.iloc[r, 12]) or 0.0
        if unit_min <= 0:
            continue
        performers = _safe_float(df_q.iloc[r, 11]) or 1.0
        freq_text = _safe_str(df_q.iloc[r, 8]) or ""
        cycle_type = _safe_str(df_q.iloc[r, 14])
        cycle_count = _safe_float(df_q.iloc[r, 15])
        annual_freq = _safe_float(df_q.iloc[r, 19]) or cycle_count
        task_code = _resolve_task_code(registry, wg, task_item)
        freq_method = _FREQ_MAP.get(freq_text.replace(" ", ""), None)
        if freq_method is None:
            for k, v in _FREQ_MAP.items():
                if k.replace(" ", "") in freq_text.replace(" ", ""):
                    freq_method = v
                    break
        freq_method = freq_method or FrequencyMethod.PERIODIC

        record = QuantitativeRecord(
            record_id=f"R-{uuid.uuid4().hex[:8]}",
            plant=plant,
            wg=wg,
            task_code=task_code,
            task_name=task_item,
            sub_task=sub_task,
            line=_safe_str(df_q.iloc[r, 4]),
            performers=performers,
            unit_time_min=unit_min,
            estimation_method=_safe_str(df_q.iloc[r, 7]),
            frequency_method_text=freq_text,
            cycle_type=cycle_type,
            cycle_count=cycle_count,
            data_source=_safe_str(df_q.iloc[r, 9]),
            mh_formula=_safe_str(df_q.iloc[r, 10]),
            annual_frequency=annual_freq,
            frequency_override=annual_freq,
            hq_review=_safe_str(df_q.iloc[r, 24]),
        )
        quantitative.append(record)

        if not any(f.task_code == task_code for f in freq_db):
            entry_kwargs: dict = {
                "task_code": task_code,
                "frequency_method": freq_method,
                "data_source": record.data_source,
                "description": record.mh_formula,
            }
            if freq_method == FrequencyMethod.PERIODIC:
                entry_kwargs["cycle_type"] = cycle_type or "월간"
                entry_kwargs["cycle_count"] = cycle_count or 1.0
            elif freq_method == FrequencyMethod.PLAN_LINKED and annual_freq:
                entry_kwargs["ref_ratio"] = 1.0
                entry_kwargs["plan_qty"] = annual_freq
            freq_db.append(FrequencyDB(**entry_kwargs))

    qualitative: list[QualitativeRecord] = []
    df_ql = pd.read_excel(source, sheet_name=qual_sheet, header=None)
    for r in range(5, len(df_ql)):
        plant = _safe_str(df_ql.iloc[r, 2])
        wg = _safe_str(df_ql.iloc[r, 3])
        task_name = _safe_str(df_ql.iloc[r, 4])
        if not plant or not task_name:
            continue
        std_hc = int(_safe_float(df_ql.iloc[r, 7]) or 0)
        qualitative.append(
            QualitativeRecord(
                record_id=f"QL-{uuid.uuid4().hex[:8]}",
                plant=plant,
                wg=wg or "공통",
                task_name=task_name,
                task_definition=_safe_str(df_ql.iloc[r, 5]),
                workload_desc=_safe_str(df_ql.iloc[r, 6]),
                standard_headcount=std_hc,
                current_headcount=std_hc,
                diff=0,
                remark=_safe_str(df_ql.iloc[r, 9]),
            )
        )

    return config, quantitative, qualitative, freq_db
