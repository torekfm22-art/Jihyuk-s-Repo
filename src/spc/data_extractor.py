"""
MES/QMS 원본 데이터 추출 모듈 (xlsx 전용).

MES·QMS에서 내보낸 Excel(.xlsx) 파일을 읽고, 컬럼명을 표준화한 뒤
단일 파일 또는 MES+QMS 병합 데이터로 SPC 분석에 사용합니다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
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
    ],
    "measure_date": ["측정일", "작업일", "검사일", "date", "measure_date", "work_date", "생산일"],
    "value": [
        "측정값", "검사값", "결과 값", "결과값", "결과", "result",
        "value", "measurement", "result_value", "data_value", "measure_value",
        "중량", "중량값", "중량 값", "인플레이터중량", "인플레이터 중량",
        "인플레이터 중량값", "무게", "weight", "wt",
    ],
    "item": ["품목", "품명", "품번", "item", "product", "part_no", "part_number"],
    "process": ["공정", "공정명", "공정 코드", "공정코드", "process", "operation", "step"],
    "characteristic": [
        "특성", "검사항목", "검사 항목", "characteristic", "spec_item", "항목",
        "inspection_item", "measure_item",
    ],
    "lot": [
        "LOT", "lot", "lot_no", "로트 번호", "로트번호", "배치번호", "batch", "lot number",
        "AIRBAG 번호", "airbag번호", "airbag 번호", "에어백번호", "에어백 번호", "시리얼", "serial",
    ],
    "usl": ["USL", "usl", "상한", "upper_spec", "spec_upper", "upper limit"],
    "lsl": ["LSL", "lsl", "하한", "lower_spec", "spec_lower", "lower limit"],
    "target": ["Target", "target", "목표", "nominal", "중심값", "타겟값", "타겟", "target_value"],
    "shift": ["교대", "근무조", "shift", "작업조", "주야", "주/야"],
    "source": ["source", "출처", "system", "시스템"],
}


def _col_key(name: str) -> str:
    """컬럼명 비교용 정규화 (공백·언더스코어 제거, 소문자)."""
    return str(name).strip().lower().replace(" ", "").replace("_", "")


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


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼명을 표준 SPC 컬럼으로 정규화."""
    rename_map = {}
    lower_cols = {_col_key(c): c for c in df.columns}

    for standard, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = _col_key(alias)
            if key in lower_cols:
                rename_map[lower_cols[key]] = standard
                break

    return df.rename(columns=rename_map)


def _ensure_readable(path: Path) -> Path:
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(
            f"지원 형식: xlsx, xls, csv — 입력 파일: {path.name} ({path.suffix})"
        )
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    return path


@dataclass
class XlsxSource:
    """MES 또는 QMS Excel 파일 (.xlsx / .xls / csv / 암호화 Excel)."""

    path: Path
    sheet_name: str | int = 0
    system_label: str = "MES"
    password: str | None = None

    def read(self) -> pd.DataFrame:
        _ensure_readable(self.path)
        fmt = detect_file_format(self.path)
        df = read_excel_auto(self.path, self.sheet_name, self.password)
        df = _normalize_columns(df)
        ref_date = date_from_filename(self.path)
        if "timestamp" in df.columns:
            df["timestamp"] = parse_timestamp_series(df["timestamp"], ref_date)
        elif "measure_date" in df.columns:
            df["timestamp"] = pd.to_datetime(df["measure_date"], errors="coerce")
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
    ) -> "MesQmsExtractor":
        """첨부된 Excel 파일(1개 이상)을 읽어 병합."""
        if not paths:
            raise ValueError("분석할 Excel 파일을 1개 이상 첨부하세요.")

        frames: list[pd.DataFrame] = []
        for path in paths:
            p = Path(path)
            label = p.stem
            frames.append(XlsxSource(p, sheet_name, label, password).read())
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
        logger.info("Excel 파일 병합 완료: 총 %d행", len(df))
        if validate:
            self._validate(df)
        return self._prepare(df)

    def _validate(self, df: pd.DataFrame) -> None:
        if "value" not in df.columns:
            hints = [c for c in df.columns if any(k in _col_key(c) for k in ("결과", "측정", "검사", "value", "result"))]
            raise ValueError(
                "측정값 컬럼을 찾을 수 없습니다.\n"
                "인식 가능 예: 측정값, 검사값, 결과 값, value\n"
                f"현재 컬럼: {list(df.columns)}\n"
                + (f"측정값 후보: {hints}" if hints else "")
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
