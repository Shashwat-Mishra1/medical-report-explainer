"""Small SQLite store for reports. Uses only Python's built-in sqlite3.

Privacy choices: the raw OCR text (which can contain a name or phone number) is NOT stored,
and reports older than RETENTION_HOURS are deleted together with their uploaded file.
"""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "medreport.db"
RETENTION_HOURS = 24

_JSON_FIELDS = ("tests", "explanation", "chat")
_COLUMNS = {"file_path", "status", "extraction_method", "tests", "explanation", "chat"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS reports (
                       id TEXT PRIMARY KEY,
                       created_at REAL NOT NULL,
                       file_path TEXT,
                       status TEXT,
                       extraction_method TEXT,
                       tests TEXT NOT NULL DEFAULT '[]',
                       explanation TEXT,
                       chat TEXT NOT NULL DEFAULT '[]'
                   )"""
            )
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    for field in _JSON_FIELDS:
        data[field] = json.loads(data[field]) if data[field] is not None else None
    return data


def create_report(report_id: str, file_path: str, status: str, extraction_method: str, tests: list) -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO reports (id, created_at, file_path, status, extraction_method, tests) VALUES (?,?,?,?,?,?)",
                (report_id, time.time(), file_path, status, extraction_method, json.dumps(tests)),
            )
    finally:
        conn.close()


def get_report(report_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row else None


def update_report(report_id: str, **fields) -> None:
    unknown = set(fields) - _COLUMNS
    if unknown:
        raise ValueError(f"Unknown report fields: {unknown}")
    if not fields:
        return
    values = [json.dumps(v) if k in _JSON_FIELDS else v for k, v in fields.items()]
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn = _connect()
    try:
        with conn:
            conn.execute(f"UPDATE reports SET {assignments} WHERE id = ?", (*values, report_id))
    finally:
        conn.close()


def delete_report(report_id: str) -> str | None:
    """Deletes the row and returns the file path that should be removed (or None if not found)."""
    conn = _connect()
    try:
        row = conn.execute("SELECT file_path FROM reports WHERE id = ?", (report_id,)).fetchone()
        if row is None:
            return None
        with conn:
            conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        return row["file_path"] or ""
    finally:
        conn.close()


def purge_old(hours: float = RETENTION_HOURS) -> int:
    """Deletes reports older than `hours` and their uploaded files. Returns how many were removed."""
    cutoff = time.time() - hours * 3600
    conn = _connect()
    try:
        rows = conn.execute("SELECT id, file_path FROM reports WHERE created_at < ?", (cutoff,)).fetchall()
        with conn:
            conn.execute("DELETE FROM reports WHERE created_at < ?", (cutoff,))
    finally:
        conn.close()
    for row in rows:
        if row["file_path"]:
            Path(row["file_path"]).unlink(missing_ok=True)
    return len(rows)