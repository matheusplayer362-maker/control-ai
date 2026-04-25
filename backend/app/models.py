from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    session_id: str = "default"


class SourceItem(BaseModel):
    url: str
    title: str
    reliability: float
    excerpt: str


class ChatResponse(BaseModel):
    answer: str
    confidence: float
    sources: list[SourceItem]
    mode: str
    timestamp: datetime


class HistoryMessage(BaseModel):
    role: str
    content: str
    created_at: datetime


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    status: str
    model_ready: bool
    scraper_ready: bool
    uptime_seconds: float
    counters: dict[str, Any]
