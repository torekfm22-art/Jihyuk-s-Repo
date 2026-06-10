#!/usr/bin/env python
"""입고검사 발생빈도 분석(생산계획 연동) 자동 집계 CLI."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quality_mh.incoming_frequency_analyzer import (  # noqa: E402
    analyze_workbook_sheets_with_raw,
    to_frequency_dataframe,
)
from quality_mh.incoming_workbook_reader import read_incoming_workbook  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="입고검사 발생빈도(샘플링/전수/무검사) 자동 집계",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="첨부) 1. (천안EBS) 입고 MH 산출 (상세) 근거_v2.xlsx 경로",
    )
    parser.add_argument(
        "--output",
        default="",
        help="결과 xlsx 저장 경로 (미지정 시 data/output 자동 생성)",
    )
    parser.add_argument(
        "--years",
        default="2024,2025",
        help="분석 연도 (쉼표 구분)",
    )
    args = parser.parse_args()

    source = Path(args.file)
    if not source.exists():
        print(f"파일 없음: {source}")
        return 1

    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    sheets = read_incoming_workbook(source)
    summary, raw_by_year, pivot_by_year, audit = analyze_workbook_sheets_with_raw(
        sheets,
        years=years,
    )
    if summary.empty:
        print("분석 결과 없음 - 검사빈도(부품별) 리스트 시트를 확인하세요.")
        return 1

    for line in audit:
        print(line)
    freq_df = to_frequency_dataframe(summary)
    out_dir = ROOT / "data" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.output) if args.output else out_dir / f"입고검사_발생빈도_{ts}.xlsx"

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for year, raw_df in raw_by_year.items():
            raw_df.to_excel(writer, sheet_name=f"Raw_{year}", index=False)
        for year, pivot_df in pivot_by_year.items():
            pivot_df.to_excel(writer, sheet_name=f"Pivot_{year}", index=False)
        summary.to_excel(writer, sheet_name="발생빈도_집계", index=False)
        if not freq_df.empty:
            freq_df.to_excel(writer, sheet_name="MH연동_빈도", index=False)

    print(f"완료: {out_path}")
    print(f"집계 행: {len(summary)} / MH연동: {len(freq_df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
