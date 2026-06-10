"""
원본 데이터에서 SPC 분석용 표본 채취 모듈.

subgroup 채취 규칙 (기본):
- 군 내: subgroup_size(=5)개 **연속** 측정값 (동일 LOT·일자·교대 블록)
- 군 간: **일자를 우선**하여 여러 날짜에서 **랜덤** 25군 채취
- LOT · 주/야 교대 경계는 군 내에서 유지

대체 규칙 (블록 채취 불가 시):
- 필터된 데이터 **순번(시간·원본 순서)** 기준 연속 n개를 1 subgroup으로 보고
- 후보군 중 **랜덤**으로 n_subgroups개 선택 (예: LOT마다 1행만 있는 export)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Literal, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SamplingMethod = Literal["random", "systematic", "latest", "subgroup", "consecutive"]

DAY_SHIFT_START_HOUR = 8
DAY_SHIFT_END_HOUR = 20


class SampleSelector:
    """공정능력·관리도 분석을 위한 표본 선정."""

    def __init__(self, df: pd.DataFrame, value_col: str = "value"):
        self.df = df.copy()
        self.value_col = value_col

    def select(
        self,
        method: SamplingMethod = "consecutive",
        sample_size: Optional[int] = None,
        subgroup_size: int = 5,
        n_subgroups: Optional[int] = 25,
        random_state: int = 42,
    ) -> pd.DataFrame | tuple[pd.DataFrame, int]:
        n = len(self.df)
        if n == 0:
            raise ValueError("채취할 데이터가 없습니다.")

        if method in ("subgroup", "consecutive"):
            return self._select_consecutive_subgroups(
                subgroup_size, n_subgroups or 25, random_state=random_state
            )

        if method == "random":
            size = sample_size or min(100, n)
            return self.df.sample(n=min(size, n), random_state=random_state).reset_index(drop=True)

        if method == "systematic":
            size = sample_size or min(100, n)
            step = max(1, n // size)
            return self.df.iloc[::step].head(size).reset_index(drop=True)

        if method == "latest":
            size = sample_size or min(100, n)
            sort_col = "timestamp" if "timestamp" in self.df.columns else self.value_col
            return (
                self.df.sort_values(sort_col, ascending=False)
                .head(size)
                .sort_values(sort_col)
                .reset_index(drop=True)
            )

        raise ValueError(f"지원하지 않는 채취 방식: {method}")

    def _select_consecutive_subgroups(
        self,
        subgroup_size: int,
        n_subgroups: int,
        random_state: int = 42,
    ) -> tuple[pd.DataFrame, int]:
        """
        1) LOT·일자·교대 블록별 연속 n개 후보군 생성
        2) 일자별로 골고루 랜덤 추출하여 n_subgroups개 선택
        """
        if subgroup_size < 2:
            raise ValueError("subgroup_size >= 2 가 필요합니다.")

        df = self._prepare_for_sampling()
        blocks = self._split_blocks(df)
        strategy = "date_block"
        candidates = self._collect_candidates(blocks, subgroup_size)

        if not candidates:
            logger.warning(
                "LOT·일자·교대 블록으로 subgroup 후보 없음 → 순번 기준 연속 랜덤 채취로 대체합니다."
            )
            strategy = "sequence_random"
            candidates = self._collect_sequence_candidates(self._order_for_sequence(), subgroup_size)

        if not candidates:
            raise ValueError(
                f"채취 가능한 subgroup 없음: 데이터 {len(df)}행, 군당 {subgroup_size}개 연속 구간 필요"
            )

        rng = np.random.default_rng(random_state)
        if strategy == "sequence_random":
            picked = self._random_pick_sequence(candidates, n_subgroups, rng)
        else:
            picked = self._random_pick_by_date(candidates, n_subgroups, rng)

        selected_parts: list[pd.DataFrame] = []
        for subgroup_id, cand in enumerate(picked, start=1):
            chunk = cand["chunk"].copy()
            chunk["subgroup_id"] = subgroup_id
            chunk["sampling_block"] = cand["block_key"]
            chunk["sampling_date"] = cand["date"]
            chunk["sampling_strategy"] = strategy
            if "seq_start" in cand:
                chunk["seq_start_index"] = cand["seq_start"]
            selected_parts.append(chunk)

        result = pd.concat(selected_parts, ignore_index=True)
        n_got = int(result["subgroup_id"].nunique())
        dates_used = sorted(result["sampling_date"].unique())

        if n_got < n_subgroups:
            logger.warning("목표 %d subgroup → %d subgroup (후보 %d개)", n_subgroups, n_got, len(candidates))

        drop_cols = [
            c
            for c in ("_sort_time", "_block_date", "_block_shift", "_block_lot", "_seq_ord")
            if c in result.columns
        ]
        result = result.drop(columns=drop_cols)

        if strategy == "sequence_random":
            logger.info(
                "순번 랜덤 subgroup: %d군 × n=%d (후보 %d개, 순번 구간 랜덤)",
                n_got, subgroup_size, len(candidates),
            )
        else:
            logger.info(
                "랜덤 subgroup: %d군 × n=%d, 사용 일자 %d개 %s",
                n_got, subgroup_size, len(dates_used),
                dates_used[:5] if len(dates_used) > 5 else dates_used,
            )
        return result.reset_index(drop=True), subgroup_size

    def _collect_candidates(
        self,
        blocks: list[tuple[str, pd.DataFrame]],
        subgroup_size: int,
    ) -> list[dict]:
        """블록별 비중첩 연속 윈도우 → 후보 subgroup 목록."""
        candidates: list[dict] = []
        for block_key, block_df in blocks:
            block_df = block_df.sort_values("_sort_time").reset_index(drop=True)
            n_rows = len(block_df)
            if n_rows < subgroup_size:
                continue
            block_date = str(block_df["_block_date"].iloc[0])
            for start in range(0, n_rows - subgroup_size + 1, subgroup_size):
                chunk = block_df.iloc[start : start + subgroup_size]
                candidates.append({
                    "date": block_date,
                    "block_key": str(block_key),
                    "chunk": chunk,
                })
        return candidates

    def _order_for_sequence(self) -> pd.DataFrame:
        """순번 채취용 정렬: 측정일시 있으면 시간순, 없으면 파일 읽기 순서."""
        df = self.df.copy()
        if "timestamp" in df.columns:
            t = pd.to_datetime(df["timestamp"], errors="coerce")
            if t.notna().any():
                df["_sort_time"] = t
                return df.sort_values("_sort_time", na_position="last").reset_index(drop=True)
        return df.reset_index(drop=True)

    def _collect_sequence_candidates(
        self,
        df: pd.DataFrame,
        subgroup_size: int,
    ) -> list[dict]:
        """
        전체 데이터 순번(시간·읽기 순서)상 연속 subgroup_size개 윈도우 후보.
        기본: 비중첩 stride=subgroup_size. 후보 부족 시 슬라이딩(겹침) 윈도우 추가.
        """
        ordered = df.reset_index(drop=True)
        n_rows = len(ordered)
        if n_rows < subgroup_size:
            return []

        candidates: list[dict] = []
        for start in range(0, n_rows - subgroup_size + 1, subgroup_size):
            chunk = ordered.iloc[start : start + subgroup_size]
            candidates.append({
                "date": "SEQUENCE",
                "block_key": f"seq_{start}-{start + subgroup_size - 1}",
                "chunk": chunk,
                "seq_start": start,
            })

        min_needed = max(1, min(25, n_rows // subgroup_size))
        if len(candidates) < min_needed:
            seen = {c["seq_start"] for c in candidates}
            for start in range(0, n_rows - subgroup_size + 1):
                if start in seen:
                    continue
                chunk = ordered.iloc[start : start + subgroup_size]
                candidates.append({
                    "date": "SEQUENCE",
                    "block_key": f"seq_{start}-{start + subgroup_size - 1}",
                    "chunk": chunk,
                    "seq_start": start,
                })
        return candidates

    @staticmethod
    def _random_pick_sequence(
        candidates: list[dict],
        n_subgroups: int,
        rng: np.random.Generator,
    ) -> list[dict]:
        """순번 후보군에서 무작위 n_subgroups개 (시작 순번 오름차순 정렬)."""
        if len(candidates) <= n_subgroups:
            return sorted(candidates, key=lambda c: c["seq_start"])
        picks = rng.choice(len(candidates), size=n_subgroups, replace=False)
        return sorted((candidates[int(i)] for i in picks), key=lambda c: c["seq_start"])

    @staticmethod
    def _random_pick_by_date(
        candidates: list[dict],
        n_subgroups: int,
        rng: np.random.Generator,
    ) -> list[dict]:
        """일자별 후보를 섞은 뒤 라운드로빈으로 n_subgroups개 랜덤 선택."""
        by_date: dict[str, list[dict]] = defaultdict(list)
        for c in candidates:
            by_date[c["date"]].append(c)

        dates = list(by_date.keys())
        rng.shuffle(dates)
        for d in dates:
            rng.shuffle(by_date[d])

        selected: list[dict] = []
        date_idx = 0
        max_rounds = n_subgroups * max(len(dates), 1) + 1
        rounds = 0

        while len(selected) < n_subgroups and rounds < max_rounds:
            rounds += 1
            progressed = False
            for _ in range(len(dates)):
                d = dates[date_idx % len(dates)]
                date_idx += 1
                if by_date[d]:
                    selected.append(by_date[d].pop())
                    progressed = True
                    if len(selected) >= n_subgroups:
                        break
            if not progressed:
                break

        return selected

    def _prepare_for_sampling(self) -> pd.DataFrame:
        df = self.df.copy()
        if "timestamp" in df.columns:
            df["_sort_time"] = pd.to_datetime(df["timestamp"], errors="coerce")
        else:
            df["_sort_time"] = pd.NaT

        df["_block_lot"] = df["lot"].astype(str) if "lot" in df.columns else "ALL"
        df["_block_date"] = df["_sort_time"].dt.date.astype(str)
        df.loc[df["_sort_time"].isna(), "_block_date"] = "UNKNOWN"

        if "shift" in df.columns:
            df["_block_shift"] = df["shift"].astype(str)
        else:
            df["_block_shift"] = df["_sort_time"].apply(self._infer_shift)

        return df.sort_values(["_block_date", "_block_shift", "_block_lot", "_sort_time"])

    @staticmethod
    def _infer_shift(ts: pd.Timestamp) -> str:
        if pd.isna(ts):
            return "UNKNOWN"
        h = ts.hour
        if DAY_SHIFT_START_HOUR <= h < DAY_SHIFT_END_HOUR:
            return "주간"
        return "야간"

    def _split_blocks(self, df: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
        key_cols = ["_block_date", "_block_shift", "_block_lot"]  # 일자 우선
        blocks: list[tuple[str, pd.DataFrame]] = []
        for key, grp in df.groupby(key_cols, sort=False):
            date, shift, lot = key
            label = f"{date}|{shift}|LOT={lot}"
            blocks.append((label, grp))
        return blocks

    @staticmethod
    def to_subgroup_matrix(df: pd.DataFrame, subgroup_size: int, value_col: str = "value") -> np.ndarray:
        if "subgroup_id" in df.columns:
            groups = [g[value_col].to_numpy() for _, g in df.sort_values("subgroup_id").groupby("subgroup_id")]
            return np.array(groups)
        values = df[value_col].to_numpy()
        n_groups = len(values) // subgroup_size
        return values[: n_groups * subgroup_size].reshape(n_groups, subgroup_size)

    @staticmethod
    def recommend_chart_type(n_total: int, subgroup_size: int = 5) -> Literal["xbar_r", "imr"]:
        if n_total >= subgroup_size * 2 and subgroup_size >= 2:
            return "xbar_r"
        return "imr"
