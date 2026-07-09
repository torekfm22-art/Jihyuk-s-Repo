"""
원본 데이터에서 SPC 분석용 표본 채취 모듈.

subgroup 채취 규칙 (기본):
- 블록: 라인·설비·공정·**일자·교대** (LOT 제외 — LOT당 1행 export 대응)
- 군 내: subgroup_size(=5)개 **시간순 연속** 측정값 (동일 블록 내)
- 군 간: **일자를 우선**하여 여러 날짜에서 **랜덤** 25군 채취
- 교대·일자 경계는 군 내에서 유지

대체 규칙 (블록 후보 0개일 때만):
- 필터된 데이터 **순번(시간·원본 순서)** 기준 연속 n개를 1 subgroup으로 보고
- 후보군 중 **랜덤**으로 n_subgroups개 선택

I-MR 채취 (권장 — 공정 상태 대표):
- 항목별 자동 분리 후 **단일 검사항목** 데이터에 대해 대표 1점씩
- 1시간 1개: 라인·설비·공정·일·교대·**시간(1h)** 당 1점 (LOT 제외)
- 단위: Lot / 1시간 / 교대 / Cycle(N건) / 자동
- 표본 수 = n_subgroups (기본 25점) — 최신 구간 우선
"""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from typing import Literal, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SamplingMethod = Literal["random", "systematic", "latest", "subgroup", "consecutive"]
ImrSamplingUnit = Literal["auto", "lot", "hour", "shift", "cycle"]

IMR_UNIT_LABELS: dict[ImrSamplingUnit, str] = {
    "auto": "자동 (데이터 기반)",
    "lot": "Lot당 1개",
    "hour": "1시간 1개",
    "shift": "교대당 1개",
    "cycle": "Cycle(N건)당 1개",
}

DAY_SHIFT_START_HOUR = 8
DAY_SHIFT_END_HOUR = 20

SubgroupBoundaryKey = Literal["date", "shift", "lot", "line", "machine", "process"]

SUBGROUP_BOUNDARY_LABELS: dict[SubgroupBoundaryKey, str] = {
    "date": "날짜",
    "shift": "교대",
    "lot": "LOT",
    "line": "라인",
    "machine": "설비",
    "process": "공정",
}

BLOCK_COLUMN_MAP: dict[SubgroupBoundaryKey, str] = {
    "date": "_block_date",
    "shift": "_block_shift",
    "lot": "_block_lot",
    "line": "_block_line",
    "machine": "_block_machine",
    "process": "_block_process",
}

AUTO_SUBGROUP_BOUNDARY_ORDER: tuple[SubgroupBoundaryKey, ...] = (
    "line", "machine", "process", "date", "shift", "lot",
)

# 사용자 지정 — Excel에 컬럼이 없어도 선택 가능한 가상 분리 조건
VIRTUAL_BOUNDARY_SHIFT = "@virtual:shift"
VIRTUAL_BOUNDARY_DATE = "@virtual:date"

VIRTUAL_BOUNDARY_LABELS: dict[str, str] = {
    VIRTUAL_BOUNDARY_SHIFT: "교대 (시간대 자동)",
    VIRTUAL_BOUNDARY_DATE: "날짜 (측정일시에서)",
}


def is_virtual_boundary_column(col: str) -> bool:
    return col in (VIRTUAL_BOUNDARY_SHIFT, VIRTUAL_BOUNDARY_DATE)


def virtual_boundary_block_column(col: str) -> str | None:
    if col == VIRTUAL_BOUNDARY_SHIFT:
        return "_block_shift"
    if col == VIRTUAL_BOUNDARY_DATE:
        return "_block_date"
    return None


def boundary_column_display_name(col: str) -> str:
    return VIRTUAL_BOUNDARY_LABELS.get(col, col)


def _df_has_timestamp(df: pd.DataFrame) -> bool:
    if "timestamp" not in df.columns:
        return False
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    return bool(ts.notna().any())


def list_virtual_boundary_options(df: pd.DataFrame) -> list[tuple[str, str]]:
    """(UI 표시명, 내부 토큰) — timestamp 있으면 교대·날짜 가상 옵션 제공."""
    if df is None or df.empty:
        return []
    out: list[tuple[str, str]] = []
    if _df_has_timestamp(df):
        out.append((VIRTUAL_BOUNDARY_LABELS[VIRTUAL_BOUNDARY_SHIFT], VIRTUAL_BOUNDARY_SHIFT))
        out.append((VIRTUAL_BOUNDARY_LABELS[VIRTUAL_BOUNDARY_DATE], VIRTUAL_BOUNDARY_DATE))
    return out


