from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from .recovery import with_retries

LOGGER = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class CategoryPolicy:
    name: str
    primary_domains: list[str]
    secondary_domains: list[str]
    tertiary_domains: list[str]


CATEGORY_POLICIES = {
    "general": CategoryPolicy(
        name="Conhecimento geral",
        primary_domains=["pt.wikipedia.org"],
        secondary_domains=[],
        tertiary_domains=[],
    ),
    "science": CategoryPolicy(
        name="Ciencia / medicina",
        primary_domains=["pubmed.ncbi.nlm.nih.gov"],
        secondary_domains=["scholar.google.com"],
        tertiary_domains=[],
    ),
    "programming": CategoryPolicy(
        name="Programacao / tecnologia",
        primary_domains=["developer.mozilla.org", "stackoverflow.com"],
        secondary_domains=["github.com"],
        tertiary_domains=[],
    ),
    "data": CategoryPolicy(
        name="Dados / estatisticas",
        primary_domains=["data.worldbank.org"],
        secondary_domains=["ibge.gov.br", "www.ibge.gov.br"],
        tertiary_domains=[],
    ),
    "news": CategoryPolicy(
        name="Noticias / atualidades",
        primary_domains=["reuters.com", "www.reuters.com"],
        secondary_domains=["bbc.com", "www.bbc.com"],
        tertiary_domains=[],
    ),
}


