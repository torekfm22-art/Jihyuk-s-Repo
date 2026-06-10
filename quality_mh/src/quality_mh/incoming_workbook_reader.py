"""입고 MH 근거 통합문서 읽기 (DRM 암호화 파일은 Excel COM 우선)."""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _read_with_pandas(path: Path | BytesIO, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, header=None, engine="openpyxl")


def _list_sheets_pandas(path: Path | BytesIO) -> list[str]:
    xl = pd.ExcelFile(path, engine="openpyxl")
    return xl.sheet_names


def _read_with_com(path: Path, sheet_names: list[str] | None = None) -> dict[str, pd.DataFrame]:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False

    workbook = None
    opened_here = False
    target_name = path.name

    try:
        for i in range(1, excel.Workbooks.Count + 1):
            wb = excel.Workbooks(i)
            if target_name in wb.Name:
                workbook = wb
                break
        if workbook is None:
            workbook = excel.Workbooks.Open(str(path.resolve()), ReadOnly=True)
            opened_here = True

        names = [workbook.Sheets(i + 1).Name for i in range(workbook.Sheets.Count)]
        targets = sheet_names or names
        parsed: dict[str, pd.DataFrame] = {}

        for sheet_name in targets:
            if sheet_name not in names:
                continue
            ws = workbook.Sheets(sheet_name)
            used = ws.UsedRange
            rows = used.Rows.Count
            cols = used.Columns.Count
            data = used.Value
            if rows == 1 and cols == 1:
                grid = [[data]]
            elif rows == 1:
                grid = [list(data)]
            elif cols == 1:
                grid = [[row] for row in data]
            else:
                grid = [list(row) for row in data]
            parsed[sheet_name] = pd.DataFrame(grid)

        return parsed
    finally:
        if opened_here and workbook is not None:
            workbook.Close(SaveChanges=False)


def read_incoming_workbook(
    path: Path | BytesIO,
    sheet_names: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """근거 통합문서 시트 로드. 실패 시 COM 재시도."""
    if isinstance(path, BytesIO):
        return {name: _read_with_pandas(path, name) for name in (_list_sheets_pandas(path))}

    file_path = Path(path)
    default_sheets = [
        "입고검사 발생빈도 분석(생산계획 연동)",
        "생산계획 연동",
        "24년 Pivot",
        "25년 Pivot",
        "검사빈도(부품별) 리스트_24년",
        "검사빈도(부품별) 리스트_25년",
    ]

    try:
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        names = xl.sheet_names if sheet_names is None else sheet_names
        return {sn: _read_with_pandas(file_path, sn) for sn in names if sn in xl.sheet_names}
    except Exception as exc:
        logger.info("openpyxl 읽기 실패, Excel COM 시도: %s", exc)

    try:
        com_sheets = _read_with_com(file_path, None)
        if sheet_names is None:
            picked = {}
            for key in default_sheets:
                if key in com_sheets:
                    picked[key] = com_sheets[key]
            for name, frame in com_sheets.items():
                if name in picked:
                    continue
                if "Pivot" in name or "리스트" in name or "생산계획" in name:
                    picked[name] = frame
            return picked
        return {sn: com_sheets[sn] for sn in sheet_names if sn in com_sheets}
    except Exception as exc:
        raise RuntimeError(
            "엑셀 파일을 읽을 수 없습니다. "
            "DRM 암호화 파일은 Excel에서 연 상태로 실행하거나, "
            "다른 이름으로 .xlsx 저장 후 다시 시도하세요."
        ) from exc


def discover_incoming_sheet_names(sheets: dict[str, pd.DataFrame]) -> dict[str, str]:
    """시트명 키워드 매칭."""
    found: dict[str, str] = {}
    for name in sheets:
        if "입고검사" in name and "발생빈도" in name:
            found["analysis"] = name
        elif "생산계획" in name:
            found["plan"] = name
        elif "24" in name and "pivot" in name.lower():
            found["pivot_2024"] = name
        elif "25" in name and "pivot" in name.lower():
            found["pivot_2025"] = name
    return found
