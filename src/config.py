"""Konfigurasi terpusat untuk aplikasi Yu-Gi-Oh! Hybrid GraphRAG."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EMBED_CACHE_DIR = DATA_DIR / "embeddings_cache"

for directory in (DATA_DIR, RAW_DIR, PROCESSED_DIR, EMBED_CACHE_DIR):
    directory.mkdir(parents=True, exist_ok=True)


@dataclass
class Settings:
    """Pengaturan koneksi Neo4j, Gemini API, dan lokasi dataset lokal."""

    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_llm_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_LLM_MODEL", "gemini-3.5-flash-lite")
    )
    embedding_provider: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "fastembed")
    )
    gemini_embedding_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    )
    fastembed_model: str = field(
        default_factory=lambda: os.getenv(
            "FASTEMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
    )
    embedding_dimension: int = field(
        default_factory=lambda: int(
            os.getenv(
                "EMBEDDING_DIMENSION",
                "384"
                if os.getenv("EMBEDDING_PROVIDER", "fastembed").lower() == "fastembed"
                and "base" not in os.getenv("FASTEMBED_MODEL", "all-MiniLM-L6-v2").lower()
                else "768",
            )
        )
    )

    neo4j_uri: str = field(
        default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687")
    )
    neo4j_username: str = field(
        default_factory=lambda: os.getenv("NEO4J_USERNAME", "neo4j")
    )
    neo4j_password: str = field(
        default_factory=lambda: os.getenv("NEO4J_PASSWORD", "yugioh_graphrag_2026")
    )
    neo4j_database: str = field(
        default_factory=lambda: os.getenv("NEO4J_DATABASE", "neo4j")
    )

    # Path file dataset
    cards_raw_path: Path = RAW_DIR / "ygoprodeck_cards_v7.json"
    banlist_processed_path: Path = PROCESSED_DIR / "banlist_entries.json"
    cards_processed_path: Path = PROCESSED_DIR / "cards_enriched.json"
    rulebook_pdf_path: Path = RAW_DIR / "SD_RuleBook_EN_10.pdf"
    rulebook_chunks_path: Path = PROCESSED_DIR / "rulebook_chunks.json"
    psct_rules_path: Path = PROCESSED_DIR / "psct_rules.json"
    rulings_raw_dir: Path = RAW_DIR / "rulings"
    rulings_processed_path: Path = PROCESSED_DIR / "card_rulings.json"


def get_settings() -> Settings:
    """Ambil instance konfigurasi terbaru dari environment variables."""
    return Settings()
