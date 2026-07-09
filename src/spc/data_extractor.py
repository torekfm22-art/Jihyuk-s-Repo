"""
MES/QMS 원본 데이터 추출 모듈 (xlsx 전용).

MES·QMS에서 내보낸 Excel(.xlsx) 파일을 읽고, 컬럼명을 표준화한 뒤
단일 파일 또는 MES+QMS 병합 데이터로 SPC 분석에 사용합니다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from src.spc.datetime_utils import date_from_filename, enrich_timestamp_from_source, parse_timestamp_series
from src.spc.excel_reader import detect_file_format, read_excel_auto

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".csv"}

# MES/QMS 공통 컬럼 매핑 (시스템별 alias → 표준명)
COLUMN_ALIASES = {
    "timestamp": [
        "측정일시", "검사일시", "수집일시", "처리 시간", "처리시간",
        "datetime", "date_time", "inspection_time", "measure_time",
        "트랜잭션 시간", "트랜잭션시간", "transaction_time", "transaction time",
    ],
    "measure_date": ["측정일", "작업일", "검사일", "date", "measure_date", "work_date", "생산일"],
    "measure_time": [
        "측정시간", "검사시간", "작업시간", "수집시간", "time", "measure_time",
        "inspection_time_only", "시간",
    ],
    "value": [
        "측정값", "검사값", "결과 값", "결과값", "결과", "result",
        "value", "measurement", "result_value", "data_value", "measure_value",
        "값",  # MES/QMS export
        "중량", "중량값", "중량 값", "인플레이터중량", "인플레이터 중량",
        "인플레이터 중량값", "무게", "weight", "wt",
    ],
    "item": ["품목", "품명", "품번", "item", "product", "part_no", "part_number"],
    "process": ["공정", "공정 코드", "공정코드", "process", "operation", "step"],
    "process_name": ["공정명"],
    "operation": ["작업"],
    "operation_name": ["작업명"],
    "line": ["라인", "라인코드", "라인 코드", "line", "line_code"],
    "machine": [
        "설비", "설비명", "설비코드", "설비 코드", "설비 id", "설비id", "설비 ID",
        "machine", "equipment",
        "equipment_code", "설비/라인", "machine_name",
    ],
    "characteristic": [
        "특성", "검사항목", "검사 항목", "characteristic", "spec_item", "항목",
        "inspection_item", "measure_item",
    ],
    "measure_item": [
        "측정항목", "측정 항목", "measure_item", "measurement_item", "검사항목명",
    ],
    "measurement_point": [
        "네트 갯수", "체결부위", "체결 부위", "측정포인트", "측정 포인트",
        "measure_point", "measurement_point", "point", "point_no", "포인트", "포인트번호",
        "측정점", "값 갯수",
    ],
    "lot": [
        "LOT", "lot", "lot_no", "로트 번호", "로트번호", "배치번호", "batch", "lot number",
        "AIRBAG 번호", "airbag번호", "airbag 번호", "에어백번호", "에어백 번호", "시리얼", "serial",
    ],
    "usl": [
        "USL", "usl", "상한", "상한값", "상한 값", "upper_spec", "spec_upper", "upper limit",
        "규격상한", "규격 상한", "공차상한", "공차 상한", "spec upper", "upper", "max",
    ],
    "lsl": [
        "LSL", "lsl", "하한", "하한값", "하한 값", "lower_spec", "spec_lower", "lower limit",
        "규격하한", "규격 하한", "공차하한", "공차 하한", "spec lower", "lower", "min",
    ],
    "target": ["Target", "target", "목표", "nominal", "중심값", "타겟값", "타겟", "target_value"],
    "shift": ["교대", "근무조", "shift", "작업조", "주야", "주/야"],
    "source": ["source", "출처", "system", "시스템"],
}


def _col_key(name: str) -> str:
    """컬럼명 비교용 정규화 (공백·언더스코어 제거, 소문자)."""
    return str(name).strip().lower().replace(" ", "").replace("_", "")


def _rank_value_column(name: str) -> tuple[int, int, str]:
    """측정값 후보 정렬 — 구체적 항목명 우선, 통용 '값' 열은 후순위."""
    ck = _col_key(name)
    generic_keys = {_col_key(a) for a in COLUMN_ALIASES["value"] if len(a) <= 2 or a in ("값", "중량", "무게", "weight", "wt")}
    if ck in generic_keys:
        return (2, len(ck), name)
    if any(k in str(name) for k in ("하한", "상한", "오류", "판정", "런다운")):
        return (3, len(ck), name)
    return (0, len(ck), name)


def _is_metadata_column(label: str) -> bool:
    ck = _col_key(label)
    for standard, aliases in COLUMN_ALIASES.items():
        if standard == "value":
            continue
        if ck in {_col_key(a) for a in aliases}:
            return True
    if ck in ("sno", "품번", "공정", "단위") or label.endswith("갯수"):
        return True
    if label.upper().startswith("S/") or "트랜잭션" in label or "시간" in label:
        return True
    return False


def _is_limit_or_judge_column(label: str) -> bool:
    if any(k in label for k in ("하한", "상한", "런다운", "오류", "판정")):
        return True
    ck = _col_key(label)
    limit_keys = {_col_key(a) for std in ("usl", "lsl", "target") for a in COLUMN_ALIASES[std]}
    return ck in limit_keys


def _column_numeric_stats(series: pd.Series) -> tuple[int, float]:
    """(유효 숫자 개수, 비어 있지 않은 셀 대비 숫자 비율)."""
    non_empty = series.dropna()
    non_empty = non_empty[non_empty.astype(str).str.strip().str.lower().isin(("", "nan", "none", "-")) == False]
    if len(non_empty) < 2:
        return 0, 0.0
    numeric = pd.to_numeric(non_empty, errors="coerce")
    n_valid = int(numeric.notna().sum())
    ratio = n_valid / len(non_empty) if len(non_empty) else 0.0
    return n_valid, ratio


def _is_likely_row_index_column(series: pd.Series) -> bool:
    n_valid, ratio = _column_numeric_stats(series)
    if n_valid < 3 or ratio < 0.9:
        return False
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 3:
        return False
    diffs = numeric.diff().dropna()
    return not diffs.empty and float((diffs == 1).mean()) >= 0.8


def _is_obviously_non_value_column(label: str, series: pd.Series | None = None) -> bool:
    if _is_metadata_column(label):
        return True
    if _is_limit_or_judge_column(label):
        return True
    if series is not None and _is_likely_row_index_column(series):
        return True
    return False


def list_value_column_choices(df: pd.DataFrame) -> list[str]:
    """수동 선택용 — 명백한 메타·규격 열을 제외한 전체 컬럼 목록."""
    out: list[str] = []
    for col in df.columns:
        label = str(col)
        if _is_obviously_non_value_column(label, df[col]):
            continue
        out.append(label)
    if not out:
        out = [str(c) for c in df.columns]
    return out


def _suggest_value_columns(df: pd.DataFrame) -> list[str]:
    """측정값 열 후보 (MES/QMS 형식 포함)."""
    value_keys = {_col_key(a) for a in COLUMN_ALIASES["value"]}
    hints: list[str] = []
    numeric_scored: list[tuple[float, int, str]] = []

    for col in df.columns:
        ck = _col_key(col)
        label = str(col)
        series = df[col]
        if _is_obviously_non_value_column(label, series):
            continue
        if ck in value_keys:
            hints.append(label)
            continue
        if any(
            k in label.lower()
            for k in ("값", "측정", "결과", "value", "result", "중량", "무게", "실측", "수치", "data", "measure")
        ):
            hints.append(label)
            continue
        n_valid, ratio = _column_numeric_stats(series)
        if n_valid >= 2 and ratio >= 0.35:
            numeric_scored.append((ratio, n_valid, label))

    if not hints and numeric_scored:
        numeric_scored.sort(key=lambda x: (-x[0], -x[1], _rank_value_column(x[2])))
        hints = [label for _, _, label in numeric_scored]

    ordered = sorted(hints, key=_rank_value_column)
    seen: set[str] = set()
    out: list[str] = []
    for h in ordered:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:12]


def _resolve_column_name(df: pd.DataFrame, name: str, *, purpose: str = "value") -> str:
    """사용자 지정 열 이름 → 실제 DataFrame 컬럼 (유연 매칭)."""
    raw = name.strip()
    if not raw:
        raise ValueError("열 이름이 비어 있습니다.")

    cols = [str(c) for c in df.columns]
    if raw in cols:
        return raw

    key = _col_key(raw)
    norm_matches = [c for c in cols if _col_key(c) == key]
    if len(norm_matches) == 1:
        return norm_matches[0]
    if len(norm_matches) > 1:
        raise ValueError(
            f"지정한 열 '{raw}'과(와) 일치하는 컬럼이 여러 개입니다: {norm_matches}"
        )

    if len(key) >= 2:
        partial = [c for c in cols if key in _col_key(c)]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            raise ValueError(
                f"지정한 측정값 열 '{raw}'이(가) 여러 컬럼과 부분 일치합니다: {partial}\n"
                "목록에서 정확한 열 이름을 선택하세요."
            )

    hints = _suggest_value_columns(df) if purpose == "value" else []
    hint_txt = f"\n측정값 후보: {hints}" if hints else ""
    raise ValueError(
        f"지정한 측정값 열 '{raw}'을(를) 찾을 수 없습니다.{hint_txt}\n"
        f"현재 컬럼: {cols}\n"
        "※ 이 데이터는 측정값 열에 **값** 을 입력하세요. "
        "(비워 두면 '값' 열을 자동 인식합니다. 'S'는 X-bar S 관리도 유형이지 열 이름이 아닙니다.)"
    )


def resolve_value_column_for_split_label(df: pd.DataFrame, label: str | None) -> pd.DataFrame:
    """
    항목별 분리 시 항목명과 동일한 열이 있으면 해당 열을 측정값(value)으로 사용.
    (측정항목 열 + 항목별 전용 수치 열이 공존하는 QMS wide 형식)
    """
    if not label:
        return df
    target = _col_key(label)
    if not target:
        return df
    for col in df.columns:
        if str(col) == "value":
            continue
        if _col_key(str(col)) == target:
            out = df.copy()
            out["value"] = pd.to_numeric(out[col], errors="coerce")
            logger.info("항목 '%s' → 전용 측정값 열 '%s' 적용", label, col)
            return out
    return df


def _alias_keys() -> set[str]:
    keys: set[str] = set()
    for aliases in COLUMN_ALIASES.values():
        for alias in aliases:
            keys.add(_col_key(alias))
    return keys


def detect_header_row_index(raw: pd.DataFrame, max_scan: int = 40) -> int:
    """
    상단 빈 행·제목 행이 있는 MES export에서 실제 컬럼 헤더 행(0-based) 추정.
    """
    alias_keys = _alias_keys()
    best_row = 0
    best_score = -1
    n = min(max_scan, len(raw))

    for i in range(n):
        row = raw.iloc[i]
        score = 0
        non_empty = 0
        numeric_cells = 0
        for cell in row:
            if pd.isna(cell) or str(cell).strip() == "":
                continue
            non_empty += 1
            ck = _col_key(str(cell))
            if ck in alias_keys:
                score += 3
            elif any(k in ck or ck in k for k in alias_keys if len(k) >= 2):
                score += 1
            if isinstance(cell, (int, float)) and not isinstance(cell, bool):
                numeric_cells += 1

        if non_empty >= 2 and numeric_cells >= max(1, non_empty // 2):
            score -= 4
        if score > best_score:
            best_score = score
            best_row = i

    if best_score < 3:
        unnamed_ratio = 0.0
        if len(raw.columns) and all(str(c).startswith("Unnamed") for c in raw.columns):
            unnamed_ratio = 1.0
        if unnamed_ratio < 1.0:
            return 0
    return best_row


def _coalesce_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """동일 이름 컬럼이 여러 개면 왼쪽부터 비어 있지 않은 값으로 병합."""
    if not df.columns.duplicated().any():
        return df
    merged: dict[str, pd.Series] = {}
    for name in dict.fromkeys(df.columns):
        sub = df.loc[:, df.columns == name]
        if sub.shape[1] == 1:
            merged[name] = sub.iloc[:, 0]
        else:
            merged[name] = sub.bfill(axis=1).iloc[:, 0]
    return pd.DataFrame(merged)


def _column_rename_map(df: pd.DataFrame) -> dict[str, str]:
    """원본 컬럼명 → 표준 SPC 컬럼명 매핑."""
    rename_map: dict[str, str] = {}
    lower_cols = {_col_key(c): c for c in df.columns}
    used_standards: set[str] = set()
    value_already_set = "value" in df.columns

    for standard, aliases in COLUMN_ALIASES.items():
        if standard in used_standards:
            continue
        if standard == "value" and value_already_set:
            used_standards.add("value")
            continue
        for alias in aliases:
            key = _col_key(alias)
            if key in lower_cols:
                original = lower_cols[key]
                if standard == "value" and original == "value":
                    used_standards.add("value")
                    break
                rename_map[str(original)] = standard
                used_standards.add(standard)
                break
    return rename_map


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼명을 표준 SPC 컬럼으로 정규화."""
    rename_map = _column_rename_map(df)
    out = df.rename(columns=rename_map)
    return _coalesce_duplicate_columns(_ensure_measurement_point_column(out))


