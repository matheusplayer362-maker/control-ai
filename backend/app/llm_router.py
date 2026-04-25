from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

LOGGER = logging.getLogger(__name__)


class LLMRouter:
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self._backend = None
        self.mode = "heuristic"
        self._try_load_local_model()

    def _try_load_local_model(self) -> None:
        if not self.model_path.exists():
            LOGGER.warning("Local model not found at %s. Using heuristic mode.", self.model_path)
            return
        try:
            from llama_cpp import Llama  # type: ignore

            self._backend = Llama(model_path=str(self.model_path), n_ctx=4096, n_threads=6)
            self.mode = "llama_cpp"
            LOGGER.info("Local model loaded: %s", self.model_path)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to load local model: %s", exc)
            self._backend = None
            self.mode = "heuristic"

    @property
    def model_ready(self) -> bool:
        return self._backend is not None

    def generate(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        facts: list[str],
        sources: list[dict],
        category_name: str,
        confidence_label: str,
        response_style: str = "normal",
    ) -> str:
        if self._backend is None:
            return self._heuristic_response(user_message, facts, sources, category_name, confidence_label, response_style)

        prompt_parts = [
            f"<system>{system_prompt}</system>",
            f"<category>{category_name}</category>",
            f"<confidence>{confidence_label}</confidence>",
            f"<style>{self._style_instruction(response_style)}</style>",
            "<history>",
        ]
        for item in history[-8:]:
            role = item["role"]
            content = item["content"]
            prompt_parts.append(f"<{role}>{content}</{role}>")
        prompt_parts.append("</history>")
        prompt_parts.append("<sources>")
        for item in sources[:4]:
            prompt_parts.append(
                f"- {item.get('title', '')} | {item.get('url', '')} | {item.get('excerpt', '')[:280]}"
            )
        prompt_parts.append("</sources>")
        prompt_parts.append("<facts>")
        for fact in facts[:6]:
            prompt_parts.append(f"- {fact}")
        prompt_parts.append("</facts>")
        prompt_parts.append(f"<user>{user_message}</user>")
        prompt_parts.append("<assistant>")
        prompt = "\n".join(prompt_parts)

        out = self._backend(prompt, max_tokens=420, temperature=0.2, stop=["</assistant>"])
        return out["choices"][0]["text"].strip()

    def _heuristic_response(
        self,
        user_message: str,
        facts: list[str],
        sources: list[dict],
        category_name: str,
        confidence_label: str,
        response_style: str,
    ) -> str:
        lowered = user_message.lower().strip()
        if lowered in {"oi", "ola", "olá", "bom dia", "boa tarde", "boa noite"}:
            return "Oi. Me diga o que voce quer saber que eu respondo direto ao ponto."

        if not sources:
            return (
                f"Nao encontrei informacao suficiente nas fontes permitidas para a categoria {category_name}.\n\n"
                "Resposta: nao consigo confirmar isso com seguranca sem evidencias adequadas.\n\n"
                "Confiabilidade: Baixo\n"
                "Fontes utilizadas: nenhuma"
            )

        return self._build_structured_answer(user_message, facts, sources, confidence_label, response_style)

    def _build_structured_answer(
        self,
        user_message: str,
        facts: list[str],
        sources: list[dict],
        confidence_label: str,
        response_style: str,
    ) -> str:
        cleaned_facts = self._normalize_facts(facts)
        answer_line = self._build_direct_answer(user_message, cleaned_facts, response_style)
        detail_lines = self._build_development(cleaned_facts, response_style)
        summary_line = self._build_conclusion(cleaned_facts, response_style)
        source_line = self._format_sources(sources)

        parts = [answer_line]
        if detail_lines:
            parts.append("")
            parts.extend(detail_lines)
        if summary_line:
            parts.append("")
            parts.append(summary_line)
        parts.append("")
        parts.append(f"Confiabilidade: {confidence_label}")
        parts.append(f"Fontes utilizadas: {source_line}")
        return "\n".join(parts)

    def _build_direct_answer(self, user_message: str, facts: list[str], response_style: str) -> str:
        focus = self._extract_focus(user_message)
        if not facts:
            return f"Resposta direta: nao encontrei evidencias suficientes para responder {focus} com seguranca."

        if response_style == "short":
            return self._ensure_period(facts[0])

        if self._looks_like_code_request(user_message):
            code_block = self._find_code_snippet(facts)
            if code_block:
                return f"Resposta direta: use este exemplo base.\n\n```text\n{code_block}\n```"

        return f"Resposta direta: {self._ensure_period(facts[0])}"

    def _build_development(self, facts: list[str], response_style: str) -> list[str]:
        if response_style == "short":
            return []
        useful = facts[1:4]
        if not useful:
            return []
        lines = ["Detalhes importantes:"]
        lines.extend([f"- {self._clean_fact_text(fact)}" for fact in useful])
        return lines

    def _build_conclusion(self, facts: list[str], response_style: str) -> str:
        if response_style == "short":
            return ""
        if len(facts) >= 2:
            return f"Resumo: {self._ensure_period(facts[0])}"
        if facts:
            return f"Resumo: {self._ensure_period(facts[0])}"
        return ""

    def _format_sources(self, sources: list[dict]) -> str:
        domains: list[str] = []
        seen: set[str] = set()
        for item in sources[:4]:
            domain = urlparse(str(item.get("url", ""))).netloc.lower()
            if not domain or domain in seen:
                continue
            seen.add(domain)
            domains.append(domain)
        return ", ".join(domains) if domains else "nenhuma"

    def _normalize_facts(self, facts: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for fact in facts:
            cleaned = self._clean_fact_text(fact)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
        return result[:6]

    def _find_code_snippet(self, facts: list[str]) -> str:
        for fact in facts:
            if any(token in fact for token in ["local ", "function ", "const ", "let ", "var ", "=>", "{", "}"]):
                return fact
        return ""

    def _looks_like_code_request(self, user_message: str) -> bool:
        lowered = user_message.lower()
        return any(token in lowered for token in ["script", "codigo", "código", "exemplo", "roblox", "lua", "javascript", "python"])

    def _extract_focus(self, message: str) -> str:
        collapsed = re.sub(r"\s+", " ", message).strip()
        return collapsed or "o tema pedido"

    def _clean_fact_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip(" .-")
        if not cleaned:
            return ""
        return cleaned[0].upper() + cleaned[1:]

    def _ensure_period(self, text: str) -> str:
        cleaned = self._clean_fact_text(text)
        if not cleaned:
            return ""
        if cleaned.endswith((".", "!", "?")):
            return cleaned
        return cleaned + "."

    def _style_instruction(self, response_style: str) -> str:
        if response_style == "short":
            return "Responda em no maximo duas frases curtas."
        if response_style == "technical":
            return "Responda de forma tecnica e objetiva."
        if response_style == "simple":
            return "Responda de forma simples e clara."
        return "Responda de forma clara, organizada e direta."
