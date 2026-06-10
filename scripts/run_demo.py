"""가상 MES/QMS xlsx로 SPC 분석 데모 실행."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    print("=" * 60)
    print(" 1. 샘플 xlsx 생성")
    print("=" * 60)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_sample_data.py")], check=True, cwd=ROOT)

    print("\n" + "=" * 60)
    print(" 2. SPC 분석 (종합 Excel + PDF)")
    print("=" * 60)
    subprocess.run([sys.executable, "-m", "src.spc_main"], check=True, cwd=ROOT)

    out = ROOT / "data" / "output"
    reports = sorted(out.glob("SPC_종합보고서_*.xlsx"), key=lambda p: p.stat().st_mtime)
    pdfs = sorted(out.glob("SPC_종합보고서_*.pdf"), key=lambda p: p.stat().st_mtime)
    if reports:
        print(f"\n종합 Excel: {reports[-1]}")
    if pdfs:
        print(f"종합 PDF:   {pdfs[-1]}")
    print(f"차트 폴더:  {out / 'charts'}")
    print("\nGUI 실행: python src/spc_gui.py  또는 run_spc_app.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
