from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Dict, Optional


_lock = Lock()
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "refinement_store.db"
TTL_SECONDS = 60 * 60 * 24


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS refinements (
            request_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            result_json TEXT,
            error_text TEXT,
            updated_at REAL NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _cleanup_expired(connection: sqlite3.Connection) -> None:
    cutoff = time.time() - TTL_SECONDS
    connection.execute("DELETE FROM refinements WHERE updated_at < ?", (cutoff,))
    connection.commit()


def set_pending(request_id: str) -> None:
    with _lock:
        connection = _conn()
        try:
            _cleanup_expired(connection)
            connection.execute(
                """
                INSERT INTO refinements(request_id, status, result_json, error_text, updated_at)
                VALUES (?, ?, NULL, NULL, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    status=excluded.status,
                    result_json=NULL,
                    error_text=NULL,
                    updated_at=excluded.updated_at
                """,
                (request_id, "pending", time.time()),
            )
            connection.commit()
        finally:
            connection.close()


def set_result(request_id: str, result: Dict) -> None:
    with _lock:
        connection = _conn()
        try:
            _cleanup_expired(connection)
            connection.execute(
                """
                INSERT INTO refinements(request_id, status, result_json, error_text, updated_at)
                VALUES (?, ?, ?, NULL, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    status=excluded.status,
                    result_json=excluded.result_json,
                    error_text=NULL,
                    updated_at=excluded.updated_at
                """,
                (request_id, "complete", json.dumps(result, ensure_ascii=False), time.time()),
            )
            connection.commit()
        finally:
            connection.close()


def set_error(request_id: str, error_message: str) -> None:
    with _lock:
        connection = _conn()
        try:
            _cleanup_expired(connection)
            connection.execute(
                """
                INSERT INTO refinements(request_id, status, result_json, error_text, updated_at)
                VALUES (?, ?, NULL, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    status=excluded.status,
                    result_json=NULL,
                    error_text=excluded.error_text,
                    updated_at=excluded.updated_at
                """,
                (request_id, "error", error_message, time.time()),
            )
            connection.commit()
        finally:
            connection.close()


def get_entry(request_id: str) -> Optional[Dict]:
    with _lock:
        connection = _conn()
        try:
            _cleanup_expired(connection)
            row = connection.execute(
                "SELECT status, result_json, error_text FROM refinements WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        finally:
            connection.close()

    if not row:
        return None

    status, result_json, error_text = row
    if status == "complete":
        return {"status": "complete", "result": json.loads(result_json or "{}")}
    if status == "error":
        return {"status": "error", "error": error_text or "Unknown error"}
    return {"status": "pending"}
