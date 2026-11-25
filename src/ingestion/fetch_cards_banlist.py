"""Akuisisi Dokumen 2 (~14.000+ Kartu) & Dokumen 4 (Kartu Banned/Limited) dari YGOPRODeck API v7."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from src.config import Settings, get_settings
from src.ingestion.psct_analyzer import analyze_card_psct

YGOPRODECK_API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php?misc=yes"

BAN_STATUS_MAP = {
    "Banned": ("Forbidden", 0),
    "Forbidden": ("Forbidden", 0),
    "Limited": ("Limited", 1),
    "Semi-Limited": ("Semi-Limited", 2),
}


def download_raw_cards(settings: Settings | None = None, force: bool = False) -> list[dict[str, Any]]:
    """Mengunduh seluruh database ~14.000+ kartu beserta metadata Konami ID & Banlist."""
    cfg = settings or get_settings()
    raw_path: Path = cfg.cards_raw_path

    if raw_path.exists() and not force:
        logger.info(f"Memuat cache kartu mentah dari {raw_path}")
        with raw_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("data", payload)

    logger.info(f"Mengunduh ~14.000+ kartu dari {YGOPRODECK_API_URL} ...")
    resp = requests.get(
        YGOPRODECK_API_URL,
        headers={"User-Agent": "YuGiOh-GraphRAG-AcademicProject/1.0"},
        timeout=90,
    )
    resp.raise_for_status()
    payload = resp.json()

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    cards = payload.get("data", [])
    logger.success(f"Berhasil mengunduh {len(cards):,} kartu ke {raw_path}")
    return cards


def process_cards_and_banlist(
    settings: Settings | None = None,
    force_download: bool = False,
    force_process: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Memproses seluruh kartu dengan analisis PSCT serta mengekstrak daftar Banlist TCG/OCG/Goat."""
    cfg = settings or get_settings()

    if (
        cfg.cards_processed_path.exists()
        and cfg.banlist_processed_path.exists()
        and not force_download
        and not force_process
    ):
        logger.info("Memuat kartu terproses & banlist dari cache lokal...")
        with cfg.cards_processed_path.open("r", encoding="utf-8") as f:
            cards_enriched = json.load(f)
        with cfg.banlist_processed_path.open("r", encoding="utf-8") as f:
            banlist_entries = json.load(f)
        return cards_enriched, banlist_entries

    raw_cards = download_raw_cards(cfg, force=force_download)

    known_card_names = {c.get("name", "") for c in raw_cards if c.get("name")}
    known_archetypes = {c.get("archetype", "") for c in raw_cards if c.get("archetype")}

    cards_enriched: list[dict[str, Any]] = []
    banlist_entries: list[dict[str, Any]] = []

    logger.info(f"Menganalisis struktur PSCT & relasi untuk {len(raw_cards):,} kartu...")
    for card in raw_cards:
        misc_list = card.get("misc_info") or []
        misc = misc_list[0] if misc_list else {}
        images = card.get("card_images") or []
        image_url = images[0].get("image_url_small", "") if images else ""
        image_url_full = images[0].get("image_url", "") if images else ""

        ban_info = card.get("banlist_info") or {}
        ban_tcg_raw = ban_info.get("ban_tcg", "Unlimited")
        ban_ocg_raw = ban_info.get("ban_ocg", "Unlimited")
        ban_goat_raw = ban_info.get("ban_goat", "Unlimited")

        ban_tcg = BAN_STATUS_MAP.get(ban_tcg_raw, ("Unlimited", 3))[0]
        ban_ocg = BAN_STATUS_MAP.get(ban_ocg_raw, ("Unlimited", 3))[0]
        ban_goat = BAN_STATUS_MAP.get(ban_goat_raw, ("Unlimited", 3))[0]

        psct = analyze_card_psct(
            card,
            known_card_names=known_card_names,
            known_archetypes=known_archetypes,
        )

        konami_id = misc.get("konami_id")
        views = int(misc.get("views", 0) or 0)

        enriched = {
            "id": int(card["id"]),
            "konami_id": int(konami_id) if konami_id is not None else None,
            "name": card.get("name", ""),
            "type": card.get("type", ""),
            "frameType": card.get("frameType", ""),
            "humanReadableCardType": card.get("humanReadableCardType", card.get("type", "")),
            "desc": card.get("desc", ""),
            "atk": card.get("atk"),
            "def": card.get("def"),
            "level": card.get("level"),
            "scale": card.get("scale"),
            "linkval": card.get("linkval"),
            "linkmarkers": card.get("linkmarkers") or [],
            "race": card.get("race", ""),
            "attribute": card.get("attribute", ""),
            "archetype": card.get("archetype", ""),
            "tcg_date": misc.get("tcg_date", ""),
            "ocg_date": misc.get("ocg_date", ""),
            "md_rarity": misc.get("md_rarity", ""),
            "views": views,
            "image_url": image_url,
            "image_url_full": image_url_full,
            "ban_tcg": ban_tcg,
            "ban_ocg": ban_ocg,
            "ban_goat": ban_goat,
            "psct": psct,
        }
        cards_enriched.append(enriched)

        # Simpan entri Banlist untuk Dokumen 4 (TCG, OCG, Goat)
        for fmt_name, raw_status in (
            ("TCG", ban_tcg_raw),
            ("OCG", ban_ocg_raw),
            ("Goat", ban_goat_raw),
        ):
            if raw_status in BAN_STATUS_MAP:
                norm_status, max_copies = BAN_STATUS_MAP[raw_status]
                banlist_entries.append(
                    {
                        "card_id": int(card["id"]),
                        "konami_id": int(konami_id) if konami_id is not None else None,
                        "card_name": card.get("name", ""),
                        "card_type": card.get("type", ""),
                        "archetype": card.get("archetype", ""),
                        "format": fmt_name,
                        "status": norm_status,
                        "max_copies": max_copies,
                    }
                )

    with cfg.cards_processed_path.open("w", encoding="utf-8") as f:
        json.dump(cards_enriched, f, ensure_ascii=False)

    with cfg.banlist_processed_path.open("w", encoding="utf-8") as f:
        json.dump(banlist_entries, f, ensure_ascii=False, indent=2)

    logger.success(
        f"Selesai memproses {len(cards_enriched):,} kartu dan {len(banlist_entries):,} entri Banlist!"
    )
    return cards_enriched, banlist_entries
