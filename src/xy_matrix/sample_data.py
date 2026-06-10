"""X-Y 매트릭스 Raw data 샘플 생성."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import INPUT_PATH


def generate_xy_raw_sample(
    output_dir: str | Path | None = None,
    n_rows: int = 120,
    seed: int = 42,
) -> Path:
    rng = np.random.default_rng(seed)
    n = n_rows

    외기온도 = rng.normal(25, 5, n)
    예열온도 = rng.normal(180, 15, n) + 0.3 * 외기온도
    압력 = rng.normal(2.5, 0.2, n)
    라인 = rng.choice(["A", "B", "C"], n, p=[0.5, 0.3, 0.2])
    생산일 = pd.date_range("2026-01-01", periods=n, freq="h")
    y = 130.0 + 0.05 * 외기온도 + 0.02 * (예열온도 - 180) + rng.normal(0, 0.08, n)

    type_row = [None, "생산일", "결과 Y", "계량형 X", "계량형 X", "계량형 X", "범주형 X"]
    name_row = [None, "생산일", "인플레이터중량", "외기온도", "예열온도", "압력", "라인"]

    data = pd.DataFrame({
        "": range(1, n + 1),
        "생산일": 생산일,
        "인플레이터중량": np.round(y, 4),
        "외기온도": np.round(외기온도, 2),
        "예열온도": np.round(예열온도, 2),
        "압력": np.round(압력, 3),
        "라인": 라인,
    })

    out_dir = Path(output_dir or INPUT_PATH)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "xy_matrix_raw_sample.xlsx"

    sheet = pd.DataFrame([type_row, name_row])
    sheet.columns = data.columns
    combined = pd.concat([sheet, data], ignore_index=True)
    combined.to_excel(out, sheet_name="Raw data", index=False, header=False)
    return out