def resolve_auto_subgroup_boundary_keys(df: pd.DataFrame) -> list[str]:
    """자동: 날짜·교대 + (있으면) 라인·설비·공정. LOT은 정렬·연속성에 활용."""
    keys: list[str] = []
    if "line" in df.columns:
        keys.append("line")
    if "machine" in df.columns:
        keys.append("machine")
    if "process" in df.columns or "process_name" in df.columns:
        keys.append("process")
    if "timestamp" in df.columns or "measure_date" in df.columns:
        keys.append("date")
    if "shift" in df.columns or "timestamp" in df.columns:
        keys.append("shift")
    if not keys:
        keys = ["date", "shift"]
    return keys


def format_subgroup_boundary_labels(
    keys: list[str] | None = None,
    *,
    columns: list[str] | None = None,
) -> str:
    if columns:
        return " · ".join(boundary_column_display_name(str(c)) for c in columns)
    if not keys:
        return ""
    return " · ".join(SUBGROUP_BOUNDARY_LABELS.get(k, k) for k in keys if k in SUBGROUP_BOUNDARY_LABELS)


def _col_key(name: str) -> str:
    return str(name).strip().lower().replace(" ", "").replace("_", "")


def is_date_like_boundary_column(col: str, df: pd.DataFrame) -> bool:
    if col == VIRTUAL_BOUNDARY_DATE:
        return True
    if col not in df.columns:
        return False
    if col in ("timestamp", "measure_date", "measure_time", "_strat_date"):
        return True
    ck = _col_key(col)
    if ck in (
        "timestamp", "measuredate", "measuretime", "측정일", "작업일", "검사일",
        "검사시간", "측정시간", "date", "datetime",
    ):
        return True
    if any(k in str(col) for k in ("측정일", "작업일", "검사일", "검사시간", "측정시간", "일시", "날짜", "트랜잭션")):
        return True
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        return True
    try:
        parsed = pd.to_datetime(df[col], errors="coerce")
        if parsed.notna().mean() > 0.8:
            return True
    except Exception:
        pass
    return False


def is_lot_like_boundary_column(col: str, df: pd.DataFrame) -> bool:
    if col not in df.columns:
        return False
    if col == "lot":
        return True
    ck = _col_key(col)
    lot_keys = {
        "lot", "lotno", "로트번호", "로트번호", "batch", "airbag번호", "에어백번호", "serial", "시리얼",
    }
    if ck in lot_keys:
        return True
    return "lot" in ck or "로트" in str(col) or "배치" in str(col)


def list_raw_boundary_column_candidates(df: pd.DataFrame) -> list[str]:
    """Raw data 컬럼 중 subgroup 분리 조건 후보."""
    skip_exact = {
        "value", "usl", "lsl", "target", "subgroup_id", "original_index",
        "pp", "ppk", "cp", "cpk", "sampling_strategy", "sampling_boundary",
        "sampling_block", "sampling_date", "seq_start_index",
    }
    out: list[str] = []
    for col in df.columns:
        name = str(col).strip()
        if not name or name in skip_exact:
            continue
        if name.startswith("_") or name.startswith("sampling_"):
            continue
        if name.lower().startswith("unnamed"):
            continue
        out.append(name)
    return out


def resolve_auto_boundary_columns(df: pd.DataFrame) -> list[str]:
    """자동 모드 — 실제 DataFrame 컬럼명 목록."""
    from src.spc.mixed_distribution_stratification import resolve_stratification_columns

    logical_keys = resolve_auto_subgroup_boundary_keys(df)
    available = resolve_stratification_columns(df)
    cols: list[str] = []
    seen: set[str] = set()
    for key in logical_keys:
        col = available.get(key)
        if col and col in df.columns and col not in seen:
            cols.append(col)
            seen.add(col)
    if not cols:
        for fallback in ("timestamp", "measure_date", "shift", "lot", "machine", "line"):
            if fallback in df.columns and fallback not in seen:
                cols.append(fallback)
                seen.add(fallback)
    return cols


def _series_column(df: pd.DataFrame, name: str, default: str = "ALL") -> pd.Series:
    """단일 컬럼 Series 반환 (동일 이름 중복 컬럼이면 병합)."""
    if name not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype=object)
    data = df[name]
    if isinstance(data, pd.DataFrame):
        data = data.bfill(axis=1).iloc[:, 0]
    return data.astype(str)


def _process_block_series(df: pd.DataFrame) -> pd.Series:
    """공정 블록 키 — process 우선, 없으면 process_name."""
    if "process" in df.columns:
        return _series_column(df, "process")
    if "process_name" in df.columns:
        return _series_column(df, "process_name")
    return pd.Series(["ALL"] * len(df), index=df.index, dtype=object)


