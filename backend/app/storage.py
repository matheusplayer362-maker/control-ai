from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    return datetime.fromisoformat(normalized)


def _build_supabase_headers(api_key: str, schema: str) -> dict[str, str]:
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if schema and schema != "public":
        headers["Accept-Profile"] = schema
        headers["Content-Profile"] = schema
    return headers


class _SQLiteStorage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    confidence REAL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    component TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_message(self, session_id: str, role: str, content: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now),
            )

    def get_history(self, session_id: str, limit: int = 32) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        result = [dict(row) for row in reversed(rows)]
        for item in result:
            item["created_at"] = datetime.fromisoformat(str(item["created_at"]))
        return result

    def clear_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))

    def save_knowledge(self, topic: str, content: str, source: str, confidence: float) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO knowledge(topic, content, source, confidence, created_at) VALUES (?, ?, ?, ?, ?)",
                (topic, content, source, confidence, now),
            )

    def log_incident(self, component: str, message: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO incidents(component, message, created_at) VALUES (?, ?, ?)",
                (component, message, now),
            )


class _SupabaseStorage:
    def __init__(self, base_url: str, service_role_key: str, schema: str = "public") -> None:
        self.base_url = base_url.rstrip("/")
        self.schema = schema or "public"
        self.headers = _build_supabase_headers(service_role_key, self.schema)
        self.client = httpx.Client(timeout=20.0, headers=self.headers)

    def _table_url(self, table: str) -> str:
        return f"{self.base_url}/rest/v1/{table}"

    def _request(self, method: str, table: str, *, params: dict[str, str] | None = None, json: Any | None = None) -> httpx.Response:
        response = self.client.request(method, self._table_url(table), params=params, json=json)
        response.raise_for_status()
        return response

    def save_message(self, session_id: str, role: str, content: str) -> None:
        now = datetime.utcnow().isoformat()
        payload = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
        }
        self._request("POST", "messages", json=payload)

    def get_history(self, session_id: str, limit: int = 32) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "messages",
            params={
                "select": "role,content,created_at",
                "session_id": f"eq.{session_id}",
                "order": "id.asc",
                "limit": str(limit),
            },
        )
        rows = response.json()
        history: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["created_at"] = _parse_datetime(str(item["created_at"]))
            history.append(item)
        return history

    def clear_session(self, session_id: str) -> None:
        self._request(
            "DELETE",
            "messages",
            params={"session_id": f"eq.{session_id}"},
        )

    def save_knowledge(self, topic: str, content: str, source: str, confidence: float) -> None:
        now = datetime.utcnow().isoformat()
        payload = {
            "topic": topic,
            "content": content,
            "source": source,
            "confidence": confidence,
            "created_at": now,
        }
        self._request("POST", "knowledge", json=payload)

    def log_incident(self, component: str, message: str) -> None:
        now = datetime.utcnow().isoformat()
        payload = {
            "component": component,
            "message": message,
            "created_at": now,
        }
        self._request("POST", "incidents", json=payload)


class Storage:
    def __init__(
        self,
        db_path: Path,
        supabase_url: str | None = None,
        supabase_service_role_key: str | None = None,
        supabase_schema: str = "public",
    ) -> None:
        self._backend = self._build_backend(
            db_path=db_path,
            supabase_url=supabase_url,
            supabase_service_role_key=supabase_service_role_key,
            supabase_schema=supabase_schema,
        )

    @staticmethod
    def _resolve_supabase_value(value: str | None, env_names: list[str]) -> str | None:
        if value:
            return value
        for env_name in env_names:
            env_value = os.getenv(env_name)
            if env_value:
                return env_value
        return None

    def _build_backend(
        self,
        *,
        db_path: Path,
        supabase_url: str | None,
        supabase_service_role_key: str | None,
        supabase_schema: str,
    ) -> _SQLiteStorage | _SupabaseStorage:
        resolved_url = self._resolve_supabase_value(
            supabase_url,
            ["CONTROL_AI_SUPABASE_URL", "SUPABASE_URL"],
        )
        resolved_key = self._resolve_supabase_value(
            supabase_service_role_key,
            ["CONTROL_AI_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY"],
        )
        resolved_schema = os.getenv("CONTROL_AI_SUPABASE_SCHEMA") or os.getenv("SUPABASE_SCHEMA") or supabase_schema or "public"

        if resolved_url and resolved_key:
            return _SupabaseStorage(resolved_url, resolved_key, resolved_schema)
        return _SQLiteStorage(db_path)

    def save_message(self, session_id: str, role: str, content: str) -> None:
        self._backend.save_message(session_id, role, content)

    def get_history(self, session_id: str, limit: int = 32) -> list[dict[str, Any]]:
        return self._backend.get_history(session_id, limit=limit)

    def clear_session(self, session_id: str) -> None:
        self._backend.clear_session(session_id)

    def save_knowledge(self, topic: str, content: str, source: str, confidence: float) -> None:
        self._backend.save_knowledge(topic, content, source, confidence)

    def log_incident(self, component: str, message: str) -> None:
        self._backend.log_incident(component, message)