class ResilientScraper:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self._search_cache: dict[str, list[dict]] = {}

    @with_retries(retries=3, delay=0.9)
    def _get(self, url: str) -> str:
        response = requests.get(url, timeout=self.timeout, headers=HEADERS)
        response.raise_for_status()
        return response.text

    def _get_once(self, url: str) -> str:
        response = requests.get(url, timeout=max(6, min(self.timeout, 10)), headers=HEADERS)
        response.raise_for_status()
        return response.text

    def classify_query(self, query: str) -> str:
        lowered = query.lower()
        if any(token in lowered for token in ["noticia", "noticias", "hoje", "atualidade", "últimas", "ultimas", "guerra", "eleicao", "eleições"]):
            return "news"
        if any(token in lowered for token in ["ibge", "estatistica", "estatísticas", "estatistica", "percentual", "taxa", "populacao", "população", "pib", "desemprego"]):
            return "data"
        if any(token in lowered for token in ["medicina", "doenca", "doença", "saude", "saúde", "remedio", "remédio", "sintoma", "tratamento", "artigo cientifico", "pubmed", "creatina", "vacina", "whey", "suplemento", "colesterol"]):
            return "science"
        if any(token in lowered for token in ["codigo", "código", "script", "programar", "programacao", "programação", "api", "javascript", "typescript", "python", "html", "css", "roblox", "lua"]):
            return "programming"
        return "general"

    def get_policy(self, category: str) -> CategoryPolicy:
        return CATEGORY_POLICIES.get(category, CATEGORY_POLICIES["general"])

    def collect(self, query: str, category: str | None = None) -> list[dict]:
        chosen_category = category or self.classify_query(query)
        policy = self.get_policy(chosen_category)
        query_key = f"{chosen_category}:{query}"
        cached = self._search_cache.get(query_key)
        if cached is not None:
            return cached

        links = self._search_links(query, policy)
        results: list[dict] = []
        max_results = 4

        for item in links:
            if len(results) >= max_results:
                break
            url = item["url"]
            host = urlparse(url).netloc.lower()
            if not self._is_allowed_domain(host, policy):
                continue
            try:
                html = self._get_once(url)
                title = self._extract_page_title(html) or item["title"]
                excerpt = self._semantic_excerpt(html, query, chosen_category)
                if not excerpt:
                    continue
                results.append(
                    {
                        "url": url,
                        "title": title,
                        "excerpt": excerpt,
                        "reliability": self._source_score(host),
                        "category": chosen_category,
                        "domain": host,
                        "layer": item.get("layer", "primary"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Failed collecting from %s: %s", url, exc)

        self._search_cache[query_key] = results
        return results

    def _search_links(self, query: str, policy: CategoryPolicy) -> list[dict]:
        optimized_query = self._optimize_query(query)
        layers = [
            ("primary", policy.primary_domains),
            ("secondary", policy.secondary_domains),
            ("tertiary", policy.tertiary_domains),
        ]
        gathered: list[dict] = []
        seen: set[str] = set()

        for layer_name, domains in layers:
            for domain in domains:
                layer_query = f"{optimized_query} site:{domain}".strip()
                for link in self._search_engine_results(layer_query):
                    host = urlparse(link["url"]).netloc.lower()
                    if not self._domain_matches(host, domain):
                        continue
                    if link["url"] in seen:
                        continue
                    seen.add(link["url"])
                    gathered.append({**link, "layer": layer_name})
                if len(gathered) >= 6:
                    return self._rank_links(query, gathered, policy)

        return self._rank_links(query, gathered, policy)

    def _search_engine_results(self, query: str) -> list[dict]:
        engines = [
            f"https://search.brave.com/search?q={quote(query)}&source=web",
            f"https://duckduckgo.com/html/?q={quote(query)}",
            f"https://html.duckduckgo.com/html/?q={quote(query)}",
            f"https://www.bing.com/search?q={quote(query)}",
        ]

        for target in engines:
            try:
                html = self._get(target)
                links = self._extract_result_links(html)
                if links:
                    return links
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Search engine failed for %s: %s", target, exc)
        return []

    def _extract_result_links(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        links: list[dict] = []

        for a in soup.select("a.result__a, h3 a, article a, li.b_algo h2 a, .b_algo a"):
            href = a.get("href") or ""
            text = a.get_text(" ", strip=True)
            if href.startswith("http") and len(text) > 8:
                links.append({"url": href, "title": text})

        if not links:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                if href.startswith("http") and len(text) > 20:
                    links.append({"url": href, "title": text})

        unique: list[dict] = []
        seen: set[str] = set()
        for link in links:
            if link["url"] in seen:
                continue
            seen.add(link["url"])
            unique.append(link)
        return unique[:10]

    def _optimize_query(self, query: str) -> str:
        lowered = query.lower()
        lowered = re.sub(r"\b(me|manda|mande|responda|explique|por favor|pra mim|para mim)\b", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    def _rank_links(self, query: str, links: list[dict], policy: CategoryPolicy) -> list[dict]:
        ranked = sorted(links, key=lambda item: self._link_score(query, item, policy), reverse=True)
        return ranked[:8]

    def _link_score(self, query: str, item: dict, policy: CategoryPolicy) -> int:
        title = str(item.get("title", "")).lower()
        url = str(item.get("url", "")).lower()
        layer = str(item.get("layer", "tertiary"))
        tokens = {token for token in re.findall(r"\w+", query.lower()) if len(token) > 2}
        haystack = f"{title} {url}"
        overlap = sum(1 for token in tokens if token in haystack)

        score = overlap * 5
        if layer == "primary":
            score += 30
        elif layer == "secondary":
            score += 18
        elif layer == "tertiary":
            score += 8

        if any(self._domain_matches(urlparse(url).netloc.lower(), domain) for domain in policy.primary_domains):
            score += 20
        if "youtube.com" in url:
            score -= 20
        if "reddit.com" in url:
            score -= 12
        if "support.google.com" in url or "answers.microsoft.com" in url:
            score -= 20
        return score

    def _extract_page_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        if soup.title and soup.title.string:
            return re.sub(r"\s+", " ", soup.title.string).strip()
        return ""

    def _semantic_excerpt(self, html: str, query: str, category: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        candidates: list[str] = []
        query_tokens = {x.lower() for x in re.findall(r"\w+", query) if len(x) > 2}

        if category == "programming":
            for code in soup.select("pre code, code, pre"):
                text = re.sub(r"\s+", " ", code.get_text(" ", strip=True))
                if 12 < len(text) < 400:
                    candidates.append(text)
                if len(candidates) >= 4:
                    break

        for selector in ["article p", "main p", "section p", "p", "li"]:
            for node in soup.select(selector):
                text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
                if 40 < len(text) < 360:
                    candidates.append(text)
            if len(candidates) >= 10:
                break

        if not candidates:
            raw = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            return raw[:500]

        def score(line: str) -> tuple[int, int]:
            tokens = {x.lower() for x in re.findall(r"\w+", line)}
            overlap = len(tokens & query_tokens)
            relevance_bonus = 0
            lowered = line.lower()
            if category == "programming" and any(token in lowered for token in ["script", "code", "function", "local", "const", "var"]):
                relevance_bonus += 2
            if category == "science" and any(token in lowered for token in ["study", "trial", "risk", "treatment", "symptom"]):
                relevance_bonus += 2
            return overlap + relevance_bonus, min(len(line), 250)

        ranked = sorted(candidates, key=score, reverse=True)
        return " ".join(ranked[:2])[:650]

    def _is_allowed_domain(self, host: str, policy: CategoryPolicy) -> bool:
        allowed = policy.primary_domains + policy.secondary_domains + policy.tertiary_domains
        return any(self._domain_matches(host, domain) for domain in allowed)

    def _domain_matches(self, host: str, domain: str) -> bool:
        normalized_host = host.lower()
        normalized_domain = domain.lower()
        return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")

    @staticmethod
    def _source_score(host: str) -> float:
        if "pubmed.ncbi.nlm.nih.gov" in host:
            return 0.97
        if "scholar.google.com" in host:
            return 0.93
        if "developer.mozilla.org" in host:
            return 0.95
        if "stackoverflow.com" in host:
            return 0.83
        if "github.com" in host:
            return 0.82
        if "data.worldbank.org" in host:
            return 0.96
        if "ibge.gov.br" in host:
            return 0.97
        if "reuters.com" in host:
            return 0.96
        if "bbc.com" in host:
            return 0.93
        if "wikipedia.org" in host:
            return 0.8
        return 0.65
