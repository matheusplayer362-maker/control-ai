from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse


@dataclass
class ValidatedResult:
    confidence: float
    confidence_label: str
    summary_points: list[str]


def validate_consistency(snippets: Iterable[dict]) -> ValidatedResult:
    snippets = list(snippets)
    if not snippets:
        return ValidatedResult(confidence=0.2, confidence_label="Baixo", summary_points=[])

    source_scores = [float(item.get("reliability", 0.65)) for item in snippets]
    unique_domains = {urlparse(str(item.get("url", ""))).netloc.lower() for item in snippets if item.get("url")}
    sentences: list[str] = []

    for item in snippets:
        title = str(item.get("title", "")).strip()
        excerpt = str(item.get("excerpt", "")).strip()
        if title:
            sentences.append(title)
        for raw in excerpt.split("."):
            piece = raw.strip()
            if len(piece) > 30:
                sentences.append(piece)

    normalized = [" ".join(text.lower().split()) for text in sentences if text]
    top = [item for item, _ in Counter(normalized).most_common(6)]
    reliability = sum(source_scores) / max(1, len(source_scores))
    source_bonus = min(0.2, len(unique_domains) * 0.07)
    confidence = round(min(0.99, reliability + source_bonus), 2)

    if len(unique_domains) >= 2 and reliability >= 0.85:
        label = "Alto"
    elif reliability >= 0.75:
        label = "Medio"
    else:
        label = "Baixo"

    summary_points = [text for text in top if text][:6]
    return ValidatedResult(confidence=confidence, confidence_label=label, summary_points=summary_points)
