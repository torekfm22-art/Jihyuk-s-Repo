"""통합 테스트 실행 스크립트."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quality_mh.calculation_engine import aggregate_by_plant, calculate_quantitative_record
from quality_mh.database import init_db, load_calc_results, save_calc_result, save_freq_db, save_record
from quality_mh.excel_exporter import export_excel
from quality_mh.sample_data import build_all_scenarios
from quality_mh.validation import validate_record


def main() -> None:
    init_db()
    print("=" * 55)
    print("  품질 M/H 통합 테스트")
    print("=" * 55)

    results = []
    for rec, rule, freq in build_all_scenarios():
        validate_record(rec, rule, freq)
        save_freq_db(freq)
        save_record(rec, "quantitative")
        result = calculate_quantitative_record(rec, rule, freq)
        save_calc_result(result)
        results.append(result)
        print(f"\n[{rec.task_code}] {rec.wg} / {rec.task_name}")
        print(f"  발생빈도     : {result.final_frequency:,.1f}")
        print(f"  표준작업시간 : {result.standard_work_time_hr:,.3f} hr")
        print(f"  부가공수 후  : {result.final_work_time_hr:,.3f} hr")
        print(f"  표준공수     : M/H {result.standard_mh:.4f} / M/D {result.standard_md:.4f}")
        print(f"  표준인원     : {result.standard_headcount}명")

    print("\n[공장별 집계]")
    for plant, agg in aggregate_by_plant(results).items():
        print(f"  {plant}: M/H {agg['standard_mh']:.4f}, 인원 {agg['standard_headcount']}명")

    out = ROOT / "test_output.xlsx"
    export_excel(results, output_path=out)
    print(f"\n[엑셀] {out} ({out.stat().st_size:,} bytes)")
    print(f"[DB]  calc_results {len(load_calc_results())}건 저장")
    print("\n통합 테스트 완료")


if __name__ == "__main__":
    main()
