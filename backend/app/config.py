from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = "Control AI"
    host: str = "127.0.0.1"
    port: int = 8765
    db_path: Path = Path("backend/data/control_ai.db")
    logs_path: Path = Path("backend/data/runtime.log")
    cache_path: Path = Path("backend/data/cache.json")
    model_path: Path = Path("models/llm.gguf")
    max_history_turns: int = 16
    request_timeout_s: int = 15
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_schema: str = "public"

    @property
    def data_dir(self) -> Path:
        return self.db_path.parent

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


def load_settings() -> Settings:
    port = int(os.getenv("CONTROL_AI_PORT", "8765"))
    host = os.getenv("CONTROL_AI_HOST", "127.0.0.1")
    data_root = Path(os.getenv("CONTROL_AI_DATA_DIR", "backend/data"))
    model_path = Path(os.getenv("CONTROL_AI_MODEL_PATH", "models/llm.gguf"))
    supabase_url = os.getenv("CONTROL_AI_SUPABASE_URL") or os.getenv("SUPABASE_URL")
    supabase_service_role_key = (
        os.getenv("CONTROL_AI_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    supabase_schema = os.getenv("CONTROL_AI_SUPABASE_SCHEMA") or os.getenv("SUPABASE_SCHEMA") or "public"
    return Settings(
        host=host,
        port=port,
        db_path=data_root / "control_ai.db",
        logs_path=data_root / "runtime.log",
        cache_path=data_root / "cache.json",
        model_path=model_path,
        supabase_url=supabase_url,
        supabase_service_role_key=supabase_service_role_key,
        supabase_schema=supabase_schema,
    )
