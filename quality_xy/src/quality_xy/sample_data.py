"""데모용 샘플 데이터 생성."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def make_sample_datasets() -> dict[str, pd.DataFrame]:
    base = datetime(2025, 3, 1, 8, 0, 0)
    barcodes = [f"BC{i:04d}" for i in range(1, 21)]
    lots = [f"LOT{(i - 1) // 4 + 1:03d}" for i in range(1, 21)]

    # Y: 불량 이벤트
    defect_rows = []
    for i, bc in enumerate(barcodes):
        t = base + timedelta(hours=i * 2)
        defect_rows.append({
            "바코드": bc,
            "LOT": lots[i],
            "발생일시": t,
            "불량점수": 1 + (i % 5) + (0.3 if i % 3 == 0 else 0),
            "불량유형": ["스크래치", "치수", "외관", "기능"][i % 4],
        })
    defects = pd.DataFrame(defect_rows)

    # X1: 공정 검사 (바코드 직접 연결)
    process_rows = []
    for i, bc in enumerate(barcodes):
        t = base + timedelta(hours=i * 2, minutes=15)
        process_rows.append({
            "바코드": bc,
            "검사일시": t,
            "압력값": 100 + (i % 7) * 2 + (5 if i % 3 == 0 else 0),
            "속도": 50 + i,
        })
    process = pd.DataFrame(process_rows)

    # X2: 설비 로그 (LOT 연결 — 바코드 없음)
    equip_rows = []
    for i, lot in enumerate(lots):
        t = base + timedelta(hours=i * 2, minutes=20)
        equip_rows.append({
            "LOT번호": lot,
            "기록시각": t,
            "온도": 22 + (i % 5) * 0.8 + (3 if i % 3 == 0 else 0),
            "습도": 45 + (i % 5),
        })
    equipment = pd.DataFrame(equip_rows)

    # X3: 자재 (바코드 ↔ LOT 브릿지 테이블 역할은 defects에 있음; 여기선 LOT만)
    material_rows = []
    for i, lot in enumerate(sorted(set(lots))):
        material_rows.append({
            "로트": lot,
            "입고일시": base - timedelta(days=1, hours=i),
            "점도": 10 + i * 1.2,
        })
    material = pd.DataFrame(material_rows)

    return {
        "불량이력": defects,
        "공정검사": process,
        "설비로그": equipment,
        "자재이력": material,
    }
