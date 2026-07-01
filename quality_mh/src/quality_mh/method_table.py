"""method table.xlsx 기반 업무별 산정방법 매핑."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "method_table.json"

UNIT_TIME_METHOD_DESC: dict[str, str] = {
    "모답스": "모범답안(표준작업) 기반 단위시간 — 현재는 직접 기입 (추후 자동 산출 예정)",
    "관측법": "작업 관측·시간측정 기반 — 현재는 직접 기입 (추후 자동 산출 예정)",
    "업무기준": "업무기준서·표준절차 기반 — 현재는 직접 기입 (추후 자동 산출 예정)",
    "동작모듈화": "동작모듈 분해 기반 — 현재는 직접 기입 (추후 자동 산출 예정)",
}

FREQ_METHOD_DESC: dict[str, str] = {
    "3개년 가중평균": "전년·전전년·전전전년 실적에 가중치(5:3:2)를 적용한 가중평균",
    "생산계획 연동": "전년 검사수량/생산실적 비율을 당해년 생산계획에 반영 (FG expected qty 양식)",
    "수행주기": "일/주/월/분기/연 수행주기 기반 — M/H 산출 Tool에서는 ② 메뉴에서 입력",
}


class MethodTableEntry(BaseModel):
    wg: str
    task_name: str
    unit_time_method: str
    frequency_method: str
    remark: str = ""

    @property
    def key(self) -> str:
        return f"{self.wg}|{self.task_name}"


@lru_cache(maxsize=1)
def load_method_table() -> list[MethodTableEntry]:
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return [MethodTableEntry.model_validate(item) for item in raw]


def get_method_entry(wg: str, task_name: str) -> MethodTableEntry | None:
    for entry in load_method_table():
        if entry.wg == wg and entry.task_name == task_name:
            return entry
    return None


def list_wg_values() -> list[str]:
    seen: list[str] = []
    for entry in load_method_table():
        if entry.wg not in seen:
            seen.append(entry.wg)
    return seen


def entries_for_tool(*, wg_filter: str = "전체") -> list[MethodTableEntry]:
    """수행주기 제외 — M/H 산출 Tool 대상 목록."""
    rows = load_method_table()
    if wg_filter != "전체":
        rows = [r for r in rows if r.wg == wg_filter]
    return [r for r in rows if r.frequency_method != "수행주기"]


def entry_to_display_row(entry: MethodTableEntry) -> dict[str, Any]:
    return {
        "W/G": entry.wg,
        "업무항목": entry.task_name,
        "단위시간 산정방법": entry.unit_time_method,
        "발생빈도 산정방법": entry.frequency_method,
        "비고": entry.remark,
    }
