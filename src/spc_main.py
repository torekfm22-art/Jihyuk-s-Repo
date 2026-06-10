"""
SPC 공정능력·관리도 자동 분석 CLI

사용법:
    python -m src.spc_main
    python scripts/run_demo.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.spc.pipeline import SpcJobConfig, SpcPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "spc_automation.log", encoding="utf-8"),
    ],
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MES/QMS xlsx SPC 분석")
    parser.add_argument("--config", "-c", default="config/spc_job.yaml")
    parser.add_argument("--mes-file")
    parser.add_argument("--qms-file")
    parser.add_argument("--usl", type=float)
    parser.add_argument("--lsl", type=float)
    parser.add_argument("--process")
    parser.add_argument("--characteristic")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = ROOT / args.config
    config = SpcJobConfig.from_yaml(config_path) if config_path.exists() else SpcJobConfig(
        input_files=["mes_data.xlsx", "qms_data.xlsx"], usl=10.5, lsl=9.5
    )
    if args.mes_file:
        config.mes_file = args.mes_file
    if args.qms_file:
        config.qms_file = args.qms_file
    if args.usl is not None:
        config.usl = args.usl
    if args.lsl is not None:
        config.lsl = args.lsl
    if args.process:
        config.filter_process = args.process
    if args.characteristic:
        config.filter_characteristic = args.characteristic

    try:
        result = SpcPipeline(config).run()
    except Exception as exc:
        logging.exception("SPC 분석 실패: %s", exc)
        return 1

    a = result.analysis
    print("\n" + "=" * 60)
    print(f" 표본: {result.sample_count}건 | {a.control_limits.chart_type}")
    if a.capability:
        print(f" Cp={a.capability.cp:.4f}, Cpk={a.capability.cpk:.4f}")
    print(f" Excel: {result.report_paths.get('excel')}")
    print(f" PDF:   {result.report_paths.get('pdf')}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
