"""X-Y 매트릭스 분석용 Raw data 샘플 Excel 생성."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.xy_matrix.sample_data import generate_xy_raw_sample


if __name__ == "__main__":
    path = generate_xy_raw_sample()
    print(f"샘플 생성: {path}")
