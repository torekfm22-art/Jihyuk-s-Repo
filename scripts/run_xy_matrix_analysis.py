"""X-Y 매트릭스 분석 실행 (CLI)."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import INPUT_PATH, OUTPUT_PATH
from src.xy_matrix.sample_data import generate_xy_raw_sample
from src.xy_matrix import analyze_xy_matrix


def main() -> None:
    parser = argparse.ArgumentParser(description="X-Y 매트릭스 자동 분석")
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="입력 Excel/CSV 경로 (미지정 시 샘플 생성 후 분석)",
    )
    parser.add_argument("--y", type=str, default=None, help="Y인자 컬럼명")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="결과 Excel 경로",
    )
    parser.add_argument("--no-multi", action="store_true", help="다중회귀 생략")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else generate_xy_raw_sample()
    out_path = Path(
        args.output or Path(OUTPUT_PATH) / "xy_matrix_result.xlsx"
    )

    result = analyze_xy_matrix(
        input_path,
        y_column=args.y,
        run_multiple_reg=not args.no_multi,
        output_format="excel",
        output_path=out_path,
    )

    def safe_print(text: str) -> None:
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("cp949", errors="replace").decode("cp949"))

    safe_print(result["matrix_display"].to_string(index=False))
    safe_print("")
    safe_print(result["recommendations"].get("summary", ""))
    for ctp in result["recommendations"].get("ctp_factors", []):
        safe_print(
            f"  CTP: {ctp['factor']} {ctp['symbol']} -> {ctp['chart_recommendation']}"
        )
    print(f"\nExcel 저장: {out_path}")
    if result.get("pareto_chart_path"):
        print(f"파레토 차트: {result['pareto_chart_path']}")


if __name__ == "__main__":
    main()