class SampleSelector:
    """공정능력·관리도 분석을 위한 표본 선정."""

    def __init__(
        self,
        df: pd.DataFrame,
        value_col: str = "value",
        *,
        subgroup_boundary_keys: list[str] | None = None,
        subgroup_boundary_columns: list[str] | None = None,
    ):
        self.df = df.copy()
        if "original_index" not in self.df.columns:
            self.df["original_index"] = self.df.index
        self.value_col = value_col
        self.subgroup_boundary_columns = list(subgroup_boundary_columns or [])
        self._raw_boundary_map: dict[str, str] = {}
        if self.subgroup_boundary_columns:
            self.subgroup_boundary_keys: list[str] = []
        elif subgroup_boundary_keys is None:
            self.subgroup_boundary_keys = resolve_auto_subgroup_boundary_keys(self.df)
        else:
            self.subgroup_boundary_keys = subgroup_boundary_keys

    @property
    def _manual_sampling_boundary(self) -> bool:
        """사용자 지정 컬럼 — 채취·subgroup 구성에만 적용 (원본 필터 아님)."""
        return bool(self.subgroup_boundary_columns)

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
        strategy = self._sampling_strategy_label()
        use_date_pick = self._use_date_balanced_pick()
        candidates = self._collect_candidates(blocks, subgroup_size)
        sequence_candidates = self._collect_sequence_candidates(
            self._order_for_sequence(), subgroup_size
        )

        if not candidates:
            logger.warning(
                "설정된 블록(%s)으로 subgroup 후보 없음 → 순번 기준 연속 랜덤 채취로 대체합니다.",
                format_subgroup_boundary_labels(
                    self.subgroup_boundary_keys,
                    columns=self.subgroup_boundary_columns or None,
                ),
            )
            strategy = "sequence_random"
            candidates = sequence_candidates
        elif len(candidates) < n_subgroups:
            logger.warning(
                "블록 후보 %d개 < 목표 %d subgroup — 가능한 군만 사용 (군 내 연속 유지)",
                len(candidates),
                n_subgroups,
            )

        if not candidates:
            raise ValueError(
                f"채취 가능한 subgroup 없음: 데이터 {len(df)}행, 군당 {subgroup_size}개 연속 구간 필요"
            )

        rng = np.random.default_rng(random_state)
        if strategy == "sequence_random" or not use_date_pick:
            picked = self._random_pick_sequence(candidates, n_subgroups, rng)
        else:
            picked = self._random_pick_by_date(candidates, n_subgroups, rng)

        from src.spc.sample_ordering import candidate_sort_key, sort_sample_dataframe

        picked = sorted(picked, key=candidate_sort_key)

        boundary_tag = self._boundary_tag()
        selected_parts: list[pd.DataFrame] = []
        for subgroup_id, cand in enumerate(picked, start=1):
            chunk = cand["chunk"].copy()
            chunk["subgroup_id"] = subgroup_id
            chunk["sampling_block"] = cand["block_key"]
            chunk["sampling_date"] = cand["date"]
            chunk["sampling_strategy"] = strategy
            chunk["sampling_boundary"] = boundary_tag
            if "seq_start" in cand:
                chunk["seq_start_index"] = cand["seq_start"]
            selected_parts.append(chunk)

        result = pd.concat(selected_parts, ignore_index=True)
        n_got = int(result["subgroup_id"].nunique())
        dates_used = sorted(result["sampling_date"].unique())

        size_check = result.groupby("subgroup_id", sort=True).size()
        bad_sizes = size_check[size_check != subgroup_size]
        if not bad_sizes.empty:
            detail = ", ".join(f"id={int(k)}:{int(v)}개" for k, v in bad_sizes.items())
            raise ValueError(
                f"subgroup 크기 불일치: 군당 {subgroup_size}개 필요 — {detail}"
            )

        if n_got < n_subgroups:
            logger.warning("목표 %d subgroup → %d subgroup (후보 %d개)", n_subgroups, n_got, len(candidates))

        drop_cols = [
            c
            for c in ("_sort_time", "_block_date", "_block_shift", "_block_lot", "_seq_ord")
            if c in result.columns
        ]
        result = result.drop(columns=drop_cols)

        result = sort_sample_dataframe(result)

        if strategy == "sequence_random":
            logger.info(
                "순번 랜덤 subgroup: %d군 × n=%d (후보 %d개, 순번 구간 랜덤)",
                n_got, subgroup_size, len(candidates),
            )
        else:
            pick_mode = "일자 분산" if use_date_pick else "블록 내 연속"
            logger.info(
                "subgroup 채취 (%s): %d군 × n=%d, 기준=%s, 사용 일자 %d개 %s",
                pick_mode,
                n_got, subgroup_size,
                format_subgroup_boundary_labels(
                    self.subgroup_boundary_keys,
                    columns=self.subgroup_boundary_columns or None,
                ),
                len(dates_used),
                dates_used[:5] if len(dates_used) > 5 else dates_used,
            )
        return result.reset_index(drop=True), subgroup_size

    def _boundary_tag(self) -> str:
        if self.subgroup_boundary_columns:
            return "+".join(
                boundary_column_display_name(c) for c in self.subgroup_boundary_columns
            )
        return "+".join(self.subgroup_boundary_keys)

    def _use_date_balanced_pick(self) -> bool:
        """날짜형 컬럼을 분리 기준으로 선택했을 때만 일자별 골고루 채취."""
        if "date" in self.subgroup_boundary_keys:
            return True
        return any(
            is_date_like_boundary_column(col, self.df)
            for col in self.subgroup_boundary_columns
        )

    def _sampling_strategy_label(self) -> str:
        tag = self._boundary_tag()
        if not tag:
            return "boundary_block"
        return f"boundary_block:{tag}"

    @staticmethod
    def _internal_boundary_col(raw: str) -> str:
        digest = hashlib.md5(str(raw).encode("utf-8")).hexdigest()[:10]
        return f"_bnd_{digest}"

    def _build_raw_boundary_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        self._raw_boundary_map = {}
        for raw in self.subgroup_boundary_columns:
            if is_virtual_boundary_column(raw):
                block = virtual_boundary_block_column(raw)
                if block and block in df.columns:
                    self._raw_boundary_map[raw] = block
                continue
            if raw not in df.columns:
                continue
            internal = self._internal_boundary_col(raw)
            if is_date_like_boundary_column(raw, df):
                ts = pd.to_datetime(df[raw], errors="coerce")
                df[internal] = ts.dt.date.astype(str)
                df.loc[ts.isna(), internal] = "UNKNOWN"
            else:
                df[internal] = _series_column(df, raw)
            self._raw_boundary_map[raw] = internal
        return df

    def _lot_boundary_active(self) -> bool:
        if "lot" in self.subgroup_boundary_keys:
            return True
        return any(is_lot_like_boundary_column(c, self.df) for c in self.subgroup_boundary_columns)

    def _lot_boundary_series_col(self, chunk: pd.DataFrame) -> str | None:
        if "lot" in self.subgroup_boundary_keys and "_block_lot" in chunk.columns:
            return "_block_lot"
        for raw in self.subgroup_boundary_columns:
            if is_lot_like_boundary_column(raw, self.df):
                internal = self._raw_boundary_map.get(raw)
                if internal and internal in chunk.columns:
                    return internal
                if raw in chunk.columns:
                    return raw
        if "lot" in chunk.columns:
            return "lot"
        return None

    def _collect_candidates(
        self,
        blocks: list[tuple[str, pd.DataFrame]],
        subgroup_size: int,
    ) -> list[dict]:
        """블록별 슬라이딩 연속 윈도우(군 내 n개 연속) → 후보 subgroup 목록."""
        candidates: list[dict] = []
        for block_key, block_df in blocks:
            block_df = block_df.sort_values("_sort_time").reset_index(drop=True)
            n_rows = len(block_df)
            if n_rows < subgroup_size:
                continue
            block_date = str(block_df["_block_date"].iloc[0])
            for start in range(0, n_rows - subgroup_size + 1):
                chunk = block_df.iloc[start : start + subgroup_size]
                if self._chunk_violates_lot_boundary(chunk):
                    continue
                candidates.append({
                    "date": block_date,
                    "block_key": str(block_key),
                    "chunk": chunk,
                    "seq_start": start,
                })
        return candidates

    def _order_for_sequence(self) -> pd.DataFrame:
        """순번 채취용 정렬: 측정일시 있으면 시간순, 없으면 파일 읽기 순서."""
        from src.spc.sample_ordering import resolve_sort_timestamp_series

        df = self.df.copy()
        ts = resolve_sort_timestamp_series(df)
        if ts.notna().any():
            df["_sort_time"] = ts
            return df.sort_values("_sort_time", na_position="last").reset_index(drop=True)
        return df.reset_index(drop=True)

    def _collect_sequence_candidates(
        self,
        df: pd.DataFrame,
        subgroup_size: int,
    ) -> list[dict]:
        """전체 데이터 순번(시간·읽기 순서)상 연속 subgroup_size개 슬라이딩 윈도우 후보."""
        ordered = df.reset_index(drop=True)
        n_rows = len(ordered)
        if n_rows < subgroup_size:
            return []

        candidates: list[dict] = []
        for start in range(0, n_rows - subgroup_size + 1):
            chunk = ordered.iloc[start : start + subgroup_size]
            if self._chunk_violates_lot_boundary(chunk):
                continue
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
        from src.spc.sample_ordering import resolve_sort_timestamp_series

        df = self.df.copy()
        df["_sort_time"] = resolve_sort_timestamp_series(df)

        df["_block_lot"] = _series_column(df, "lot")
        df["_block_line"] = _series_column(df, "line")
        df["_block_machine"] = _series_column(df, "machine")
        df["_block_process"] = _process_block_series(df)
        if "characteristic" in df.columns:
            df["_block_characteristic"] = _series_column(df, "characteristic")
        df["_block_date"] = df["_sort_time"].dt.date.astype(str)
        df.loc[df["_sort_time"].isna(), "_block_date"] = "UNKNOWN"

        if VIRTUAL_BOUNDARY_SHIFT in self.subgroup_boundary_columns:
            df["_block_shift"] = df["_sort_time"].apply(self._infer_shift)
        elif "shift" in df.columns:
            df["_block_shift"] = _series_column(df, "shift")
        else:
            df["_block_shift"] = df["_sort_time"].apply(self._infer_shift)

        df = self._build_raw_boundary_columns(df)
        return df.sort_values(self._prepare_sort_columns(df))

    def _prepare_sort_columns(self, df: pd.DataFrame) -> list[str]:
        """선택한 분리 기준 → 시간순."""
        cols: list[str] = []
        if self.subgroup_boundary_columns:
            for raw in self.subgroup_boundary_columns:
                internal = self._raw_boundary_map.get(raw)
                if internal and internal in df.columns and internal not in cols:
                    cols.append(internal)
        else:
            for key in self.subgroup_boundary_keys:
                block_col = BLOCK_COLUMN_MAP.get(key)
                if block_col and block_col in df.columns and block_col not in cols:
                    cols.append(block_col)
            lot_active = self._lot_boundary_active()
            if not lot_active and "_block_lot" in df.columns:
                cols.append("_block_lot")
        if "_sort_time" in df.columns:
            cols.append("_sort_time")
        return cols or ["_sort_time"]

    def _sampling_block_keys(self, df: pd.DataFrame) -> list[str]:
        """채취 블록 키 — 직접 지정 시 선택 컬럼만, 자동 시 기본 공정·일자·교대."""
        if self._manual_sampling_boundary:
            cols: list[str] = []
            for raw in self.subgroup_boundary_columns:
                if is_lot_like_boundary_column(raw, self.df):
                    continue
                internal = self._raw_boundary_map.get(raw)
                if internal and internal in df.columns:
                    cols.append(internal)
            return cols
        if self.subgroup_boundary_keys:
            out: list[str] = []
            for key in self.subgroup_boundary_keys:
                if key == "lot":
                    continue
                block_col = BLOCK_COLUMN_MAP.get(key)
                if block_col and block_col in df.columns:
                    out.append(block_col)
            if out:
                return out
        return SampleSelector._default_block_keys(df)

    @staticmethod
    def _infer_shift(ts: pd.Timestamp) -> str:
        if pd.isna(ts):
            return "UNKNOWN"
        h = ts.hour
        if DAY_SHIFT_START_HOUR <= h < DAY_SHIFT_END_HOUR:
            return "주간"
        return "야간"

    def _chunk_violates_lot_boundary(self, chunk: pd.DataFrame) -> bool:
        """LOT 경계: LOT당 1행 데이터는 허용, LOT당 n행 이상이면 subgroup 내 LOT 혼합 금지."""
        if not self._lot_boundary_active():
            return False
        lot_col = self._lot_boundary_series_col(chunk)
        if not lot_col:
            return False
        lots = chunk[lot_col].astype(str)
        if lots.nunique() <= 1:
            return False
        lot_src = "lot" if "lot" in self.df.columns else lot_col
        lot_counts = self.df[lot_src].value_counts() if lot_src in self.df.columns else pd.Series(dtype=int)
        if lot_counts.empty:
            return False
        return int(lot_counts.max()) >= 2

    def _block_group_columns(self, df: pd.DataFrame) -> list[str]:
        """블록 분할용 컬럼 (LOT은 subgroup 내 혼합 규칙으로 별도 처리)."""
        if self._manual_sampling_boundary:
            cols: list[str] = []
            for raw in self.subgroup_boundary_columns:
                if is_lot_like_boundary_column(raw, self.df):
                    continue
                internal = self._raw_boundary_map.get(raw)
                if internal and internal in df.columns:
                    cols.append(internal)
            return cols
        cols: list[str] = []
        for key in self.subgroup_boundary_keys:
            if key == "lot":
                continue
            block_col = BLOCK_COLUMN_MAP.get(key)
            if block_col and block_col in df.columns:
                cols.append(block_col)
        if not cols:
            cols = SampleSelector._default_block_keys(df)
        return cols

    @staticmethod
    def _default_block_keys(df: pd.DataFrame) -> list[str]:
        keys: list[str] = []
        for col in ("_block_line", "_block_machine", "_block_process", "_block_date", "_block_shift"):
            if col in df.columns:
                keys.append(col)
        return keys or ["_block_date", "_block_shift"]

    def _split_blocks(self, df: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
        """설정된 조건(일자·교대·공정 등)별 블록 — 블록 순서는 시간순."""
        from src.spc.sample_ordering import resolve_sort_timestamp_series

        key_cols = self._block_group_columns(df)
        if not key_cols:
            if self._manual_sampling_boundary:
                logger.warning(
                    "직접 지정 분리 조건이 매핑되지 않아 전체를 단일 블록으로 채취합니다."
                )
            return [("ALL", df)]
        blocks: list[tuple[str, pd.DataFrame]] = []
        for key, grp in df.groupby(key_cols, sort=False):
            parts = key if isinstance(key, tuple) else (key,)
            label = "|".join(str(p) for p in parts)
            blocks.append((label, grp))

        def _block_start(item: tuple[str, pd.DataFrame]) -> tuple[int, float]:
            ts = resolve_sort_timestamp_series(item[1])
            if ts.notna().any():
                return (0, float(pd.Timestamp(ts.min()).value))
            return (1, 0.0)

        blocks.sort(key=_block_start)
        return blocks

    def select_full_population(
        self,
        subgroup_size: int = 5,
        *,
        for_xbar: bool = True,
    ) -> tuple[pd.DataFrame, int | None]:
        """필터된 전체 데이터를 시간순으로 사용 (샘플링 없음)."""
        from src.spc.sample_ordering import sort_sample_dataframe

        df = self.df.dropna(subset=[self.value_col]).copy()
        if df.empty:
            raise ValueError("전수 데이터: 유효한 측정값이 없습니다.")
        df = sort_sample_dataframe(df)
        df["sampling_strategy"] = "full_population"

        if for_xbar:
            sorted_df = sort_sample_dataframe(df)
            work_sel = SampleSelector(
                sorted_df,
                self.value_col,
                subgroup_boundary_keys=self.subgroup_boundary_keys,
                subgroup_boundary_columns=self.subgroup_boundary_columns,
            )
            prepared = work_sel._prepare_for_sampling()
            blocks = work_sel._split_blocks(prepared)
            parts: list[pd.DataFrame] = []
            sg_id = 1
            for _, block_df in blocks:
                block_df = block_df.sort_values("_sort_time").reset_index(drop=True)
                n_rows = len(block_df)
                for start in range(0, n_rows - subgroup_size + 1, subgroup_size):
                    chunk = block_df.iloc[start : start + subgroup_size]
                    if len(chunk) < subgroup_size:
                        break
                    if work_sel._chunk_violates_lot_boundary(chunk):
                        continue
                    out = chunk.copy()
                    out["subgroup_id"] = sg_id
                    sg_id += 1
                    parts.append(out)
            if len(parts) < 2:
                raise ValueError(
                    f"전수 X-bar 분석: subgroup 구성 조건 하에 최소 2군 필요 (현재 {len(parts)}군)"
                )
            result = pd.concat(parts, ignore_index=True)
            drop_cols = [
                c for c in (
                    "_sort_time", "_block_date", "_block_shift", "_block_lot",
                    "_block_line", "_block_machine", "_block_process", "_block_characteristic",
                )
                if c in result.columns
            ]
            result = result.drop(columns=drop_cols)
            from src.spc.sample_ordering import sort_sample_dataframe

            return sort_sample_dataframe(result.reset_index(drop=True)), subgroup_size

        if len(df) < 2:
            raise ValueError(f"전수 I-MR 분석: 최소 2건 필요 (현재 {len(df)}건)")
        return df.reset_index(drop=True), None

    @staticmethod
    def to_subgroup_matrix(df: pd.DataFrame, subgroup_size: int, value_col: str = "value") -> np.ndarray:
        from src.spc.sample_ordering import resolve_sort_timestamp_series

        if "subgroup_id" in df.columns:
            groups: list[np.ndarray] = []
            for sg_id, g in df.sort_values("subgroup_id").groupby("subgroup_id", sort=True):
                ts = resolve_sort_timestamp_series(g)
                if ts.notna().any():
                    order = ts.argsort(kind="mergesort")
                    vals = g.iloc[order][value_col].to_numpy(dtype=float)
                else:
                    vals = g[value_col].to_numpy(dtype=float)
                if len(vals) != subgroup_size:
                    raise ValueError(
                        f"subgroup_id={sg_id} 행 수 {len(vals)}개 — 군당 {subgroup_size}개 연속이 필요합니다."
                    )
                groups.append(vals)
            if not groups:
                raise ValueError("subgroup_id가 있으나 유효한 subgroup이 없습니다.")
            return np.stack(groups, axis=0)
        values = df[value_col].to_numpy(dtype=float)
        n_groups = len(values) // subgroup_size
        if n_groups == 0:
            raise ValueError(
                f"subgroup 행렬 생성 불가: 데이터 {len(values)}행, 군당 {subgroup_size}개 필요"
            )
        if len(values) % subgroup_size != 0:
            logger.warning(
                "subgroup_id 없음 — 잔여 %d행 제외 후 %d군 × n=%d 사용",
                len(values) % subgroup_size,
                n_groups,
                subgroup_size,
            )
        return values[: n_groups * subgroup_size].reshape(n_groups, subgroup_size)

    @staticmethod
    def effective_sample_size(subgroup_size: int, n_subgroups: int) -> int:
        """X-bar: 군당 × 군 수. I-MR은 n_subgroups(대표점 수)만 사용."""
        return max(1, subgroup_size) * max(1, n_subgroups)

    def select_rational_individuals(
        self,
        n_points: int,
        unit: ImrSamplingUnit = "auto",
        cycle_stride: int = 5,
    ) -> pd.DataFrame:
        """
        I-MR용: 동일 공정 조건 구간에서 대표 1점씩 선정 후 시간순 n_points개.
        """
        n_points = max(2, n_points)
        cycle_stride = max(1, cycle_stride)
        prepared = self._prepare_for_sampling()
        resolved = self._resolve_imr_unit(prepared, unit, n_points)
        prepared = self._assign_block_hours(prepared, resolved)
        reps = self._build_imr_representatives(prepared, resolved, cycle_stride)

        if reps.empty:
            logger.warning("I-MR 대표점 없음 → 시간순 연속 채취로 대체")
            return self.select_consecutive_individuals(n_points)

        reps = reps.sort_values("_sort_time", na_position="last").reset_index(drop=True)
        if len(reps) > n_points:
            reps = reps.iloc[-n_points:].copy()

        reps["sampling_strategy"] = f"imr_rational_{resolved}"
        reps["imr_sampling_unit"] = resolved
        if "_block_hour" in reps.columns:
            reps["sampling_hour_bucket"] = reps["_block_hour"]
        if len(reps) < n_points:
            logger.warning(
                "I-MR 목표 %d점 → 대표점 %d점 (%s)",
                n_points, len(reps), IMR_UNIT_LABELS.get(resolved, resolved),
            )
        else:
            logger.info(
                "I-MR 대표 채취: %d점 (%s)",
                len(reps), IMR_UNIT_LABELS.get(resolved, resolved),
            )
        drop_cols = [
            c
            for c in (
                "_sort_time", "_block_date", "_block_shift", "_block_lot",
                "_block_hour", "_hour_inferred", "_seq_ord", "_rep_group",
            )
            if c in reps.columns
        ]
        return reps.drop(columns=drop_cols).reset_index(drop=True)

    def _assign_block_hours(self, df: pd.DataFrame, unit: ImrSamplingUnit) -> pd.DataFrame:
        """I-MR 1시간 단위: timestamp 기준 또는 시간 없을 때 순번 추정."""
        out = df.copy()
        if unit != "hour":
            if "_sort_time" in out.columns:
                out["_block_hour"] = out["_sort_time"].dt.floor("h").astype(str)
                out.loc[out["_sort_time"].isna(), "_block_hour"] = "UNKNOWN"
            else:
                out["_block_hour"] = "UNKNOWN"
            return out

        if self._has_intraday_time(out):
            out["_block_hour"] = out["_sort_time"].dt.floor("h").astype(str)
            out.loc[out["_sort_time"].isna(), "_block_hour"] = "UNKNOWN"
            out["_hour_inferred"] = False
            return out

        logger.warning(
            "측정일시에 시간 정보가 없어, 동일 조건(라인·설비·공정) 내 순번으로 1시간 구간을 추정합니다."
        )
        parts: list[pd.DataFrame] = []
        for _, block in out.groupby(self._sampling_block_keys(out), sort=False):
            block = block.sort_values("_sort_time", na_position="last").reset_index(drop=True)
            n = len(block)
            if n == 0:
                continue
            work_hours = 12
            rows_per_hour = max(1, (n + work_hours - 1) // work_hours)
            block = block.copy()
            block["_block_hour"] = [
                f"{block['_block_date'].iloc[0]}|slot{idx // rows_per_hour:02d}"
                for idx in range(n)
            ]
            block["_hour_inferred"] = True
            parts.append(block)
        return pd.concat(parts, ignore_index=True) if parts else out

    @staticmethod
    def _has_intraday_time(df: pd.DataFrame) -> bool:
        valid = df["_sort_time"].dropna() if "_sort_time" in df.columns else pd.Series(dtype="datetime64[ns]")
        if len(valid) < 2:
            return False
        if valid.dt.floor("h").nunique() >= 2:
            return True
        by_day = valid.dt.date
        for day in pd.unique(by_day)[:30]:
            day_ts = valid[by_day == day]
            if len(day_ts) >= 2 and (day_ts.max() - day_ts.min()).total_seconds() >= 3600:
                return True
            if day_ts.dt.hour.nunique() > 1 or day_ts.dt.minute.nunique() > 1:
                return True
        return False

    def _resolve_imr_unit(
        self,
        df: pd.DataFrame,
        unit: ImrSamplingUnit,
        n_points: int,
    ) -> ImrSamplingUnit:
        if unit != "auto":
            return unit
        n = len(df)
        if n == 0:
            return "cycle"
        lots = df["_block_lot"].nunique()
        if "lot" in self.df.columns and lots >= 2:
            avg_per_lot = n / lots
            if avg_per_lot >= 1.2 and lots >= min(n_points // 2, 3):
                return "lot"
        if "shift" in self.df.columns or df["_block_shift"].nunique() >= 2:
            per_shift = df.groupby(["_block_date", "_block_shift", "_block_lot"], dropna=False).ngroups
            if per_shift >= min(n_points // 2, 3):
                return "shift"
        if df["_sort_time"].notna().sum() >= n_points and self._has_intraday_time(df):
            tmp_hour = df["_sort_time"].dt.floor("h")
            per_hour = df.assign(_tmp_hour=tmp_hour).groupby(
                self._imr_process_block_keys(df) + ["_tmp_hour"], dropna=False
            ).ngroups
            if per_hour >= min(n_points // 2, 5):
                return "hour"
        return "cycle"

    @staticmethod
    def _imr_process_block_keys(df: pd.DataFrame) -> list[str]:
        """I-MR 공정 조건 키 (LOT·검사항목 제외 — 라인·설비·공정·일·교대)."""
        keys: list[str] = []
        for col in ("_block_line", "_block_machine", "_block_process", "_block_date", "_block_shift"):
            if col in df.columns:
                keys.append(col)
        if not keys:
            keys = ["_block_date", "_block_shift"]
        return keys

    def _imr_group_cols(self, df: pd.DataFrame, unit: ImrSamplingUnit) -> list[str]:
        if unit == "lot":
            return ["_block_lot"]
        base = self._imr_process_block_keys(df)
        if unit == "hour":
            return base + ["_block_hour"]
        if unit == "shift":
            return base
        return base

    def _build_imr_representatives(
        self,
        df: pd.DataFrame,
        unit: ImrSamplingUnit,
        cycle_stride: int,
    ) -> pd.DataFrame:
        if unit == "cycle":
            parts: list[pd.DataFrame] = []
            for _, block in df.groupby(self._imr_process_block_keys(df), sort=False):
                block = block.sort_values("_sort_time", na_position="last")
                picked = block.iloc[::cycle_stride]
                if not picked.empty:
                    parts.append(picked)
            return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

        group_cols = self._imr_group_cols(df, unit)

        picked_rows: list[pd.DataFrame] = []
        for _, grp in df.groupby(group_cols, sort=False):
            picked_rows.append(self._pick_representative_row(grp))
        if not picked_rows:
            return pd.DataFrame()
        return pd.concat(picked_rows, ignore_index=True)

    @staticmethod
    def _pick_representative_row(group: pd.DataFrame) -> pd.DataFrame:
        """동일 조건 구간의 대표 1점 (시간 중앙값 위치)."""
        if len(group) == 1:
            return group.copy()
        g = group.sort_values("_sort_time", na_position="last")
        return g.iloc[[len(g) // 2]].copy()

    def select_consecutive_individuals(self, n_points: int) -> pd.DataFrame:
        """I-MR용: 시간(또는 원본) 순 **연속** n_points개 — 데이터 끝(최신) 구간 우선."""
        n_points = max(1, n_points)
        ordered = self._order_for_sequence()
        n = len(ordered)
        if n == 0:
            raise ValueError("채취할 데이터가 없습니다.")
        size = min(n_points, n)
        chunk = ordered.iloc[-size:].copy()
        chunk["sampling_strategy"] = "consecutive_individual"
        if size < n_points:
            logger.warning("I-MR 목표 %d점 → 연속 %d점 (데이터 부족)", n_points, size)
        else:
            logger.info("I-MR 연속 채취: %d점 (시간순 최신 구간)", size)
        drop_cols = [
            c
            for c in ("_sort_time", "_block_date", "_block_shift", "_block_lot", "_seq_ord")
            if c in chunk.columns
        ]
        return chunk.drop(columns=drop_cols).reset_index(drop=True)

    @staticmethod
    def flatten_subgroups_to_individuals(df: pd.DataFrame) -> pd.DataFrame:
        """subgroup 채취 결과를 I-MR용 개별값 시계열로 펼침 (시간·군 순 정렬)."""
        out = df.copy()
        sort_keys: list[str] = []
        if "subgroup_id" in out.columns:
            sort_keys.append("subgroup_id")
        if "timestamp" in out.columns:
            sort_keys.append("timestamp")
        if sort_keys:
            out = out.sort_values(sort_keys, kind="mergesort").reset_index(drop=True)
        drop_cols = [
            c
            for c in ("_sort_time", "_block_date", "_block_shift", "_block_lot", "_seq_ord")
            if c in out.columns
        ]
        return out.drop(columns=drop_cols)

    @staticmethod
    def recommend_chart_type(n_total: int, subgroup_size: int = 5) -> Literal["xbar_r", "imr"]:
        if n_total >= subgroup_size * 2 and subgroup_size >= 2:
            return "xbar_r"
        return "imr"
