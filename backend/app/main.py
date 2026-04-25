from __future__ import annotations

import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .actions import ActionRunner
from .config import load_settings
from .llm_router import LLMRouter
from .logging_utils import setup_logging
from .models import ChatRequest, ChatResponse, HealthResponse, SourceItem
from .monitor import Monitor
from .scraper import ResilientScraper
from .skills import SkillRegistry
from .storage import Storage
from .validator import validate_consistency

settings = load_settings()
setup_logging(settings.logs_path)
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="Control AI Local Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = Storage(
    settings.db_path,
    supabase_url=settings.supabase_url,
    supabase_service_role_key=settings.supabase_service_role_key,
    supabase_schema=settings.supabase_schema,
)
llm = LLMRouter(settings.model_path)
scraper = ResilientScraper(timeout=settings.request_timeout_s)
monitor = Monitor()
actions = ActionRunner()
skills = SkillRegistry(settings.data_dir.parent / "skills")
skills.reload()

SYSTEM_PROMPT = (
    "Voce eh um assistente local autonomo. Seja objetivo, util, proativo e seguro. "
    "Use apenas informacoes confirmadas nas fontes selecionadas e explique com clareza."
)


def is_smalltalk(user_text: str) -> bool:
    normalized = user_text.lower().strip(" !?.")
    return normalized in {
        "oi",
        "ola",
        "olá",
        "eai",
        "e aí",
        "bom dia",
        "boa tarde",
        "boa noite",
        "obrigado",
        "obrigada",
        "valeu",
    }


def detect_response_style(user_text: str) -> str:
    lowered = user_text.lower()
    if any(token in lowered for token in ["mais curta", "mais curto", "resuma", "seja breve", "bem curto", "direto ao ponto"]):
        return "short"
    if any(token in lowered for token in ["tecnica", "técnica", "tecnico", "técnico"]):
        return "technical"
    if any(token in lowered for token in ["mais simples", "simplificada", "simplificado"]):
        return "simple"
    return "normal"


def is_format_only_followup(user_text: str) -> bool:
    lowered = user_text.lower().strip()
    format_markers = ["responda", "resuma", "explique", "seja", "fale", "quero em", "me responda"]
    topic_markers = [
        "como ",
        "o que ",
        "quem ",
        "quando ",
        "onde ",
        "por que",
        "porque ",
        "qual ",
        "quais ",
        "receita",
        "script",
        "codigo",
        "código",
        "roblox",
        "lua",
        "python",
    ]
    has_format = any(marker in lowered for marker in format_markers)
    has_topic = any(marker in lowered for marker in topic_markers)
    return has_format and not has_topic


def is_contextual_followup(user_text: str) -> bool:
    lowered = user_text.lower()
    return any(
        token in lowered
        for token in [
            "nesse codigo",
            "nesse código",
            "esse codigo",
            "esse código",
            "nessa resposta",
            "nao me respondeu",
            "não me respondeu",
            "nao era isso",
            "não era isso",
            "isso",
            "isso ai",
            "isso aí",
            "nesse caso",
            "essa parte",
        ]
    )


def is_retry_followup(user_text: str) -> bool:
    lowered = user_text.lower()
    return any(
        token in lowered
        for token in [
            "nao me respondeu",
            "não me respondeu",
            "nao era isso",
            "não era isso",
            "nao respondeu",
            "não respondeu",
        ]
    )


def should_collect_sources(user_text: str) -> bool:
    if is_smalltalk(user_text):
        return False
    return len(user_text.strip()) >= 4


def find_previous_user_topic(history_items: list[dict]) -> str:
    for item in reversed(history_items):
        if item.get("role") != "user":
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if is_format_only_followup(content):
            continue
        return content
    return ""


def build_effective_query(user_text: str, history_items: list[dict]) -> str:
    previous_topic = find_previous_user_topic(history_items)
    if is_retry_followup(user_text) and previous_topic:
        return previous_topic
    if is_format_only_followup(user_text) and previous_topic:
        return previous_topic
    if is_contextual_followup(user_text) and previous_topic:
        return f"{previous_topic} {user_text}"
    return user_text