def preview_boundary_column_options(raw_df: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    """Raw Excel 컬럼명 목록 + 정규화 후 실제 분석 컬럼 매핑."""
    from src.spc.sampler import list_raw_boundary_column_candidates, list_virtual_boundary_options

    if raw_df is None or raw_df.empty:
        return [], {}
    rename_map = _column_rename_map(raw_df)
    normalized = _normalize_columns(raw_df.copy())
    resolve: dict[str, str] = {}
    options: list[str] = []
    valid_final = set(list_raw_boundary_column_candidates(normalized))
    for col in raw_df.columns:
        raw = str(col).strip()
        if not raw:
            continue
        final = rename_map.get(raw, raw)
        if final not in normalized.columns and raw in normalized.columns:
            final = raw
        if final not in normalized.columns:
            continue
        resolve[raw] = final
        if final in valid_final:
            options.append(raw)
    for label, token in list_virtual_boundary_options(normalized):
        if label not in options:
            options.append(label)
        resolve[label] = token
    return options, resolve


MEASUREMENT_POINT_MAX_LEVELS = 30
MEASUREMENT_POINT_MANUAL_MAX_LEVELS = 500
MEASUREMENT_POINT_AUTO_SPLIT_MAX = 8
MEASUREMENT_POINT_MIN_ROWS_PER_LEVEL = 2


def _is_known_measurement_point_alias(col: str) -> bool:
    ck = _col_key(col)
    return ck in {_col_key(a) for a in COLUMN_ALIASES["measurement_point"]}


def _is_known_equipment_split_column(col: str) -> bool:
    """설비 ID·설비코드 등 — 측정 포인트 분리 축으로 자주 사용."""
    if str(col) == "machine":
        return True
    ck = _col_key(col)
    return ck in {_col_key(a) for a in COLUMN_ALIASES["machine"]}


def _score_measurement_point_column(
    df: pd.DataFrame,
    col: str,
    *,
    max_levels: int = MEASUREMENT_POINT_MAX_LEVELS,
) -> float | None:
    """측정 포인트(체결부위·네트 번호·설비 ID 등) 열 후보 점수 — 고유값 수 가산 유지."""
    value_keys = {_col_key(a) for a in COLUMN_ALIASES["value"]}
    label = str(col)
    if _col_key(label) in value_keys or label == "value":
        return None
    series = df[col].dropna()
    if len(series) < 2:
        return None
    uniq = series.astype(str).str.strip().unique()
    uniq = [u for u in uniq if u and u.lower() not in ("nan", "none", "-")]
    if not 2 <= len(uniq) <= max_levels:
        return None

    known = (
        _is_known_measurement_point_alias(col)
        or col == "measurement_point"
        or _is_known_equipment_split_column(col)
    )
    numeric_ratio = pd.to_numeric(series, errors="coerce").notna().mean()
    if not known and numeric_ratio < 0.7:
        return None

    score = float(len(uniq))
    if _is_known_equipment_split_column(col) or "설비" in label:
        score += 25.0
    if "네트" in label:
        score += 20.0
    if "체결" in label or "부위" in label:
        score += 15.0
    if "포인트" in label.lower() or "point" in label.lower():
        score += 12.0
    if label.endswith("갯수") or label.endswith("개수"):
        score += 8.0
    return score


def _ensure_measurement_point_column(df: pd.DataFrame) -> pd.DataFrame:
    """표준 measurement_point 열이 없으면 최고 점수 후보로 지정."""
    if "measurement_point" in df.columns:
        return df
    best_col: str | None = None
    best_score = -1.0
    for col in df.columns:
        score = _score_measurement_point_column(df, str(col))
        if score is not None and score > best_score:
            best_score = score
            best_col = str(col)
    if not best_col:
        return df
    out = df.copy()
    out["measurement_point"] = out[best_col].astype(str).str.strip()
    return out


def _combine_date_and_time(df: pd.DataFrame, ref_date: pd.Timestamp | None) -> pd.DataFrame:
    """측정일 + 측정시간 분리 컬럼을 timestamp로 병합."""
    if "measure_time" not in df.columns:
        return df
    out = df.copy()
    if "timestamp" not in out.columns and "measure_date" in out.columns:
        out["timestamp"] = pd.to_datetime(out["measure_date"], errors="coerce")
    if "timestamp" not in out.columns:
        return out

    ts = pd.to_datetime(out["timestamp"], errors="coerce")
    tm = out["measure_time"]
    if pd.api.types.is_numeric_dtype(tm):
        tm_parsed = parse_timestamp_series(tm, ref_date)
    else:
        tm_parsed = pd.to_datetime(tm.astype(str).str.strip(), errors="coerce")
        if tm_parsed.notna().mean() < 0.5:
            tm_num = pd.to_numeric(tm, errors="coerce")
            if tm_num.notna().any():
                tm_parsed = parse_timestamp_series(tm_num, ref_date)

    combined: list[pd.Timestamp | pd.NaT] = []
    for base, tpart in zip(ts, tm_parsed):
        if pd.isna(base) and pd.isna(tpart):
            combined.append(pd.NaT)
            continue
        if pd.isna(tpart):
            combined.append(base)
            continue
        if pd.isna(base):
            combined.append(tpart)
            continue
        if tpart.year >= 2000 and (base.year < 2000 or base.hour == 0 and base.minute == 0):
            combined.append(tpart.replace(year=base.year, month=base.month, day=base.day))
        elif base.year >= 2000 and (tpart.year == 1970 or (tpart.hour == 0 and tpart.minute == 0 and tpart.second == 0)):
            combined.append(base.replace(hour=tpart.hour, minute=tpart.minute, second=tpart.second))
        else:
            combined.append(base.replace(hour=tpart.hour, minute=tpart.minute, second=tpart.second))

    out["timestamp"] = pd.Series(combined, index=out.index)
    return out


def _ensure_readable(path: Path) -> Path:
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(
            f"지원 형식: xlsx, xls, csv — 입력 파일: {path.name} ({path.suffix})"
        )
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    return path


def _resolve_sheet_name(sheet_name: str | int | None, sheet_names: list[str]) -> str | int:
    if sheet_name is None or (isinstance(sheet_name, str) and not sheet_name.strip()):
        return 0
    if isinstance(sheet_name, int):
        return sheet_name
    s = sheet_name.strip()
    if s in sheet_names:
        return s
    if s.isdigit():
        return int(s)
    return s


@dataclass
class SpecLimitPreview:
    """원본 데이터에서 감지한 규격(공차) 미리보기."""

    detected: bool = False
    usl: float | None = None
    lsl: float | None = None
    usl_column: str | None = None
    lsl_column: str | None = None
    usl_display_column: str | None = None
    lsl_display_column: str | None = None
    usl_source: str = ""
    lsl_source: str = ""
    suggested_spec_mode: str = "both"
    constant_columns: list[dict] = field(default_factory=list)


def _classify_limit_column(label: str) -> str | None:
    """열 이름 → 'usl' | 'lsl' | None."""
    ck = _col_key(label)
    if ck in {_col_key(a) for a in COLUMN_ALIASES["usl"]}:
        return "usl"
    if ck in {_col_key(a) for a in COLUMN_ALIASES["lsl"]}:
        return "lsl"
    text = str(label)
    if "상한" in text or "upper" in ck or ck.endswith("max"):
        return "usl"
    if "하한" in text or "lower" in ck or ck.endswith("min"):
        return "lsl"
    return None


def _constant_numeric_value(series: pd.Series, *, min_ratio: float = 0.99) -> float | None:
    """열 전체가 동일(또는 min_ratio 이상 동일)한 수치인지 — 규격 후보."""
    nums = pd.to_numeric(series, errors="coerce").dropna()
    if nums.empty:
        return None
    if len(nums) == 1:
        return float(nums.iloc[0])
    counts = nums.value_counts()
    if counts.iloc[0] / len(nums) < min_ratio:
        return None
    return float(counts.index[0])


def _dominant_limit_value(series: pd.Series) -> float | None:
    """상·하한 명칭 열 — 최빈값(복수 규격 혼재 시 대표값)."""
    nums = pd.to_numeric(series, errors="coerce").dropna()
    if nums.empty:
        return None
    if len(nums) == 1:
        return float(nums.iloc[0])
    counts = nums.value_counts()
    top_ratio = counts.iloc[0] / len(nums)
    if top_ratio >= 0.5:
        return float(counts.index[0])
    if len(counts) <= 8:
        return float(counts.index[0])
    return None


def _spec_scan_exclude_columns() -> set[str]:
    keys: set[str] = set()
    for group in (
        "value", "timestamp", "measure_date", "measure_time",
        "item", "process", "machine", "lot", "shift", "source",
    ):
        keys.update(_col_key(a) for a in COLUMN_ALIASES.get(group, []))
    keys.update({
        "value", "timestamp", "sno", "품번", "단위", "measurementpoint",
    })
    return keys


def detect_spec_limits(
    raw_df: pd.DataFrame,
    norm_df: pd.DataFrame,
    *,
    column_display: dict[str, str] | None = None,
) -> SpecLimitPreview:
    """
    규격 상·하한 자동 감지.
    1) 상한/하한/USL/LSL 명칭 열
    2) 동일 수치 패턴(상수) 열 — 명칭에 상·하한 포함 시 우선
    """
    display = column_display or {}
    rename = _column_rename_map(raw_df)
    preview = SpecLimitPreview()
    exclude = _spec_scan_exclude_columns()

    def _display(col: str) -> str:
        return display.get(col, col)

    def _apply(kind: str, col: str, val: float, source: str) -> None:
        if kind == "usl" and preview.usl is None:
            preview.usl = val
            preview.usl_column = col
            preview.usl_display_column = _display(col)
            preview.usl_source = source
        elif kind == "lsl" and preview.lsl is None:
            preview.lsl = val
            preview.lsl_column = col
            preview.lsl_display_column = _display(col)
            preview.lsl_source = source

    for std in ("usl", "lsl"):
        if std not in norm_df.columns:
            continue
        val = _dominant_limit_value(norm_df[std]) or _constant_numeric_value(norm_df[std])
        if val is not None:
            _apply(std, std, val, "standard")

    for raw_col in raw_df.columns:
        raw = str(raw_col).strip()
        final = rename.get(raw, raw)
        if final not in norm_df.columns:
            continue
        kind = _classify_limit_column(raw)
        if not kind:
            kind = _classify_limit_column(final)
        if not kind:
            continue
        val = _dominant_limit_value(norm_df[final]) or _constant_numeric_value(norm_df[final])
        if val is not None:
            _apply(kind, final, val, "column_name")

    unnamed_constants: list[tuple[str, float]] = []
    for col in norm_df.columns:
        col_s = str(col)
        if _col_key(col_s) in exclude:
            continue
        if _classify_limit_column(col_s):
            continue
        val = _constant_numeric_value(norm_df[col_s])
        if val is None:
            continue
        preview.constant_columns.append({
            "column": col_s,
            "display_column": _display(col_s),
            "value": val,
        })
        unnamed_constants.append((col_s, val))

    if preview.usl is None or preview.lsl is None:
        remaining = [
            (c, v) for c, v in unnamed_constants
            if c not in (preview.usl_column, preview.lsl_column)
        ]
        if len(remaining) >= 2:
            remaining.sort(key=lambda x: x[1])
            if preview.lsl is None:
                c, v = remaining[0]
                _apply("lsl", c, v, "constant_pattern")
            if preview.usl is None and len(remaining) >= 2:
                c, v = remaining[-1]
                _apply("usl", c, v, "constant_pattern")
        elif len(remaining) == 1:
            c, v = remaining[0]
            kind = _classify_limit_column(_display(c))
            if kind:
                _apply(kind, c, v, "constant_pattern")

    if preview.usl is not None and preview.lsl is not None:
        preview.suggested_spec_mode = "both"
        preview.detected = True
    elif preview.usl is not None:
        preview.suggested_spec_mode = "upper_only"
        preview.detected = True
    elif preview.lsl is not None:
        preview.suggested_spec_mode = "lower_only"
        preview.detected = True

    if preview.detected and preview.usl is not None and preview.lsl is not None:
        if preview.lsl >= preview.usl:
            preview.detected = False

    return preview


@dataclass
class ExcelColumnPreview:
    """업로드 파일 컬럼·측정값 후보 미리보기."""

    file_name: str
    sheet: str | int
    sheet_names: list[str]
    columns: list[str]
    value_candidates: list[str]
    recommended_column: str | None
    row_count: int
    manual_value_options: list[str] = field(default_factory=list)
    boundary_column_options: list[str] = field(default_factory=list)
    boundary_column_resolve: dict[str, str] = field(default_factory=dict)
    auto_boundary_columns: list[str] = field(default_factory=list)
    measurement_point_column: str | None = None
    measurement_point_candidates: list[dict] = field(default_factory=list)
    measurement_point_summary: list[dict] = field(default_factory=list)
    auto_measurement_point_values: list[str] = field(default_factory=list)
    manual_split_options: list[dict] = field(default_factory=list)
    spec_limit: SpecLimitPreview | None = None
    error: str | None = None

    def resolved_manual_value_options(self) -> list[str]:
        """세션 캐시 등 구버전 preview 호환."""
        opts = getattr(self, "manual_value_options", None)
        if opts:
            return list(opts)
        return list(self.columns or [])


def preview_excel_columns(
    path: Path,
    *,
    sheet_name: str | int | None = 0,
    password: str | None = None,
) -> ExcelColumnPreview:
    """Excel 업로드 직후 컬럼 목록·측정값 후보 탐지 (UI 안내용)."""
    from src.spc.excel_reader import list_sheet_names, read_excel_auto

    sheet_names: list[str] = []
    resolved: str | int = sheet_name if sheet_name is not None else 0
    df: pd.DataFrame | None = None
    preview_error: str | None = None

    try:
        _ensure_readable(path)
        sheet_names = list_sheet_names(path, password)
        resolved = _resolve_sheet_name(sheet_name, sheet_names)
        df = read_excel_auto(path, resolved, password)
    except Exception as exc:
        preview_error = str(exc)
        try:
            if not sheet_names:
                sheet_names = list_sheet_names(path, password)
            resolved = _resolve_sheet_name(sheet_name, sheet_names)
            df = read_excel_auto(path, resolved, password)
            preview_error = None
        except Exception:
            df = None

    if df is None:
        return ExcelColumnPreview(
            file_name=path.name,
            sheet=sheet_name if sheet_name is not None else 0,
            sheet_names=sheet_names,
            columns=[],
            value_candidates=[],
            recommended_column=None,
            manual_value_options=[],
            row_count=0,
            error=preview_error or "파일을 읽을 수 없습니다.",
        )

    try:
        candidates = _suggest_value_columns(df)
        manual_options = list_value_column_choices(df)
        boundary_opts, boundary_map = preview_boundary_column_options(df)
        norm_df = _normalize_columns(df.copy())
        from src.spc.sampler import resolve_auto_boundary_columns

        auto_final = resolve_auto_boundary_columns(norm_df)
        reverse = {v: k for k, v in boundary_map.items()}
        auto_display = [reverse.get(c, c) for c in auto_final]
        col_display = {v: k for k, v in _column_rename_map(df).items()}

        from src.spc.characteristic_split import (
            build_measurement_point_preview,
        )

        mp_preview = build_measurement_point_preview(norm_df, column_display_names=col_display)
        mp_col = mp_preview.get("recommended_column")
        mp_candidates = mp_preview.get("candidates", [])
        mp_summary = mp_preview.get("summary", [])
        auto_mp = mp_preview.get("auto_values", [])
        spec_limit = detect_spec_limits(df, norm_df, column_display=col_display)

        return ExcelColumnPreview(
            file_name=path.name,
            sheet=resolved,
            sheet_names=sheet_names,
            columns=[str(c) for c in df.columns],
            value_candidates=candidates,
            recommended_column=candidates[0] if candidates else None,
            manual_value_options=manual_options,
            row_count=len(df),
            boundary_column_options=boundary_opts,
            boundary_column_resolve=boundary_map,
            auto_boundary_columns=auto_display,
            measurement_point_column=mp_col,
            measurement_point_candidates=mp_candidates,
            measurement_point_summary=mp_summary,
            auto_measurement_point_values=auto_mp,
            spec_limit=spec_limit,
            error=preview_error,
        )
    except Exception as exc:
        candidates = _suggest_value_columns(df)
        manual_options = list_value_column_choices(df)
        return ExcelColumnPreview(
            file_name=path.name,
            sheet=resolved,
            sheet_names=sheet_names,
            columns=[str(c) for c in df.columns],
            value_candidates=candidates,
            recommended_column=candidates[0] if candidates else None,
            manual_value_options=manual_options,
            row_count=len(df),
            error=str(exc),
        )


@dataclass
class XlsxSource:
    """MES 또는 QMS Excel 파일 (.xlsx / .xls / csv / 암호화 Excel)."""

    path: Path
    sheet_name: str | int = 0
    system_label: str = "MES"
    password: str | None = None
    value_column: str | None = None

    def read(self) -> pd.DataFrame:
        _ensure_readable(self.path)
        fmt = detect_file_format(self.path)
        df = read_excel_auto(self.path, self.sheet_name, self.password)
        if self.value_column:
            col = _resolve_column_name(df, self.value_column, purpose="value")
            df = df.rename(columns={col: "value"})
            logger.info("측정값 열 지정: '%s' → value", col)
        df = _normalize_columns(df)
        ref_date = date_from_filename(self.path)
        if "timestamp" in df.columns:
            df["timestamp"] = parse_timestamp_series(df["timestamp"], ref_date)
        elif "measure_date" in df.columns:
            df["timestamp"] = pd.to_datetime(df["measure_date"], errors="coerce")
        df = _combine_date_and_time(df, ref_date)
        if "source" not in df.columns:
            df["source"] = self.system_label
        else:
            df["source"] = df["source"].fillna(self.system_label)
        df = enrich_timestamp_from_source(df)
        logger.info(
            "%s 추출 (%s): %s (%d행, 시트=%s)",
            self.system_label, fmt.value, self.path.name, len(df), self.sheet_name,
        )
        return df


class MesQmsExtractor:
    """MES/QMS xlsx 통합 추출기."""

    def __init__(self, frames: list[pd.DataFrame]):
        self.frames = frames

    @classmethod
    def from_xlsx(cls, path: str | Path, sheet_name: str | int = 0, system_label: str = "MES/QMS") -> "MesQmsExtractor":
        """단일 xlsx 파일 로드."""
        source = XlsxSource(Path(path), sheet_name, system_label)
        return cls([source.read()])

    @classmethod
    def from_files(
        cls,
        paths: list[str | Path],
        *,
        sheet_name: str | int = 0,
        password: str | None = None,
        value_column: str | None = None,
    ) -> "MesQmsExtractor":
        """첨부된 Excel 파일(1개 이상)을 읽어 병합."""
        if not paths:
            raise ValueError("분석할 Excel 파일을 1개 이상 첨부하세요.")

        frames: list[pd.DataFrame] = []
        for path in paths:
            p = Path(path)
            label = p.stem
            frames.append(
                XlsxSource(p, sheet_name, label, password, value_column=value_column).read()
            )
        return cls(frames)

    @classmethod
    def from_mes_qms_xlsx(
        cls,
        *,
        mes_path: Optional[str | Path] = None,
        qms_path: Optional[str | Path] = None,
        mes_sheet: str | int = 0,
        qms_sheet: str | int = 0,
        mes_password: str | None = None,
        qms_password: str | None = None,
    ) -> "MesQmsExtractor":
        """MES·QMS Excel 파일을 각각 읽어 병합."""
        frames: list[pd.DataFrame] = []
        if mes_path:
            frames.append(XlsxSource(Path(mes_path), mes_sheet, "MES", mes_password).read())
        if qms_path:
            frames.append(XlsxSource(Path(qms_path), qms_sheet, "QMS", qms_password).read())
        if not frames:
            raise ValueError("mes_path 또는 qms_path 중 하나 이상을 지정해야 합니다.")
        return cls(frames)

    # 하위 호환 alias
    @classmethod
    def from_file(cls, path: str | Path, sheet_name: str | int = 0) -> "MesQmsExtractor":
        return cls.from_xlsx(path, sheet_name)

    def extract(self, validate: bool = True) -> pd.DataFrame:
        df = pd.concat(self.frames, ignore_index=True)
        if "value" not in df.columns:
            df = _normalize_columns(df)
        else:
            df = _ensure_measurement_point_column(df)
        logger.info("Excel 파일 병합 완료: 총 %d행", len(df))
        if validate:
            self._validate(df)
        return self._prepare(df)

    def _validate(self, df: pd.DataFrame) -> None:
        if "value" not in df.columns:
            hints = _suggest_value_columns(df)
            raise ValueError(
                "측정값 컬럼을 찾을 수 없습니다.\n"
                "인식 가능 예: 측정값, 검사값, 결과 값, value, **값**\n"
                f"현재 컬럼: {list(df.columns)}\n"
                + (f"측정값 후보: {hints}" if hints else "측정값 열 지정란에 '값' 등을 입력하세요.")
            )

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])

        if "timestamp" in df.columns:
            df["timestamp"] = parse_timestamp_series(df["timestamp"])
            df = enrich_timestamp_from_source(df)

        if "measure_date" in df.columns:
            df = df.drop(columns=["measure_date"])

        for col in ("usl", "lsl", "target"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df.reset_index(drop=True)

    def filter_by(
        self,
        df: pd.DataFrame,
        *,
        item: Optional[str] = None,
        process: Optional[str] = None,
        characteristic: Optional[str] = None,
        lot: Optional[str] = None,
        source: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> pd.DataFrame:
        """공정/품목/기간/MES·QMS 출처 등으로 원본 필터."""
        result = df.copy()

        filters = {
            "item": item,
            "process": process,
            "characteristic": characteristic,
            "lot": lot,
            "source": source,
        }
        for col, val in filters.items():
            if val is not None and col in result.columns:
                result = result[result[col].astype(str).str.upper() == str(val).upper()]

        if "timestamp" in result.columns:
            if date_from:
                result = result[result["timestamp"] >= pd.to_datetime(date_from)]
            if date_to:
                result = result[result["timestamp"] <= pd.to_datetime(date_to)]

        logger.info("필터 적용 후 %d행", len(result))
        return result.reset_index(drop=True)
