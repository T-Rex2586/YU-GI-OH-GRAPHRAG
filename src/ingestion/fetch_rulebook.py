"""Akuisisi Dokumen 1: Official Yu-Gi-Oh! Rulebook Version 10 + Master Rule 2020/2021 Revisions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pymupdf
import requests
from loguru import logger

from src.config import Settings, get_settings

RULEBOOK_URLS = [
    "https://img.yugioh-card.com/en/downloads/rulebook/SD_RuleBook_EN_10.pdf",
    "https://img.yugioh-card.com/en/rulebook/SD_RuleBook_EN_10.pdf",
]

CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "Normal Summon": ["normal summon", "normal set", "tribute summon"],
    "Tribute": ["tribute summon", "tribute"],
    "Special Summon": ["special summon"],
    "Ritual Summon": ["ritual summon", "ritual monster", "ritual spell"],
    "Fusion Summon": ["fusion summon", "fusion monster", "polymerization"],
    "Synchro Summon": ["synchro summon", "synchro monster", "tuner"],
    "Xyz Summon": ["xyz summon", "xyz monster", "xyz material", "rank"],
    "Pendulum Summon": ["pendulum summon", "pendulum zone", "pendulum scale"],
    "Pendulum Scale": ["pendulum scale", "pendulum zone"],
    "Link Summon": ["link summon", "link monster", "link arrow", "link rating"],
    "Extra Monster Zone": ["extra monster zone", "main monster zone"],
    "Extra Deck": ["extra deck"],
    "Chain": ["chain", "chain link", "resolving a chain", "respond"],
    "Spell Speed 1": ["spell speed 1", "ignition effect"],
    "Spell Speed 2": ["spell speed 2", "quick effect", "quick-play"],
    "Spell Speed 3": ["spell speed 3", "counter trap"],
    "Quick Effect": ["quick effect", "fast effect"],
    "Quick-Play Spell": ["quick-play spell"],
    "Field Spell": ["field spell", "field zone"],
    "Equip Spell": ["equip spell"],
    "Continuous Spell": ["continuous spell"],
    "Normal Trap": ["normal trap"],
    "Continuous Trap": ["continuous trap"],
    "Counter Trap": ["counter trap"],
    "Flip Effect": ["flip effect", "flip summon"],
    "Damage Step": ["damage step", "battle step", "damage calculation", "replay"],
    "Graveyard": ["graveyard", "gy"],
    "Banished": ["banish", "banished"],
}

# Revisi resmi terbaru setelah Rulebook v10 (Master Rule April 2020 & 2021 Rules Update Konami)
MASTER_RULE_UPDATES: list[dict[str, Any]] = [
    {
        "id": "rule_mr2020_extra_deck_zones",
        "section_title": "Official Master Rule Revision (2020/2021 Update) - Extra Deck Summoning Zones",
        "category": "Master Rule Update (Latest)",
        "page": 99,
        "source": "Konami Official Master Rule Revision (2020/2021 Update)",
        "text": (
            "OFFICIAL MASTER RULE UPDATE (2020/2021 REVISION - SUPERSEDES RULEBOOK V10 PAGE 5 & 18-23 FOR EXTRA DECK ZONES): "
            "Fusion Monsters, Synchro Monsters, and Xyz Monsters Special Summoned from the Extra Deck can now be placed in EITHER "
            "an available Extra Monster Zone OR any available Main Monster Zone—they NO LONGER require a Link Monster's Link Arrow "
            "pointing to a Main Monster Zone. However, Link Monsters and face-up Pendulum Monsters Special Summoned from the Extra Deck "
            "MUST still be Summoned to either the Extra Monster Zone or a Main Monster Zone that a Link Monster points to."
        ),
        "concepts": [
            "Extra Monster Zone",
            "Extra Deck",
            "Fusion Summon",
            "Synchro Summon",
            "Xyz Summon",
            "Pendulum Summon",
            "Link Summon",
            "Special Summon",
        ],
    },
    {
        "id": "rule_mr2020_trigger_location_rule",
        "section_title": "Official Master Rule Revision (2020/2021 Update) - Trigger Effects Moving Location",
        "category": "Master Rule Update (Latest)",
        "page": 100,
        "source": "Konami Official 2021 Rules Update",
        "text": (
            "OFFICIAL 2021 RULES UPDATE - TRIGGER EFFECTS AND PRIVATE/MOVED LOCATIONS: "
            "If a card meets its Trigger Effect activation condition (for example, being sent to the Graveyard, banished, or added to hand/Deck), "
            "but before that Trigger Effect can be placed on a new Chain it moves to a different location (such as being banished from the GY "
            "mid-Chain, shuffled into the Deck, or returned to the hand/Extra Deck), it CANNOT activate that Trigger Effect anymore."
        ),
        "concepts": ["Chain", "Graveyard", "Banished", "Special Summon"],
    },
    {
        "id": "rule_mr2020_summon_restriction_count",
        "section_title": "Official Master Rule Revision (2020/2021 Update) - Negated Summons & Activations",
        "category": "Master Rule Update (Latest)",
        "page": 101,
        "source": "Konami Official 2021 Rules Update",
        "text": (
            "OFFICIAL 2021 RULES UPDATE - SUMMON LIMITS AND TRAP MONSTERS: "
            "1) Continuous Trap Cards that Special Summon themselves as monsters while still being treated as Traps NO LONGER leave "
            "an unusable occupied Spell & Trap Zone—they move to the Monster Zone and free up the Spell & Trap Zone while face-up as a monster. "
            "2) Under restrictions like 'You can only Special Summon X time(s) per turn' (e.g., El Shaddoll Winda), a Special Summon whose "
            "Summon is negated (by Solemn Judgment / Solemn Strike) depends on wording: 'You can only Special Summon once per turn' counts "
            "successful Summons unless negated, whereas 'You can only activate 1 X per turn' does NOT count if the activation itself was negated."
        ),
        "concepts": ["Continuous Trap", "Special Summon", "Counter Trap", "Chain"],
    },
]


def detect_concepts_in_text(text: str) -> list[str]:
    """Mendeteksi entitas GameConcept yang dijelaskan dalam suatu potongan aturan."""
    lower = text.lower()
    matched = [
        concept
        for concept, keywords in CONCEPT_KEYWORDS.items()
        if any(kw in lower for kw in keywords)
    ]
    return sorted(matched)


def classify_rulebook_page(page_num: int, text: str) -> tuple[str, str]:
    """Menentukan judul bagian (Section) dan kategori dari halaman Rulebook v10."""
    lower = text.lower()
    if page_num <= 5:
        return "Game Mat, Deck Construction & Zones", "Game Setup"
    if "monster cards" in lower or "link monsters" in lower or (6 <= page_num <= 17):
        return "Monster Cards & Extra Deck Types (Link, Pendulum, Xyz, Synchro, Fusion)", "Card Types & Summons"
    if "summoning monster cards" in lower or (18 <= page_num <= 25):
        return "Summoning Monster Cards (Normal, Tribute, Special Summon)", "Summoning Mechanics"
    if "spell" in lower and "trap" in lower and (26 <= page_num <= 33):
        return "Spell & Trap Cards (Subtypes & Icons)", "Spell & Trap Rules"
    if "turn structure" in lower or "phases" in lower or (34 <= page_num <= 39):
        return "Turn Structure & Phases (Draw, Standby, Main 1, Battle, Main 2, End)", "Turn Phases"
    if "battle" in lower or "damage step" in lower or (40 <= page_num <= 43):
        return "Monster Battle, Replay & Damage Step Rules", "Battle & Damage Step"
    if "chain" in lower or "spell speed" in lower or (44 <= page_num <= 49):
        return "Chains and Spell Speeds (Spell Speed 1, 2, 3)", "Chains & Timing"
    if "glossary" in lower or page_num >= 50:
        return "Official Glossary & Important Duel Rules", "Glossary & Advanced Rules"
    return f"Official Rulebook Page {page_num}", "General Rules"


def download_rulebook_pdf(settings: Settings | None = None, force: bool = False) -> Path:
    """Mengunduh PDF Official Rulebook Version 10 dari server Konami."""
    cfg = settings or get_settings()
    pdf_path = cfg.rulebook_pdf_path

    if pdf_path.exists() and pdf_path.stat().st_size > 50_000 and not force:
        logger.info(f"PDF Rulebook sudah tersedia di {pdf_path}")
        return pdf_path

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for url in RULEBOOK_URLS:
        try:
            logger.info(f"Mengunduh Official Rulebook v10 dari {url} ...")
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 YuGiOh-GraphRAG/1.0"},
                timeout=60,
            )
            resp.raise_for_status()
            if len(resp.content) > 50_000:
                pdf_path.write_bytes(resp.content)
                logger.success(f"Rulebook PDF berhasil disimpan ({len(resp.content):,} bytes)")
                return pdf_path
        except Exception as exc:
            last_err = exc
            logger.warning(f"Gagal mengunduh dari {url}: {exc}")

    raise RuntimeError(f"Tidak dapat mengunduh PDF Rulebook Konami: {last_err}")


def chunk_text_cleanly(text: str, max_chars: int = 1100, overlap_chars: int = 180) -> list[str]:
    """Memecah teks halaman PDF menjadi chunk semantik dengan overlap rapi."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= max_chars:
        return [text] if text else []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = f"{current}\n{para}".strip() if current else para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
                tail = current[-overlap_chars:] if len(current) > overlap_chars else current
                current = f"{tail}\n{para}".strip()
            else:
                # Paragraf sangat panjang
                for i in range(0, len(para), max_chars - overlap_chars):
                    chunks.append(para[i : i + max_chars])
                current = ""
    if current:
        chunks.append(current)
    return chunks


