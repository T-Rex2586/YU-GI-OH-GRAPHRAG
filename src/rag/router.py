"""Query Router & Entity Extractor dwibahasa (Indonesia/Inggris) untuk Yu-Gi-Oh! GraphRAG."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types
from loguru import logger

from src.config import Settings, get_settings

COMMON_CARD_ALIASES: dict[str, str] = {
    "ash blossom": "Ash Blossom & Joyous Spring",
    "maxx c": 'Maxx "C"',
    'maxx "c"': 'Maxx "C"',
    "imperm": "Infinite Impermanence",
    "infinite impermanence": "Infinite Impermanence",
    "called by": "Called by the Grave",
    "called by the grave": "Called by the Grave",
    "crossout": "Crossout Designator",
    "nibiru": "Nibiru, the Primal Being",
    "droplet": "Forbidden Droplet",
    "baronne": "Baronne de Fleur",
    "mirrorjade": "Mirrorjade the Iceblade Dragon",
    "zeus": "Divine Arsenal AA-ZEUS - Sky Thunder",
    "sp little knight": "S:P Little Knight",
    "s:p": "S:P Little Knight",
    "pot of greed": "Pot of Greed",
    "monster reborn": "Monster Reborn",
    "solemn judgment": "Solemn Judgment",
    "effect veiler": "Effect Veiler",
    "skill drain": "Skill Drain",
    "super poly": "Super Polymerization",
    "super polymerization": "Super Polymerization",
    "evenly matched": "Evenly Matched",
    "dark magician": "Dark Magician",
    "blue-eyes white dragon": "Blue-Eyes White Dragon",
    "fallen of albaz": "Fallen of Albaz",
}


@dataclass
class QueryPlan:
    """Rencana pencarian hasil analisis pertanyaan pengguna."""

    original_query: str
    english_search_query: str
    intents: list[str] = field(default_factory=list)
    card_names: list[str] = field(default_factory=list)
    archetypes: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    ban_status_filter: str | None = None


def heuristic_route_query(query: str) -> QueryPlan:
    """Fallback router berbasis aturan cepat (tanpa panggilan API tambahan)."""
    q_lower = query.lower()
    intents: list[str] = []

    if any(k in q_lower for k in ("ban", "banned", "forbidden", "limited", "semi-limited", "dilarang", "dibatasi", "tcg", "ocg", "goat")):
        intents.append("banlist")
    if any(k in q_lower for k in ("ruling", "psct", "chain", "negate", "target", "cost", "timing", "miss timing", "when", "then", "also", "and if you do", "resolusi", "efek", "interaksi")):
        intents.append("ruling_psct")
    if any(k in q_lower for k in ("cara main", "rulebook", "phase", "damage step", "summon", "synchro", "xyz", "link", "pendulum", "fusion", "ritual", "extra monster zone", "giliran", "spell speed")):
        intents.append("rulebook")
    if not intents or any(k in q_lower for k in ("kartu", "card", "atk", "def", "archetype", "level", "rank", "efek dari", "apa itu")):
        intents.append("card_info")

    cards: list[str] = []
    for quoted in re.findall(r'"([^"]{2,70})"', query):
        cards.append(quoted.strip())
    for alias, full_name in COMMON_CARD_ALIASES.items():
        if alias in q_lower and full_name not in cards:
            cards.append(full_name)

    formats: list[str] = []
    if "tcg" in q_lower:
        formats.append("TCG")
    if "ocg" in q_lower:
        formats.append("OCG")
    if "goat" in q_lower:
        formats.append("Goat")

    ban_status = None
    if any(w in q_lower for w in ("banned", "forbidden", "dibanned", "dilarang")):
        ban_status = "Forbidden"
    elif "semi-limited" in q_lower or "semi limited" in q_lower:
        ban_status = "Semi-Limited"
    elif "limited" in q_lower or "dibatasi 1" in q_lower:
        ban_status = "Limited"

    return QueryPlan(
        original_query=query,
        english_search_query=query,
        intents=intents,
        card_names=cards,
        archetypes=[],
        formats=formats,
        ban_status_filter=ban_status,
    )


class QueryRouter:
    """Menganalisis pertanyaan user (ID/EN) menjadi rencana pencarian Graph + Vector."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = (
            genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=types.HttpOptions(api_version="v1beta"),
            )
            if self.settings.gemini_api_key
            else None
        )

    def route(self, query: str, use_llm_router: bool = True) -> QueryPlan:
        base_plan = heuristic_route_query(query)
        if not use_llm_router or self._client is None:
            return base_plan

        system_instruction = (
            "You are a Yu-Gi-Oh! query analyzer for a Neo4j GraphRAG system. "
            "Given a user question (in Indonesian or English), output ONLY valid JSON with keys:\n"
            '- "english_search_query": concise English search query translating Indonesian game terms to official Yu-Gi-Oh! TCG English terminology\n'
            '- "intents": subset of ["rulebook", "card_info", "ruling_psct", "banlist"]\n'
            '- "card_names": list of exact official English Yu-Gi-Oh! card names mentioned or implied (resolve nicknames like "Ash" -> "Ash Blossom & Joyous Spring", "Imperm" -> "Infinite Impermanence", "Maxx C" -> "Maxx \\"C\\"")\n'
            '- "archetypes": list of official Yu-Gi-Oh! archetype names mentioned (e.g. "Tearlaments", "Branded", "Snake-Eye", "Blue-Eyes")\n'
            '- "formats": subset of ["TCG", "OCG", "Goat"] if specified\n'
            '- "ban_status_filter": one of "Forbidden", "Limited", "Semi-Limited", or null'
        )
        try:
            resp = self._client.models.generate_content(
                model=self.settings.gemini_llm_model,
                contents=query,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            data: dict[str, Any] = json.loads(resp.text or "{}")
            merged_cards = list(dict.fromkeys((data.get("card_names") or []) + base_plan.card_names))
            merged_intents = list(dict.fromkeys((data.get("intents") or []) + base_plan.intents))
            return QueryPlan(
                original_query=query,
                english_search_query=data.get("english_search_query") or query,
                intents=merged_intents or ["card_info"],
                card_names=merged_cards,
                archetypes=data.get("archetypes") or [],
                formats=data.get("formats") or base_plan.formats,
                ban_status_filter=data.get("ban_status_filter") or base_plan.ban_status_filter,
            )
        except Exception as exc:
            logger.warning(f"LLM Router fallback ke heuristik: {exc}")
            return base_plan
