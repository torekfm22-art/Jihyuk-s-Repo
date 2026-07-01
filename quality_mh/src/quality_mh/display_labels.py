"""화면·엑셀 표시용 한글 라벨."""
from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

COLUMN_LABELS_KO: dict[str, str] = {
    # 공통
    "record_id": "레코드ID",
    "plant": "공장",
    "wg": "W/G",
    "task_code": "업무코드",
    "task_name": "업무항목",
    "task": "업무항목",
    "line": "라인",
    "line_group": "라인그룹",
    "remark": "비고",
    # RuleMaster
    "task_type": "업무유형",
    "unit_time_method": "단위시간방식",
    "frequency_method": "발생빈도산정방식",
    "default_allowance_rate": "기본부가공수율",
    "rounding_policy": "정수화정책",
    # FrequencyDB
    "product_group": "제품군",
    "y1_actual": "Y-1실적",
    "y2_actual": "Y-2실적",
    "y3_actual": "Y-3실적",
    "weight1": "가중치1",
    "weight2": "가중치2",
    "weight3": "가중치3",
    "ref_ratio": "기준비율",
    "plan_qty": "계획생산량",
    "sampling_type": "샘플링구분",
    "cycle_type": "수행주기",
    "cycle_count": "횟수",
    "working_days": "근무일수",
    "working_weeks": "근무주수",
    "working_months": "근무월수",
    "data_source": "데이터출처",
    "description": "설명",
    # QuantitativeRecord
    "sub_task": "세부업무",
    "performers": "수행인원",
    "unit_time_min": "단위시간(분)",
    "current_headcount": "현재원",
    "frequency_override": "발생빈도수정",
    "allowance_override": "부가공수수정",
    "judgment_status": "판정상태",
    "hq_review": "본사검토",
    # CalcResult
    "auto_frequency": "자동발생빈도",
    "final_frequency": "최종발생빈도",
    "frequency_method_used": "사용산정방식",
    "is_overridden": "수정여부",
    "unit_time_hr": "단위시간(hr)",
    "standard_work_time_hr": "표준작업시간(hr)",
    "allowance_rate": "부가공수율",
    "final_work_time_hr": "최종작업시간(hr)",
    "standard_mh": "표준공수(M/H)",
    "standard_md": "표준공수(M/D)",
    "standard_headcount_raw": "표준인원(원시)",
    "standard_headcount": "표준인원",
    "diff_from_current": "현재원대비차이",
    "diff": "차이",
    "calc_log": "계산로그",
    "excel_mh": "엑셀M/H",
    "system_mh": "시스템M/H",
    "mh_diff": "M/H차이",
    # QualitativeRecord
    "task_definition": "업무정의",
    "workload_desc": "업무량설명",
    "selection_reason": "선정사유",
    "future_criteria": "증감판단기준",
    # 집계
    "record_count": "건수",
    "final_work_time_hr": "최종작업시간(hr)",
    # 변경이력
    "history_id": "이력ID",
    "field_name": "항목명",
    "old_value": "이전값",
    "new_value": "변경값",
    "changed_at": "변경시각",
    "change_reason": "변경사유",
    # 기준표 freq_db 축약
    "y1": "Y-1실적",
    "y2": "Y-2실적",
    "y3": "Y-3실적",
    # 변경이력 항목명 (내부키)
    "default_allowance_rate": "기본부가공수율",
}


def translate_field_name(name: str) -> str:
    return COLUMN_LABELS_KO.get(name, name)


def _format_value(key: str, value):
    if key == "is_overridden" and isinstance(value, bool):
        return "예" if value else "아니오"
    return value


def rename_dict(data: dict, extra: dict[str, str] | None = None) -> dict:
    labels = {**COLUMN_LABELS_KO, **(extra or {})}
    return {
        labels.get(k, k): _format_value(k, v)
        for k, v in data.items()
    }


def model_to_korean_dict(model: BaseModel) -> dict:
    return rename_dict(model.model_dump(mode="json"))


def rename_dataframe(df: pd.DataFrame, extra: dict[str, str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    labels = {**COLUMN_LABELS_KO, **(extra or {})}
    out = df.copy()
    out.columns = [labels.get(c, c) for c in out.columns]
    for col in out.columns:
        src = next((k for k, v in labels.items() if v == col), col)
        if src == "is_overridden":
            out[col] = out[col].map(lambda x: "예" if x else "아니오" if isinstance(x, bool) else x)
        if src == "field_name":
            out[col] = out[col].map(translate_field_name)
    return out


def models_to_korean_df(models: list[BaseModel]) -> pd.DataFrame:
    if not models:
        return pd.DataFrame()
    return rename_dataframe(pd.DataFrame([m.model_dump(mode="json") for m in models]))