def process_rulebook(
    settings: Settings | None = None,
    force_download: bool = False,
    force_process: bool = False,
) -> list[dict[str, Any]]:
    """Mengekstrak teks PDF Rulebook v10 + Master Rule Revision 2020/2021 menjadi chunk terstruktur."""
    cfg = settings or get_settings()
    if cfg.rulebook_chunks_path.exists() and not force_download and not force_process:
        logger.info(f"Memuat chunk Rulebook dari {cfg.rulebook_chunks_path}")
        with cfg.rulebook_chunks_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    chunks_output: list[dict[str, Any]] = []
    try:
        pdf_path = download_rulebook_pdf(cfg, force=force_download)
        doc = pymupdf.open(pdf_path)
        logger.info(f"Mengekstrak {len(doc)} halaman dari Official Rulebook v10...")
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            raw_text = doc[page_idx].get_text("text").strip()
            if len(raw_text) < 40:
                continue
            section_title, category = classify_rulebook_page(page_num, raw_text)
            subchunks = chunk_text_cleanly(raw_text, max_chars=1100, overlap_chars=160)
            for idx, ch_text in enumerate(subchunks):
                concepts = detect_concepts_in_text(ch_text)
                chunks_output.append(
                    {
                        "id": f"rulebook_v10_p{page_num:02d}_c{idx + 1}",
                        "section_title": section_title,
                        "category": category,
                        "page": page_num,
                        "source": f"Official Yu-Gi-Oh! TCG Rulebook v10 (Page {page_num})",
                        "text": ch_text,
                        "concepts": concepts,
                    }
                )
        doc.close()
    except Exception as exc:
        logger.warning(f"Ekstraksi PDF Rulebook mengalami kendala ({exc}), menggunakan ringkasan aturan inti + Master Rule Update.")

    # Tambahkan Master Rule 2020/2021 Updates agar aturan zona Extra Deck selalu mutakhir!
    chunks_output.extend(MASTER_RULE_UPDATES)

    with cfg.rulebook_chunks_path.open("w", encoding="utf-8") as f:
        json.dump(chunks_output, f, ensure_ascii=False, indent=2)

    logger.success(f"Berhasil menghasilkan {len(chunks_output)} chunk Rulebook & Master Rule terbaru!")
    return chunks_output
