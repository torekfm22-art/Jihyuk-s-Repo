"""MES/QMS 샘플 xlsx 생성 (GUI·CLI 공용)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _mes_rows(n: int, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "측정일시": pd.Timestamp("2026-05-01") + pd.Timedelta(minutes=i * 10),
            "공정": rng.choice(["조립공정", "가공공정"], p=[0.6, 0.4]),
            "품목": "PART-A001",
            "검사항목": rng.choice(["외경", "내경", "두께"], p=[0.5, 0.3, 0.2]),
            "LOT": f"LOT-{i // 10 + 1:03d}",
            "측정값": round(float(rng.normal(10.0, 0.08)), 4),
            "USL": 10.50,
            "LSL": 9.50,
            "Target": 10.00,
        })
    return pd.DataFrame(rows)


def _qms_rows(n: int, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "검사일시": pd.Timestamp("2026-05-01") + pd.Timedelta(minutes=i * 12 + 5),
            "공정명": rng.choice(["조립공정", "도장공정"], p=[0.7, 0.3]),
            "품번": "PART-A001",
            "특성": rng.choice(["외경", "두께"], p=[0.6, 0.4]),
            "배치번호": f"BATCH-{i // 8 + 1:03d}",
            "검사값": round(float(rng.normal(10.0, 0.09)), 4),
            "상한": 10.50,
            "하한": 9.50,
            "목표": 10.00,
        })
    return pd.DataFrame(rows)


def generate_sample_files(output_dir: str | Path, seed: int = 42) -> tuple[Path, Path]:
    """샘플 MES/QMS xlsx 2건 생성. (mes_path, qms_path) 반환."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    mes_path = out_dir / "mes_data.xlsx"
    qms_path = out_dir / "qms_data.xlsx"
    _mes_rows(150, rng).to_excel(mes_path, index=False, sheet_name="측정데이터")
    _qms_rows(100, rng).to_excel(qms_path, index=False, sheet_name="검사결과")
    return mes_path, qms_path
