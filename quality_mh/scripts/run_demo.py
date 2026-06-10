"""CLI 데모 실행."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quality_mh.pipeline import QualityMhPipeline


def main() -> None:
    pipeline = QualityMhPipeline()
    state = pipeline.run_demo()
    state = pipeline.run_calculation(state)

    print("=== 품질 M/H 데모 실행 결과 ===")
    print(f"발생빈도: {len(state.frequency_df)}건")
    print(f"단위시간: {len(state.unit_time_df)}건")
    print(f"MH 결과: {len(state.mh_df)}건")
    print()
    print(state.mh_df[["factory_name", "domain", "task_name", "frequency_value", "unit_time_value", "mh_value", "validation_status"]])

    out = ROOT / "data" / "output" / "품질MH_데모결과.xlsx"
    pipeline.export_excel(state, out)
    print(f"\n결과 저장: {out}")


if __name__ == "__main__":
    main()
