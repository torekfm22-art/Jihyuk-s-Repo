"""데이터셋 간 컬럼 교집합(연결 키) 탐지."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quality_xy.loader import DatasetProfile, columns_for_linking, normalize_key_value


@dataclass(frozen=True)
class KeyLink:
    dataset_a: str
    column_a: str
    dataset_b: str
    column_b: str
    intersection_count: int
    overlap_ratio_a: float
    overlap_ratio_b: float
    jaccard: float

    @property
    def min_overlap(self) -> float:
        return min(self.overlap_ratio_a, self.overlap_ratio_b)

    @property
    def label(self) -> str:
        return (
            f"{self.dataset_a}.{self.column_a} ↔ {self.dataset_b}.{self.column_b} "
            f"(겹침 {self.intersection_count:,}, Jaccard {self.jaccard:.1%})"
        )


def _overlap_stats(values_a: set[str], values_b: set[str]) -> tuple[int, float, float, float]:
    if not values_a or not values_b:
        return 0, 0.0, 0.0, 0.0
    inter = values_a & values_b
    union = values_a | values_b
    count = len(inter)
    ratio_a = count / len(values_a)
    ratio_b = count / len(values_b)
    jaccard = count / len(union) if union else 0.0
    return count, ratio_a, ratio_b, jaccard


def discover_key_links(
    profiles: dict[str, DatasetProfile],
    *,
    min_intersection: int = 3,
    min_overlap_ratio: float = 0.05,
    columns: dict[str, list[str]] | None = None,
) -> list[KeyLink]:
    """모든 데이터셋 쌍에서 값이 겹치는 컬럼 조합을 찾는다."""
    links: list[KeyLink] = []
    names = list(profiles.keys())

    for i, name_a in enumerate(names):
        for name_b in names[i + 1 :]:
            prof_a = profiles[name_a]
            prof_b = profiles[name_b]
            cols_a = columns.get(name_a, columns_for_linking(prof_a.df)) if columns else columns_for_linking(prof_a.df)
            cols_b = columns.get(name_b, columns_for_linking(prof_b.df)) if columns else columns_for_linking(prof_b.df)

            for col_a in cols_a:
                if col_a not in prof_a.df.columns:
                    continue
                values_a = prof_a.key_values(col_a)
                for col_b in cols_b:
                    if col_b not in prof_b.df.columns:
                        continue
                    values_b = prof_b.key_values(col_b)
                    count, ratio_a, ratio_b, jaccard = _overlap_stats(values_a, values_b)
                    if count < min_intersection:
                        continue
                    if ratio_a < min_overlap_ratio and ratio_b < min_overlap_ratio:
                        continue
                    links.append(
                        KeyLink(
                            dataset_a=name_a,
                            column_a=col_a,
                            dataset_b=name_b,
                            column_b=col_b,
                            intersection_count=count,
                            overlap_ratio_a=ratio_a,
                            overlap_ratio_b=ratio_b,
                            jaccard=jaccard,
                        )
                    )

    links.sort(key=lambda x: (x.intersection_count, x.jaccard), reverse=True)
    return links


def links_to_dataframe(links: list[KeyLink]) -> pd.DataFrame:
    if not links:
        return pd.DataFrame(
            columns=[
                "dataset_a", "column_a", "dataset_b", "column_b",
                "intersection_count", "overlap_ratio_a", "overlap_ratio_b", "jaccard",
            ]
        )
    return pd.DataFrame([link.__dict__ for link in links])
