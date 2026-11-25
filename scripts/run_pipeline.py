"""CLI Orkestrator Pipeline Yu-Gi-Oh! Hybrid GraphRAG (Fetch -> Parse -> Neo4j Ingest -> Gemini Embed).

Contoh penggunaan:
    # 1. Unduh & proses keempat sumber dokumen ke folder data/processed/
    python scripts/run_pipeline.py --fetch

    # 2. Ingesti seluruh ~14.000+ kartu, banlist, rulebook, PSCT, & rulings ke Neo4j
    python scripts/run_pipeline.py --ingest

    # 3. Hitung vektor embedding Gemini (default 600 kartu terpopuler + seluruh rulebook/PSCT/rulings)
    python scripts/run_pipeline.py --embed --max-card-embeddings 600

    # 4. Jalankan semuanya sekaligus (end-to-end)
    python scripts/run_pipeline.py --all --max-card-embeddings 600
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from src.config import get_settings
from src.graph.embedder import GeminiEmbedder
from src.graph.neo4j_client import Neo4jGraphClient
from src.graph.schema_and_ingest import (
    embed_and_index_nodes,
    ingest_cards_and_banlist_to_neo4j,
    ingest_psct_rules_to_neo4j,
    ingest_rulebook_to_neo4j,
    ingest_rulings_to_neo4j,
    setup_neo4j_schema,
)
from src.ingestion.fetch_cards_banlist import process_cards_and_banlist
from src.ingestion.fetch_psct_rulings import process_psct_and_rulings
from src.ingestion.fetch_rulebook import process_rulebook


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline Data & Knowledge Graph Yu-Gi-Oh! GraphRAG")
    parser.add_argument("--fetch", action="store_true", help="Unduh & proses keempat sumber dokumen Yu-Gi-Oh!")
    parser.add_argument("--ingest", action="store_true", help="Bangun skema & ingesti seluruh node/relasi ke Neo4j")
    parser.add_argument("--embed", action="store_true", help="Hitung vektor embedding Gemini & simpan ke Neo4j")
    parser.add_argument("--all", action="store_true", help="Jalankan fetch + ingest + embed sekaligus")
    parser.add_argument("--force", action="store_true", help="Paksa unduh ulang meski cache lokal sudah ada")
    parser.add_argument(
        "--max-ruling-cards",
        type=int,
        default=350,
        help="Jumlah kartu prioritas untuk pengunduhan FAQ/Ruling awal dari db.ygoresources.com",
    )
    parser.add_argument(
        "--max-qa-entries",
        type=int,
        default=900,
        help="Jumlah maksimum entri Q&A ruling yang diunduh pada batch awal",
    )
    parser.add_argument(
        "--max-card-embeddings",
        type=int,
        default=600,
        help="Jumlah kartu yang di-embed ke Vector Index per sesi (isi 0 untuk embed seluruh ~14.000 kartu)",
    )
    parser.add_argument(
        "--embedding-provider",
        choices=["gemini", "fastembed"],
        default=None,
        help="Pilih 'fastembed' (BAAI/bge-base-en-v1.5 768d lokal cepat tanpa limit kuota) atau 'gemini'",
    )
    args = parser.parse_args()

    if not (args.fetch or args.ingest or args.embed or args.all):
        parser.print_help()
        return

    settings = get_settings()
    if args.embedding_provider:
        settings.embedding_provider = args.embedding_provider
    do_fetch = args.fetch or args.all
    do_ingest = args.ingest or args.all
    do_embed = args.embed or args.all

    cards_enriched, banlist_entries = process_cards_and_banlist(
        settings,
        force_download=args.force if do_fetch else False,
        force_process=args.force if do_fetch else False,
    )
    rule_chunks = process_rulebook(
        settings,
        force_download=args.force if do_fetch else False,
        force_process=args.force if do_fetch else False,
    )
    psct_rules, rulings_bundle = process_psct_and_rulings(
        cards_enriched=cards_enriched,
        settings=settings,
        max_priority_cards=args.max_ruling_cards,
        max_qa_entries=args.max_qa_entries,
        force=args.force if do_fetch else False,
    )

    logger.info(
        f"Ringkasan Dataset Lokal:\n"
        f"  1. Rulebook & Master Rule Chunks : {len(rule_chunks):,}\n"
        f"  2. Total Kartu Teranalisis PSCT  : {len(cards_enriched):,}\n"
        f"  3. Aturan PSCT                   : {len(psct_rules):,}\n"
        f"     Card FAQs                     : {len(rulings_bundle.get('faqs', [])):,}\n"
        f"     Official Q&A Rulings          : {len(rulings_bundle.get('rulings', [])):,}\n"
        f"  4. Entri Banlist (TCG/OCG/Goat)  : {len(banlist_entries):,}"
    )

    if do_ingest or do_embed:
        client = Neo4jGraphClient(settings)
        ok, msg = False, ""
        for attempt in range(1, 16):
            ok, msg = client.check_connection()
            if ok:
                break
            if "incomplete handshake" in msg.lower() or "connection reset" in msg.lower() or attempt <= 6:
                logger.info(
                    f"Menunggu server Neo4j selesai inisialisasi JVM/APOC (percobaan {attempt}/15)..."
                )
                time.sleep(4)
                client.close()
            else:
                break

        if not ok:
            logger.error(
                f"Tidak dapat terhubung ke Neo4j ({settings.neo4j_uri}): {msg}\n"
                "Pastikan Docker Desktop aktif lalu jalankan: docker compose up -d"
            )
            sys.exit(1)

        if do_ingest:
            setup_neo4j_schema(client, embedding_dim=settings.embedding_dimension)
            ingest_rulebook_to_neo4j(client, rule_chunks)
            ingest_psct_rules_to_neo4j(client, psct_rules)
            ingest_cards_and_banlist_to_neo4j(client, cards_enriched, banlist_entries)
            ingest_rulings_to_neo4j(client, rulings_bundle)
            stats = client.get_graph_statistics()
            logger.success(f"Statistik Knowledge Graph Neo4j: {stats}")

        if do_embed:
            max_cards = None if args.max_card_embeddings <= 0 else args.max_card_embeddings
            embedder = GeminiEmbedder(settings)
            embed_and_index_nodes(
                client=client,
                embedder=embedder,
                rule_chunks=rule_chunks,
                psct_rules=psct_rules,
                rulings_bundle=rulings_bundle,
                cards_enriched=cards_enriched,
                max_card_embeddings=max_cards,
            )

        client.close()


if __name__ == "__main__":
    main()
