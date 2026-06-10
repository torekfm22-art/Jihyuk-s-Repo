"""MES/QMS xlsx 샘플 데이터 생성."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import INPUT_PATH
from src.spc.sample_data import generate_sample_files


if __name__ == "__main__":
    mes_path, qms_path = generate_sample_files(INPUT_PATH)
    print(f"MES xlsx: {mes_path} (150행)")
    print(f"QMS xlsx: {qms_path} (100행)")
