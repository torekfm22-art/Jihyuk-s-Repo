"""SQLite DB 관리."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from quality_mh.models import (
    CalcResult,
    FrequencyDB,
    QualitativeRecord,
    QuantitativeRecord,
    RuleMaster,
)
from quality_mh.rule_master import RuleMasterRegistry, build_rule_master

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "quality_mh.db"


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS rule_master (
            task_code TEXT PRIMARY KEY,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS freq_db (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_code TEXT NOT NULL,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS records (
            record_id TEXT PRIMARY KEY,
            record_type TEXT NOT NULL,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS calc_results (
            record_id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS history (
            history_id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_at TEXT NOT NULL,
            change_reason TEXT
        );
    """)
    conn.commit()

    if cur.execute("SELECT COUNT(*) FROM rule_master").fetchone()[0] == 0:
        for rule in build_rule_master():
            save_rule(rule, conn)
    conn.close()


def _dump(model: Any) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)


def _load(model_cls: type, data: str) -> Any:
    return model_cls.model_validate_json(data)


def save_rule(rule: RuleMaster, conn: sqlite3.Connection | None = None) -> None:
    close = conn is None
    conn = conn or get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO rule_master (task_code, data_json) VALUES (?, ?)",
        (rule.task_code, _dump(rule)),
    )
    conn.commit()
    if close:
        conn.close()


def load_rules(conn: sqlite3.Connection | None = None) -> list[RuleMaster]:
    close = conn is None
    conn = conn or get_connection()
    rows = conn.execute("SELECT data_json FROM rule_master").fetchall()
    if close:
        conn.close()
    if rows:
        return [_load(RuleMaster, r["data_json"]) for r in rows]
    return RuleMasterRegistry().get_all()


def save_freq_db(entry: FrequencyDB, conn: sqlite3.Connection | None = None) -> None:
    close = conn is None
    conn = conn or get_connection()
    conn.execute("DELETE FROM freq_db WHERE task_code = ?", (entry.task_code,))
    conn.execute(
        "INSERT INTO freq_db (task_code, data_json) VALUES (?, ?)",
        (entry.task_code, _dump(entry)),
    )
    conn.commit()
    if close:
        conn.close()


def load_freq_db(conn: sqlite3.Connection | None = None) -> list[FrequencyDB]:
    close = conn is None
    conn = conn or get_connection()
    rows = conn.execute("SELECT data_json FROM freq_db").fetchall()
    if close:
        conn.close()
    return [_load(FrequencyDB, r["data_json"]) for r in rows]


def get_freq_db_by_task_code(task_code: str, conn: sqlite3.Connection | None = None) -> FrequencyDB | None:
    close = conn is None
    conn = conn or get_connection()
    row = conn.execute(
        "SELECT data_json FROM freq_db WHERE task_code = ? LIMIT 1",
        (task_code,),
    ).fetchone()
    if close:
        conn.close()
    return _load(FrequencyDB, row["data_json"]) if row else None


def save_record(
    record: QuantitativeRecord | QualitativeRecord,
    record_type: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    close = conn is None
    conn = conn or get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO records (record_id, record_type, data_json) VALUES (?, ?, ?)",
        (record.record_id, record_type, _dump(record)),
    )
    conn.commit()
    if close:
        conn.close()


def load_quantitative_records(conn: sqlite3.Connection | None = None) -> list[QuantitativeRecord]:
    close = conn is None
    conn = conn or get_connection()
    rows = conn.execute(
        "SELECT data_json FROM records WHERE record_type = 'quantitative'"
    ).fetchall()
    if close:
        conn.close()
    return [_load(QuantitativeRecord, r["data_json"]) for r in rows]


def load_qualitative_records(conn: sqlite3.Connection | None = None) -> list[QualitativeRecord]:
    close = conn is None
    conn = conn or get_connection()
    rows = conn.execute(
        "SELECT data_json FROM records WHERE record_type = 'qualitative'"
    ).fetchall()
    if close:
        conn.close()
    return [_load(QualitativeRecord, r["data_json"]) for r in rows]


def save_calc_result(result: CalcResult, conn: sqlite3.Connection | None = None) -> None:
    close = conn is None
    conn = conn or get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO calc_results (record_id, data_json) VALUES (?, ?)",
        (result.record_id, _dump(result)),
    )
    conn.commit()
    if close:
        conn.close()


def load_calc_results(conn: sqlite3.Connection | None = None) -> list[CalcResult]:
    close = conn is None
    conn = conn or get_connection()
    rows = conn.execute("SELECT data_json FROM calc_results").fetchall()
    if close:
        conn.close()
    return [_load(CalcResult, r["data_json"]) for r in rows]


def delete_quantitative_records(
    record_ids: list[str],
    conn: sqlite3.Connection | None = None,
) -> int:
    """정량 레코드 및 연관 계산 결과 삭제. 삭제 건수 반환."""
    if not record_ids:
        return 0
    close = conn is None
    conn = conn or get_connection()
    placeholders = ",".join("?" * len(record_ids))
    conn.execute(
        f"DELETE FROM records WHERE record_type = 'quantitative' AND record_id IN ({placeholders})",
        record_ids,
    )
    conn.execute(
        f"DELETE FROM calc_results WHERE record_id IN ({placeholders})",
        record_ids,
    )
    conn.commit()
    if close:
        conn.close()
    return len(record_ids)


def add_history(
    record_id: str,
    field_name: str,
    old_value: str | None,
    new_value: str | None,
    change_reason: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    close = conn is None
    conn = conn or get_connection()
    history_id = f"H-{record_id}-{field_name}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    conn.execute(
        """INSERT INTO history
           (history_id, record_id, field_name, old_value, new_value, changed_at, change_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            history_id,
            record_id,
            field_name,
            old_value,
            new_value,
            datetime.now().isoformat(timespec="seconds"),
            change_reason,
        ),
    )
    conn.commit()
    if close:
        conn.close()


def load_history(conn: sqlite3.Connection | None = None) -> list[dict]:
    close = conn is None
    conn = conn or get_connection()
    rows = conn.execute(
        "SELECT * FROM history ORDER BY changed_at DESC"
    ).fetchall()
    if close:
        conn.close()
    return [dict(r) for r in rows]