def build_facts_from_sources(sources_raw: list[dict], validated_points: list[str]) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()

    for item in sources_raw[:4]:
        title = " ".join(str(item.get("title", "")).split())
        excerpt = " ".join(str(item.get("excerpt", "")).split())
        for candidate in [title, excerpt]:
            if not candidate:
                continue
            normalized = candidate.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            facts.append(candidate)

    for point in validated_points:
        normalized = point.lower()
        if normalized not in seen:
            seen.add(normalized)
            facts.append(point)

    return facts[:8]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    counters = monitor.as_dict()
    return HealthResponse(
        status="ok",
        model_ready=llm.model_ready,
        scraper_ready=True,
        uptime_seconds=counters.get("uptime_seconds", 0.0),
        counters=counters,
    )


@app.get("/history/{session_id}")
def history(session_id: str):
    monitor.inc("history_requests")
    return storage.get_history(session_id, limit=100)


@app.delete("/history/{session_id}")
def clear_history(session_id: str):
    storage.clear_session(session_id)
    monitor.inc("history_clears")
    return {"ok": True}


@app.get("/skills")
def list_skills():
    return {"skills": skills.reload()}


@app.post("/skills")
def create_skill(payload: dict):
    name = str(payload.get("name", "")).strip()
    instruction = str(payload.get("instruction", "Skill generica"))
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    path = skills.create_skill(name, instruction)
    return {"ok": True, "path": str(path)}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    monitor.inc("chat_requests")
    session_id = req.session_id
    user_text = req.message.strip()
    history_items = storage.get_history(session_id, limit=settings.max_history_turns)
    response_style = detect_response_style(user_text)
    effective_query = build_effective_query(user_text, history_items)
    category = scraper.classify_query(effective_query)
    category_name = scraper.get_policy(category).name

    storage.save_message(session_id, "user", user_text)

    action_result = actions.maybe_execute(user_text)
    if action_result is not None:
        answer = action_result["message"]
        storage.save_message(session_id, "assistant", answer)
        return ChatResponse(
            answer=answer,
            confidence=0.99 if action_result.get("ok") else 0.4,
            sources=[],
            mode="action",
            timestamp=datetime.utcnow(),
        )

    skill_answer = None
    if user_text.startswith("/skill"):
        parts = user_text.split(maxsplit=2)
        if len(parts) >= 3:
            skill_answer = skills.run(parts[1], parts[2])

    sources_raw: list[dict] = []
    try:
        if should_collect_sources(effective_query):
            monitor.inc("scrape_runs")
            sources_raw = scraper.collect(effective_query, category=category)
    except Exception as exc:  # noqa: BLE001
        monitor.inc("scrape_errors")
        storage.log_incident("scraper", str(exc))
        LOGGER.exception("Scraper failed")

    validated = validate_consistency(sources_raw)
    facts = build_facts_from_sources(sources_raw, validated.summary_points)

    if skill_answer:
        answer = skill_answer
        mode = "skill"
        confidence = 0.88
    else:
        answer = llm.generate(
            SYSTEM_PROMPT,
            history_items,
            effective_query,
            facts,
            sources_raw,
            category_name,
            validated.confidence_label,
            response_style=response_style,
        )
        mode = f"{llm.mode}+{category}"
        if sources_raw:
            mode = f"{mode}+web"
        confidence = max(0.2, validated.confidence)

    storage.save_message(session_id, "assistant", answer)

    source_items = [
        SourceItem(
            url=item["url"],
            title=item["title"],
            reliability=item["reliability"],
            excerpt=item["excerpt"][:300],
        )
        for item in sources_raw[:4]
    ]

    return ChatResponse(
        answer=answer,
        confidence=round(confidence, 2),
        sources=source_items,
        mode=mode,
        timestamp=datetime.utcnow(),
    )
