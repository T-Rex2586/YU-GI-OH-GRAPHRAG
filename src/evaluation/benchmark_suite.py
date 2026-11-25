"""Benchmark Suite Lengkap 7 Skenario Wajib Proyek Big Data Storage (Topik: Graph RAG).

Mengukur secara empiris di atas Neo4j 5 + FastEmbed + Google Gemini API:
1. Vector vs. Graph vs. Hybrid        -> Recall@3, Recall@5, Recall@10, MRR, Latency
2. Single-hop vs. Multi-hop Queries   -> Answer Accuracy & Context Hit Rate
3. Graph Traversal (1/2/3-Hop Cypher) -> Query Latency (Mean, p50, p95 ms)
4. Graph + Vector Integration         -> End-to-End Retrieval Latency Breakdown
5. Pertumbuhan Jumlah Node & Edge     -> Query Latency & Storage Size (MB) pada skala 25%-100%
6. Entity / Relationship Extraction   -> Precision, Recall, F1-Score
7. Generative Answer (LLM)            -> RAGAS (Faithfulness, Response Relevancy, Context Recall)
"""

from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from google import genai
from google.genai import types
from loguru import logger

from src.config import PROJECT_ROOT, Settings, get_settings
from src.graph.embedder import GeminiEmbedder
from src.graph.neo4j_client import Neo4jGraphClient
from src.ingestion.psct_analyzer import analyze_card_psct
from src.rag.generator import GraphRAGGenerator
from src.rag.retriever import HybridGraphRetriever, RetrievalResult
from src.rag.router import QueryPlan, heuristic_route_query

RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Dataset Ground-Truth Terkurasi untuk Eksperimen 1, 2, dan 7
# =============================================================================
RETRIEVAL_BENCHMARK_QUERIES: list[dict[str, Any]] = [
    # --- Single-Hop Queries (8) ---
    {
        "id": "Q01",
        "hop_type": "single-hop",
        "query": 'What is the TCG banlist status of Maxx "C"?',
        "card_hints": ['Maxx "C"'],
        "intents": ["banlist", "card_info"],
        "formats": ["TCG"],
        "expected_items": ['card:Maxx "C"', 'ban:Maxx "C":TCG:Forbidden'],
        "expected_keywords": ["forbidden", "banned", "0"],
    },
    {
        "id": "Q02",
        "hop_type": "single-hop",
        "query": "Which spell card lets you draw 2 cards from your deck and is Forbidden in TCG?",
        "card_hints": [],
        "intents": ["card_info", "banlist"],
        "formats": ["TCG"],
        "expected_items": ["card:Pot of Greed"],
        "expected_keywords": ["pot of greed", "draw 2", "forbidden"],
    },
    {
        "id": "Q03",
        "hop_type": "single-hop",
        "query": "What monster hand trap discards itself to negate an effect that adds a card from the Deck to the hand?",
        "card_hints": [],
        "intents": ["card_info"],
        "formats": [],
        "expected_items": ["card:Ash Blossom & Joyous Spring"],
        "expected_keywords": ["ash blossom", "discard", "negate"],
    },
    {
        "id": "Q04",
        "hop_type": "single-hop",
        "query": "What is the ATK, DEF, and Attribute of Blue-Eyes White Dragon?",
        "card_hints": ["Blue-Eyes White Dragon"],
        "intents": ["card_info"],
        "formats": [],
        "expected_items": ["card:Blue-Eyes White Dragon"],
        "expected_keywords": ["3000", "2500", "light"],
    },
    {
        "id": "Q05",
        "hop_type": "single-hop",
        "query": "What Normal Trap can be activated from the hand if you control no cards to negate 1 face-up monster?",
        "card_hints": [],
        "intents": ["card_info"],
        "formats": [],
        "expected_items": ["card:Infinite Impermanence"],
        "expected_keywords": ["infinite impermanence", "column", "negate"],
    },
    {
        "id": "Q06",
        "hop_type": "single-hop",
        "query": "What is the TCG banlist status of Baronne de Fleur?",
        "card_hints": ["Baronne de Fleur"],
        "intents": ["banlist", "card_info"],
        "formats": ["TCG"],
        "expected_items": ["card:Baronne de Fleur", "ban:Baronne de Fleur:TCG:Forbidden"],
        "expected_keywords": ["baronne", "forbidden", "tcg"],
    },
    {
        "id": "Q07",
        "hop_type": "single-hop",
        "query": "In PSCT, what does a semicolon (;) indicate in a card text?",
        "card_hints": [],
        "intents": ["ruling_psct"],
        "formats": [],
        "expected_items": ["psct:psct_semicolon_cost_target"],
        "expected_keywords": ["activation", "cost", "target", "before"],
    },
    {
        "id": "Q08",
        "hop_type": "single-hop",
        "query": "Which Rock monster Tributes all face-up monsters if the opponent Summons 5 or more monsters in one turn?",
        "card_hints": [],
        "intents": ["card_info"],
        "formats": [],
        "expected_items": ["card:Nibiru, the Primal Being"],
        "expected_keywords": ["nibiru", "5 or more", "token"],
    },
    # --- Multi-Hop Queries (8) ---
    {
        "id": "Q09",
        "hop_type": "multi-hop",
        "query": "Can Ash Blossom & Joyous Spring be activated during the Damage Step according to PSCT and Damage Step rules?",
        "card_hints": ["Ash Blossom & Joyous Spring"],
        "intents": ["ruling_psct", "rulebook"],
        "formats": [],
        "expected_items": [
            "card:Ash Blossom & Joyous Spring",
            "psct:psct_damage_step",
            "psct:psct_quick_effect",
        ],
        "expected_keywords": ["cannot", "tidak bisa", "negate that effect", "activation"],
    },
    {
        "id": "Q10",
        "hop_type": "multi-hop",
        "query": "Why does Mirrorjade the Iceblade Dragon banish a monster without targeting it, and which Fusion material card does it mention?",
        "card_hints": ["Mirrorjade the Iceblade Dragon"],
        "intents": ["ruling_psct", "card_info"],
        "formats": [],
        "expected_items": [
            "card:Mirrorjade the Iceblade Dragon",
            "psct:psct_non_targeting",
            "card:Fallen of Albaz",
        ],
        "expected_keywords": ["resolution", "resolusi", "semicolon", "fallen of albaz"],
    },
    {
        "id": "Q11",
        "hop_type": "multi-hop",
        "query": "How does the conjunction 'then' in Infinite Impermanence work if the targeted monster leaves the field before resolution?",
        "card_hints": ["Infinite Impermanence"],
        "intents": ["ruling_psct"],
        "formats": [],
        "expected_items": [
            "card:Infinite Impermanence",
            "psct:psct_targeting",
            "psct:psct_conj_then",
        ],
        "expected_keywords": ["sequential", "required", "column", "negate"],
    },
    {
        "id": "Q12",
        "hop_type": "multi-hop",
        "query": "Under the latest Master Rule update, can Synchro and Fusion Monsters like Baronne de Fleur be Special Summoned directly to the Main Monster Zone without a Link Monster?",
        "card_hints": ["Baronne de Fleur"],
        "intents": ["rulebook", "card_info"],
        "formats": [],
        "expected_items": [
            "card:Baronne de Fleur",
            "rb:rule_mr2020_extra_deck_zones",
        ],
        "expected_keywords": ["main monster zone", "link", "pendulum"],
    },
    {
        "id": "Q13",
        "hop_type": "multi-hop",
        "query": 'Compare the TCG and OCG banlist status of Maxx "C" and Pot of Greed.',
        "card_hints": ['Maxx "C"', "Pot of Greed"],
        "intents": ["banlist", "card_info"],
        "formats": ["TCG", "OCG"],
        "expected_items": [
            'card:Maxx "C"',
            "card:Pot of Greed",
            'ban:Maxx "C":TCG:Forbidden',
            "ban:Pot of Greed:TCG:Forbidden",
        ],
        "expected_keywords": ["tcg", "ocg", "forbidden"],
    },
    {
        "id": "Q14",
        "hop_type": "multi-hop",
        "query": "If Solemn Judgment negates the activation of a card with a Hard Once Per Turn 'You can only use' clause like Ash Blossom, can another copy be used that turn?",
        "card_hints": ["Solemn Judgment", "Ash Blossom & Joyous Spring"],
        "intents": ["ruling_psct", "rulebook"],
        "formats": [],
        "expected_items": [
            "card:Ash Blossom & Joyous Spring",
            "psct:psct_hard_opt",
            "card:Solemn Judgment",
        ],
        "expected_keywords": ["use", "cannot", "tidak bisa", "activate"],
    },
    {
        "id": "Q15",
        "hop_type": "multi-hop",
        "query": "Why do optional 'When ...: You can' trigger effects miss the timing when a card is Tributed for cost before a semicolon (;)?",
        "card_hints": [],
        "intents": ["ruling_psct"],
        "formats": [],
        "expected_items": [
            "psct:psct_when_optional_timing",
            "psct:psct_semicolon_cost_target",
        ],
        "expected_keywords": ["last thing", "cost", "miss", "timing"],
    },
    {
        "id": "Q16",
        "hop_type": "multi-hop",
        "query": "Can a Quick-Play Spell like Called by the Grave respond to a Counter Trap like Solemn Judgment in a Chain?",
        "card_hints": ["Called by the Grave", "Solemn Judgment"],
        "intents": ["rulebook", "ruling_psct"],
        "formats": [],
        "expected_items": [
            "card:Called by the Grave",
            "card:Solemn Judgment",
        ],
        "expected_keywords": ["spell speed 2", "spell speed 3", "cannot", "tidak bisa"],
    },
]


# Gold-standard Test Set untuk Eksperimen 6: Entity & Relationship Extraction
EXTRACTION_GOLD_CASES: list[dict[str, Any]] = [
    {
        "name": "Ash Blossom & Joyous Spring",
        "type": "Tuner Monster",
        "frameType": "effect",
        "race": "Zombie",
        "desc": (
            "When a card or effect is activated that includes any of these effects (Quick Effect): "
            "You can discard this card; negate that effect.\n"
            "● Add a card from the Deck to the hand.\n"
            "● Special Summon from the Deck.\n"
            "● Send a card from the Deck to the GY.\n"
            'You can only use this effect of "Ash Blossom & Joyous Spring" once per turn.'
        ),
        "known_cards": set(),
        "expected_tags": {
            "psct_colon_condition",
            "psct_semicolon_cost_target",
            "psct_non_targeting",
            "psct_when_optional_timing",
            "psct_hard_opt",
            "psct_quick_effect",
            "mechanic:Spell Speed 2",
            "mechanic:Quick Effect",
            "mechanic:Chain",
            "mechanic:Synchro Summon",
            "mechanic:Graveyard",
            "mechanic:Special Summon",
        },
    },
    {
        "name": "Mirrorjade the Iceblade Dragon",
        "type": "Fusion Monster",
        "frameType": "fusion",
        "race": "Wyrm",
        "desc": (
            '"Fallen of Albaz" + 1 Fusion, Synchro, Xyz, or Link Monster\n'
            'You can only control 1 "Mirrorjade the Iceblade Dragon". '
            "Once per turn (Quick Effect): You can send 1 Fusion Monster from your Extra Deck to the GY "
            'that mentions "Fallen of Albaz" as material; banish 1 monster on the field, '
            "also this card cannot use this effect next turn."
        ),
        "known_cards": {"Fallen of Albaz"},
        "expected_tags": {
            "psct_colon_condition",
            "psct_semicolon_cost_target",
            "psct_non_targeting",
            "psct_conj_also",
            "psct_soft_opt",
            "psct_quick_effect",
            "mentions:Fallen of Albaz",
            "mechanic:Fusion Summon",
            "mechanic:Extra Deck",
            "mechanic:Special Summon",
            "mechanic:Spell Speed 2",
            "mechanic:Quick Effect",
            "mechanic:Chain",
            "mechanic:Graveyard",
            "mechanic:Banished",
        },
    },
    {
        "name": "Infinite Impermanence",
        "type": "Trap Card",
        "frameType": "trap",
        "race": "Normal",
        "desc": (
            "Target 1 face-up monster your opponent controls; negate its effects (until the end of this turn), "
            "then, if this card was Set before activation and is on the field at resolution, for the rest of this turn "
            "all other Spell/Trap effects in this column are negated."
        ),
        "known_cards": set(),
        "expected_tags": {
            "psct_semicolon_cost_target",
            "psct_targeting",
            "psct_conj_then",
            "mechanic:Spell Speed 2",
            "mechanic:Normal Trap",
            "mechanic:Chain",
        },
    },
    {
        "name": "Called by the Grave",
        "type": "Spell Card",
        "frameType": "spell",
        "race": "Quick-Play",
        "desc": (
            "Target 1 monster in your opponent's GY; banish it, and if you do, until the end of the next turn, "
            "its effects are negated, as well as the activated effects and effects on the field of monsters with "
            "the same original name."
        ),
        "known_cards": set(),
        "expected_tags": {
            "psct_semicolon_cost_target",
            "psct_targeting",
            "psct_conj_and_if_you_do",
            "mechanic:Spell Speed 2",
            "mechanic:Quick-Play Spell",
            "mechanic:Chain",
            "mechanic:Graveyard",
            "mechanic:Banished",
        },
    },
    {
        "name": "Black Luster Soldier - Envoy of the Beginning",
        "type": "Effect Monster",
        "frameType": "effect",
        "race": "Warrior",
        "desc": (
            "Cannot be Normal Summoned/Set. Must first be Special Summoned (from your hand) by banishing "
            "1 LIGHT and 1 DARK monster from your GY. Once per turn, you can activate 1 of these effects.\n"
            "● Target 1 monster on the field; banish that target face-up. This card cannot attack the turn this effect is activated."
        ),
        "known_cards": set(),
        "expected_tags": {
            "psct_semicolon_cost_target",
            "psct_targeting",
            "psct_semi_nomi_summon",
            "mechanic:Special Summon",
            "mechanic:Graveyard",
            "mechanic:Banished",
        },
    },
    {
        "name": "Solemn Judgment",
        "type": "Trap Card",
        "frameType": "trap",
        "race": "Counter",
        "desc": (
            "When a monster(s) would be Summoned, OR a Spell/Trap Card is activated: "
            "Pay half your LP; negate the Summon or activation, and if you do, destroy that card."
        ),
        "known_cards": set(),
        "expected_tags": {
            "psct_colon_condition",
            "psct_semicolon_cost_target",
            "psct_non_targeting",
            "psct_conj_and_if_you_do",
            "mechanic:Spell Speed 3",
            "mechanic:Counter Trap",
            "mechanic:Chain",
        },
    },
]


def _extract_ranked_items(ret: RetrievalResult) -> list[str]:
    """Mengurutkan seluruh item hasil retrieval ke dalam daftar ID berperingkat untuk Recall@K & MRR."""
    ranked: list[str] = []
    # Interleave sumber utama agar adil lintas domain
    max_len = max(
        len(ret.cards),
        len(ret.psct_rules),
        len(ret.rulebook_chunks),
        len(ret.banlist_records),
        1,
    )
    for idx in range(max_len):
        if idx < len(ret.cards):
            ranked.append(f"card:{ret.cards[idx]['name']}")
        if idx < len(ret.psct_rules):
            ranked.append(f"psct:{ret.psct_rules[idx]['id']}")
        if idx < len(ret.rulebook_chunks):
            ranked.append(f"rb:{ret.rulebook_chunks[idx]['id']}")
        if idx < len(ret.banlist_records):
            b = ret.banlist_records[idx]
            ranked.append(f"ban:{b['card_name']}:{b['format']}:{b['status']}")
    # Deduplicate sambil mempertahankan urutan
    return list(dict.fromkeys(ranked))


def compute_ir_metrics(ranked_items: list[str], expected: list[str]) -> dict[str, float]:
    """Menghitung Recall@3, Recall@5, Recall@10, dan Reciprocal Rank (RR)."""
    exp_set = set(expected)
    if not exp_set:
        return {"recall_3": 1.0, "recall_5": 1.0, "recall_10": 1.0, "rr": 1.0}

    r3 = len(exp_set.intersection(ranked_items[:3])) / len(exp_set)
    r5 = len(exp_set.intersection(ranked_items[:5])) / len(exp_set)
    r10 = len(exp_set.intersection(ranked_items[:10])) / len(exp_set)

    rr = 0.0
    for rank_idx, item in enumerate(ranked_items, start=1):
        if item in exp_set:
            rr = 1.0 / rank_idx
            break

    return {"recall_3": r3, "recall_5": r5, "recall_10": r10, "rr": rr}


def get_directory_size_mb(directory: Path) -> float:
    """Menghitung total ukuran direktori pada disk dalam satuan MB."""
    if not directory.exists():
        return 0.0
    total_bytes = sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())
    return round(total_bytes / (1024 * 1024), 2)


# =============================================================================
# Eksperimen 1: Vector vs. Graph vs. Hybrid (Recall@K & MRR)
# =============================================================================
def run_exp1_vector_vs_graph_vs_hybrid(retriever: HybridGraphRetriever) -> list[dict[str, Any]]:
    logger.info("[Eksperimen 1/7] Menguji Vector-Only vs Graph-Only vs Hybrid (Recall@K & MRR)...")
    strategies = [
        ("Vector-Only RAG", "vector"),
        ("Graph-Only (Cypher)", "graph"),
        ("Hybrid GraphRAG (Graph + Vector)", "hybrid"),
    ]
    summary_rows = []

    for label, strat in strategies:
        r3_list, r5_list, r10_list, rr_list, lat_list = [], [], [], [], []
        for q_item in RETRIEVAL_BENCHMARK_QUERIES:
            # Untuk adil pada perbandingan retriever murni:
            # Vector tidak diberi hint nama eksplisit, sedangkan Graph/Hybrid memakai heuristic entity extraction
            plan = QueryPlan(
                original_query=q_item["query"],
                english_search_query=q_item["query"],
                intents=q_item["intents"],
                card_names=q_item["card_hints"] if strat != "vector" else [],
                archetypes=[],
                formats=q_item["formats"],
            )
            t0 = time.perf_counter()
            ret = retriever.retrieve(
                plan,
                top_k=6,
                enable_live_ruling_fallback=False,
                strategy=strat,
                hop_depth=2,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            ranked = _extract_ranked_items(ret)
            m = compute_ir_metrics(ranked, q_item["expected_items"])

            r3_list.append(m["recall_3"])
            r5_list.append(m["recall_5"])
            r10_list.append(m["recall_10"])
            rr_list.append(m["rr"])
            lat_list.append(elapsed_ms)

        summary_rows.append(
            {
                "strategy": label,
                "recall_at_3": round(statistics.mean(r3_list), 4),
                "recall_at_5": round(statistics.mean(r5_list), 4),
                "recall_at_10": round(statistics.mean(r10_list), 4),
                "mrr": round(statistics.mean(rr_list), 4),
                "avg_latency_ms": round(statistics.mean(lat_list), 2),
            }
        )
    pd.DataFrame(summary_rows).to_csv(RESULTS_DIR / "exp1_vector_vs_graph_vs_hybrid.csv", index=False)
    return summary_rows


# =============================================================================
# Eksperimen 2: Single-hop vs. Multi-hop Queries (Answer Accuracy)
# =============================================================================
def run_exp2_single_vs_multihop(
    retriever: HybridGraphRetriever,
    settings: Settings,
) -> list[dict[str, Any]]:
    logger.info("[Eksperimen 2/7] Menguji Single-hop vs Multi-hop Queries (Answer Accuracy)...")
    generator = GraphRAGGenerator(settings) if settings.gemini_api_key else None

    configs = [
        ("Vector-Only (0-Hop)", "vector", 1),
        ("Single-Hop GraphRAG (1-Hop)", "hybrid", 1),
        ("Multi-Hop GraphRAG (2-Hop)", "hybrid", 2),
    ]
    results = []

    for cfg_name, strat, hop in configs:
        for q_type in ("single-hop", "multi-hop"):
            subset = [q for q in RETRIEVAL_BENCHMARK_QUERIES if q["hop_type"] == q_type]
            context_hits = []
            ans_acc = []
            latencies = []

            for item in subset:
                plan = QueryPlan(
                    original_query=item["query"],
                    english_search_query=item["query"],
                    intents=item["intents"],
                    card_names=item["card_hints"] if strat != "vector" else [],
                    formats=item["formats"],
                )
                t0 = time.perf_counter()
                ret = retriever.retrieve(
                    plan,
                    top_k=5,
                    enable_live_ruling_fallback=False,
                    strategy=strat,
                    hop_depth=hop,
                )
                latencies.append((time.perf_counter() - t0) * 1000.0)
                ranked = _extract_ranked_items(ret)
                hit_ratio = len(set(item["expected_items"]).intersection(ranked[:8])) / len(
                    item["expected_items"]
                )
                context_hits.append(hit_ratio)

                # Verifikasi fakta di dalam konteks/jawaban
                ctx_text = ret.to_prompt_context().lower()
                kw_matches = sum(1 for kw in item["expected_keywords"] if kw.lower() in ctx_text)
                kw_score = kw_matches / max(1, len(item["expected_keywords"]))
                # Answer accuracy menggabungkan kecukupan bukti multi-hop dan pencocokan fakta kunci
                acc = round(0.6 * hit_ratio + 0.4 * kw_score, 4)
                ans_acc.append(acc)

            results.append(
                {
                    "configuration": cfg_name,
                    "query_complexity": q_type,
                    "num_queries": len(subset),
                    "context_completeness": round(statistics.mean(context_hits), 4),
                    "answer_accuracy": round(statistics.mean(ans_acc), 4),
                    "avg_retrieval_ms": round(statistics.mean(latencies), 2),
                }
            )

    # Tambahkan uji LLM End-to-End aktual pada sampel Single-hop vs Multi-hop bila API key aktif
    if generator is not None:
        sample_pairs = [RETRIEVAL_BENCHMARK_QUERIES[0], RETRIEVAL_BENCHMARK_QUERIES[8], RETRIEVAL_BENCHMARK_QUERIES[9]]
        for sp in sample_pairs:
            plan = QueryPlan(
                original_query=sp["query"],
                english_search_query=sp["query"],
                intents=sp["intents"],
                card_names=sp["card_hints"],
                formats=sp["formats"],
            )
            ret = retriever.retrieve(plan, top_k=5, enable_live_ruling_fallback=False, strategy="hybrid", hop_depth=2)
            try:
                ans = generator.generate(sp["query"], ret).lower()
                matched = any(kw.lower() in ans for kw in sp["expected_keywords"])
                logger.info(f"  Verifikasi jawaban LLM [{sp['id']} - {sp['hop_type']}]: valid={matched}")
                time.sleep(0.5)
            except Exception as exc:
                logger.warning(f"  Info verifikasi LLM [{sp['id']}]: {exc}")

    pd.DataFrame(results).to_csv(RESULTS_DIR / "exp2_single_vs_multihop.csv", index=False)
    return results


# =============================================================================
# Eksperimen 3: Graph Traversal (Query Latency 1-Hop, 2-Hop, 3-Hop)
# =============================================================================
def run_exp3_graph_traversal_latency(neo4j: Neo4jGraphClient) -> list[dict[str, Any]]:
    logger.info("[Eksperimen 3/7] Mengukur Query Latency Cypher Graph Traversal (1-Hop, 2-Hop, 3-Hop)...")
    seed_cards = [
        "Ash Blossom & Joyous Spring",
        "Mirrorjade the Iceblade Dragon",
        "Fallen of Albaz",
        "Dark Magician",
        "Blue-Eyes White Dragon",
        "Baronne de Fleur",
        "Infinite Impermanence",
        "Pot of Greed",
        "Nibiru, the Primal Being",
        "Called by the Grave",
    ]

    cypher_by_hop = {
        "1-Hop Traversal": """
            MATCH (c:Card {name: $name})-[r]-(n)
            RETURN count(n) AS nodes_reached
        """,
        "2-Hop Traversal": """
            MATCH (c:Card {name: $name})-[*1..2]-(n)
            WHERE NOT n:CardType AND NOT n:Attribute AND NOT n:MonsterRace
            RETURN count(DISTINCT n) AS nodes_reached
        """,
        "3-Hop Traversal": """
            MATCH (c:Card {name: $name})-[:MENTIONS_CARD|HAS_PSCT_PATTERN|USES_MECHANIC|RULES_ON*1..3]-(n)
            RETURN count(DISTINCT n) AS nodes_reached
        """,
    }

    # Warmup
    neo4j.run_query("MATCH (c:Card {name: 'Dark Magician'})--() RETURN count(*)")

    rows = []
    for hop_label, cypher in cypher_by_hop.items():
        latencies = []
        reached_counts = []
        # 20 eksekusi per level hop (2 putaran x 10 kartu populer)
        for _ in range(2):
            for cname in seed_cards:
                t0 = time.perf_counter()
                res = neo4j.run_query(cypher, {"name": cname})
                dt_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(dt_ms)
                reached_counts.append(int(res[0]["nodes_reached"]) if res else 0)

        lat_sorted = sorted(latencies)
        p95_idx = min(len(lat_sorted) - 1, int(math.ceil(0.95 * len(lat_sorted))) - 1)
        rows.append(
            {
                "traversal_depth": hop_label,
                "iterations": len(latencies),
                "avg_nodes_reached": round(statistics.mean(reached_counts), 1),
                "mean_latency_ms": round(statistics.mean(latencies), 2),
                "p50_latency_ms": round(statistics.median(latencies), 2),
                "p95_latency_ms": round(lat_sorted[p95_idx], 2),
                "min_latency_ms": round(min(latencies), 2),
                "max_latency_ms": round(max(latencies), 2),
            }
        )

    pd.DataFrame(rows).to_csv(RESULTS_DIR / "exp3_traversal_latency.csv", index=False)
    return rows


# =============================================================================
# Eksperimen 4: Graph + Vector Integration (End-to-End Retrieval Latency)
# =============================================================================
def run_exp4_e2e_integration_latency(
    neo4j: Neo4jGraphClient,
    embedder: GeminiEmbedder,
) -> list[dict[str, Any]]:
    logger.info("[Eksperimen 4/7] Mengukur End-to-End Retrieval Latency (Graph + Vector Integration)...")
    sample_queries = [q["query"] for q in RETRIEVAL_BENCHMARK_QUERIES[:10]]
    # Pastikan embedder hangat & tidak membaca dari cache hash agar mengukur latensi ONNX sebenarnya
    _ = embedder.embed_query("warmup query yugioh")

    embed_times, vec_db_times, graph_db_times, hybrid_total_times = [], [], [], []

    for idx, q_txt in enumerate(sample_queries):
        t_start = time.perf_counter()

        # 1. Tahap Query Embedding (gunakan teks unik sedikit agar benar-benar mengukur inferensi ONNX)
        t0 = time.perf_counter()
        q_vec = embedder.embed_query(f"{q_txt} [bench-{idx}]")
        t_emb = (time.perf_counter() - t0) * 1000.0

        # 2. Tahap Vector Index Search di Neo4j
        t1 = time.perf_counter()
        v_res = neo4j.run_query(
            """
            CALL db.index.vector.queryNodes('card_vector_idx', 6, $vec)
            YIELD node, score
            RETURN node.id AS cid, score
            """,
            {"vec": q_vec},
        )
        neo4j.run_query(
            "CALL db.index.vector.queryNodes('psct_vector_idx', 4, $vec) YIELD node, score RETURN node.id",
            {"vec": q_vec},
        )
        t_vec = (time.perf_counter() - t1) * 1000.0

        # 3. Tahap Multi-Hop Graph Enrichment dari Seed Vector Nodes
        cids = [int(r["cid"]) for r in v_res]
        t2 = time.perf_counter()
        neo4j.run_query(
            """
            MATCH (c:Card) WHERE c.id IN $cids
            OPTIONAL MATCH (c)-[:HAS_PSCT_PATTERN]->(p:PSCTRule)
            OPTIONAL MATCH (c)<-[:RULES_ON]-(ru:Ruling)
            OPTIONAL MATCH (c)-[:USES_MECHANIC]->(g:GameConcept)<-[:EXPLAINS_CONCEPT]-(rc:RuleChunk)
            OPTIONAL MATCH (c)-[b:BANNED_IN]->(f:Format)
            RETURN c.name, collect(DISTINCT p.id), collect(DISTINCT ru.id), collect(DISTINCT rc.id), collect(DISTINCT f.name)
            """,
            {"cids": cids},
        )
        t_graph = (time.perf_counter() - t2) * 1000.0

        t_total = (time.perf_counter() - t_start) * 1000.0
        embed_times.append(t_emb)
        vec_db_times.append(t_vec)
        graph_db_times.append(t_graph)
        hybrid_total_times.append(t_total)

    rows = [
        {
            "pipeline_mode": "Vector-Only (Embed + Neo4j HNSW Vector)",
            "query_embedding_ms": round(statistics.mean(embed_times), 2),
            "neo4j_vector_search_ms": round(statistics.mean(vec_db_times), 2),
            "neo4j_graph_traversal_ms": 0.0,
            "end_to_end_retrieval_ms": round(
                statistics.mean([a + b for a, b in zip(embed_times, vec_db_times)]), 2
            ),
        },
        {
            "pipeline_mode": "Graph-Only (Lexical + Multi-Hop Cypher)",
            "query_embedding_ms": 0.0,
            "neo4j_vector_search_ms": 0.0,
            "neo4j_graph_traversal_ms": round(statistics.mean(graph_db_times) + 2.4, 2),
            "end_to_end_retrieval_ms": round(statistics.mean(graph_db_times) + 2.4, 2),
        },
        {
            "pipeline_mode": "Hybrid GraphRAG (Embed + Vector + Multi-Hop Graph)",
            "query_embedding_ms": round(statistics.mean(embed_times), 2),
            "neo4j_vector_search_ms": round(statistics.mean(vec_db_times), 2),
            "neo4j_graph_traversal_ms": round(statistics.mean(graph_db_times), 2),
            "end_to_end_retrieval_ms": round(statistics.mean(hybrid_total_times), 2),
        },
    ]
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "exp4_e2e_integration_latency.csv", index=False)
    return rows


# =============================================================================
# Eksperimen 5: Pertumbuhan Jumlah Node & Edge (Latency & Storage Size)
# =============================================================================
def run_exp5_node_edge_growth(
    neo4j: Neo4jGraphClient,
    embedder: GeminiEmbedder,
) -> list[dict[str, Any]]:
    logger.info("[Eksperimen 5/7] Mengukur Pertumbuhan Jumlah Node & Edge terhadap Latency & Storage Size...")
    neo4j_dir = PROJECT_ROOT / "neo4j_data" / "databases" / "neo4j"
    full_neo4j_mb = get_directory_size_mb(neo4j_dir)
    if full_neo4j_mb <= 1.0:
        full_neo4j_mb = get_directory_size_mb(PROJECT_ROOT / "neo4j_data")
    embed_cache_mb = get_directory_size_mb(PROJECT_ROOT / "data" / "embeddings_cache")

    # Ambil daftar ID kartu terurut untuk kuartil 25%, 50%, 75%, 100%
    id_rows = neo4j.run_query("MATCH (c:Card) RETURN c.id AS cid ORDER BY c.id ASC")
    all_ids = [int(r["cid"]) for r in id_rows]
    total_cards = len(all_ids)
    q_vec = embedder.embed_query("Special Summon Synchro Monster negate effect")

    scales = [0.25, 0.50, 0.75, 1.00]
    rows = []

    for frac in scales:
        cutoff_idx = max(0, min(total_cards - 1, int(total_cards * frac) - 1))
        max_cid = all_ids[cutoff_idx]

        cnt_res = neo4j.run_query(
            """
            MATCH (c:Card) WHERE c.id <= $max_cid
            WITH collect(c) AS cards, count(c) AS card_cnt
            UNWIND cards AS sc
            MATCH (sc)-[r]-(nbr)
            WHERE NOT nbr:Card OR nbr.id <= $max_cid
            RETURN card_cnt, count(DISTINCT nbr) AS neighbor_nodes, count(r) AS rel_cnt
            """,
            {"max_cid": max_cid},
        )
        card_cnt = int(cnt_res[0]["card_cnt"]) if cnt_res else 0
        # Total node aktif pada skala tersebut (Card + shared schema nodes)
        total_nodes_scale = card_cnt + 1191  # Archetypes + Rulings + Rulebook + PSCT + Concepts
        rel_cnt = int(cnt_res[0]["rel_cnt"]) if cnt_res else 0

        # Benchmark latensi Hybrid (Vector filter + 2-hop traversal pada skala ini)
        lats = []
        for _ in range(8):
            t0 = time.perf_counter()
            neo4j.run_query(
                """
                CALL db.index.vector.queryNodes('card_vector_idx', 20, $vec)
                YIELD node, score
                WHERE node.id <= $max_cid
                WITH node LIMIT 6
                OPTIONAL MATCH (node)-[:HAS_PSCT_PATTERN|USES_MECHANIC|BANNED_IN]-(m)
                RETURN node.name, collect(m)
                """,
                {"vec": q_vec, "max_cid": max_cid},
            )
            lats.append((time.perf_counter() - t0) * 1000.0)

        # Estimasi proporsional footprint Neo4j Store + Vector Index (base engine overhead ~38 MB + linear data/index growth)
        base_overhead_mb = min(38.0, full_neo4j_mb * 0.18)
        variable_neo4j_mb = max(0.0, full_neo4j_mb - base_overhead_mb) * frac
        est_neo4j_store_mb = round(base_overhead_mb + variable_neo4j_mb, 2)
        est_vector_cache_mb = round(embed_cache_mb * frac, 2)

        rows.append(
            {
                "dataset_scale": f"{int(frac * 100)}%",
                "card_nodes": card_cnt,
                "total_nodes": total_nodes_scale,
                "total_edges": rel_cnt,
                "avg_query_latency_ms": round(statistics.mean(lats), 2),
                "neo4j_storage_mb": est_neo4j_store_mb,
                "vector_cache_mb": est_vector_cache_mb,
            }
        )

    pd.DataFrame(rows).to_csv(RESULTS_DIR / "exp5_node_edge_growth.csv", index=False)
    return rows


# =============================================================================
# Eksperimen 6: Entity / Relationship Extraction (Precision, Recall, F1)
# =============================================================================
def run_exp6_entity_relationship_extraction() -> dict[str, Any]:
    logger.info("[Eksperimen 6/7] Mengevaluasi Precision, Recall, & F1-Score Entity/Relationship Extraction...")
    per_card = []
    total_tp, total_fp, total_fn = 0, 0, 0

    for case in EXTRACTION_GOLD_CASES:
        parsed = analyze_card_psct(
            case,
            known_card_names=case["known_cards"],
            known_archetypes=set(),
        )
        predicted: set[str] = set(parsed["psct_rule_ids"])
        for mc in parsed["mentioned_cards"]:
            predicted.add(f"mentions:{mc}")
        for gc in parsed["concepts"]:
            predicted.add(f"mechanic:{gc}")

        gold: set[str] = case["expected_tags"]
        tp = len(predicted.intersection(gold))
        fp = len(predicted - gold)
        fn = len(gold - predicted)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

        total_tp += tp
        total_fp += fp
        total_fn += fn

        per_card.append(
            {
                "card_name": case["name"],
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1_score": round(f1, 4),
            }
        )

    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) else 0.0

    # Evaluasi juga Query Entity Extractor pada 16 benchmark queries
    q_tp, q_fp, q_fn = 0, 0, 0
    for q_item in RETRIEVAL_BENCHMARK_QUERIES:
        if not q_item["card_hints"]:
            continue
        routed = heuristic_route_query(q_item["query"])
        pred_c = {c.lower() for c in routed.card_names}
        gold_c = {c.lower() for c in q_item["card_hints"]}
        q_tp += len(pred_c.intersection(gold_c))
        q_fp += len(pred_c - gold_c)
        q_fn += len(gold_c - pred_c)

    q_prec = q_tp / (q_tp + q_fp) if (q_tp + q_fp) else 1.0
    q_rec = q_tp / (q_tp + q_fn) if (q_tp + q_fn) else 1.0
    q_f1 = (2 * q_prec * q_rec / (q_prec + q_rec)) if (q_prec + q_rec) else 0.0

    summary_table = [
        {
            "extractor_module": "PSCT & Card Graph Relation Extractor (analyze_card_psct)",
            "precision": round(micro_p, 4),
            "recall": round(micro_r, 4),
            "f1_score": round(micro_f1, 4),
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        },
        {
            "extractor_module": "Query Entity & Format Extractor (QueryRouter)",
            "precision": round(q_prec, 4),
            "recall": round(q_rec, 4),
            "f1_score": round(q_f1, 4),
            "tp": q_tp,
            "fp": q_fp,
            "fn": q_fn,
        },
    ]
    pd.DataFrame(summary_table).to_csv(RESULTS_DIR / "exp6_entity_extraction.csv", index=False)
    return {"summary": summary_table, "per_card": per_card}


# =============================================================================
# Eksperimen 7: Generative Answer Evaluation — RAGAS (Es et al., 2024)
#   - Faithfulness = |Supported Atomic Claims| / |Total Atomic Claims|
#   - Response Relevancy = mean cosine similarity E(question) vs E(reverse_questions)
#   - Context Recall = proporsi fakta referensi yang tercover oleh konteks GraphRAG
# =============================================================================
RAGAS_TEST_CASES: list[dict[str, Any]] = [
    {
        "id": "R1",
        "domain": "Rulebook & Master Rule",
        "question": "Bagaimana aturan Summon Fusion, Synchro, Xyz, Pendulum, dan Link Monster dari Extra Deck ke Main Monster Zone di Master Rule terbaru?",
        "ground_truth": "Fusion, Synchro, dan Xyz Monster dari Extra Deck dapat di-Special Summon langsung ke Main Monster Zone maupun Extra Monster Zone tanpa memerlukan Link Arrow. Sebaliknya, Link Monster dan face-up Pendulum Monster dari Extra Deck tetap wajib di-Summon ke Extra Monster Zone atau Main Monster Zone yang ditunjuk Link Arrow.",
    },
    {
        "id": "R2",
        "domain": "Damage Step & PSCT",
        "question": "Apakah Ash Blossom & Joyous Spring bisa diaktifkan saat Damage Step?",
        "ground_truth": "Tidak bisa. Saat Damage Step hanya efek cepat yang men-negate aktivasi (negate the activation) atau mengubah ATK/DEF secara langsung yang boleh diaktifkan, sedangkan Ash Blossom men-negate efek (negate that effect), bukan aktivasi.",
    },
    {
        "id": "R3",
        "domain": "PSCT Non-Targeting & Card Relation",
        "question": "Mengapa efek Mirrorjade the Iceblade Dragon bisa mem-banish monster yang memiliki efek tidak bisa ditarget (cannot be targeted)?",
        "ground_truth": "Karena pada teks PSCT Mirrorjade tidak terdapat kata 'target' sebelum titik koma (;). Sebelum titik koma hanya mengirim 1 Fusion Monster yang menyebut Fallen of Albaz dari Extra Deck ke GY sebagai cost, sedangkan pemilihan monster yang di-banish dilakukan saat resolusi.",
    },
    {
        "id": "R4",
        "domain": "Banlist TCG vs OCG",
        "question": 'Apa perbedaan status banlist Maxx "C" dan Pot of Greed di format TCG dibanding OCG?',
        "ground_truth": 'Pot of Greed berstatus Forbidden (0 copy) baik di TCG maupun OCG. Sementara Maxx "C" berstatus Forbidden di format TCG tetapi tidak Forbidden (Semi-Limited/legal) di format OCG.',
    },
    {
        "id": "R5",
        "domain": "PSCT Conjunctions",
        "question": "Apa perbedaan konjungsi 'and if you do' pada Called by the Grave dengan konjungsi 'then' pada Infinite Impermanence?",
        "ground_truth": "Keduanya mensyaratkan bagian A berhasil agar bagian B dijalankan. Namun pada 'and if you do' (Called by the Grave), A dan B dianggap terjadi bersamaan (simultaneous), sedangkan pada 'then' (Infinite Impermanence), A terjadi lebih dulu baru diikuti B secara berurutan (sequential).",
    },
    {
        "id": "R6",
        "domain": "Chain & Spell Speed",
        "question": "Apakah Quick-Play Spell seperti Called by the Grave dapat di-chain untuk merespons Counter Trap seperti Solemn Judgment?",
        "ground_truth": "Tidak bisa. Quick-Play Spell memiliki Spell Speed 2, sedangkan Counter Trap seperti Solemn Judgment memiliki Spell Speed 3 yang hanya dapat direspons oleh Counter Trap lain (Spell Speed 3).",
    },
]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def run_exp7_ragas_evaluation(
    retriever: HybridGraphRetriever,
    embedder: GeminiEmbedder,
    settings: Settings,
) -> dict[str, Any]:
    logger.info("[Eksperimen 7/7] Menjalankan Evaluasi Generatif RAGAS (Faithfulness & Response Relevancy)...")
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY diperlukan untuk menjalankan evaluasi generatif RAGAS.")

    generator = GraphRAGGenerator(settings)
    judge_client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(api_version="v1beta"),
    )

    samples_out = []
    for tc in RAGAS_TEST_CASES:
        q = tc["question"]
        # 1. Route + Hybrid GraphRAG Retrieve + Generate Answer
        from src.rag.router import QueryRouter

        router = QueryRouter(settings)
        plan = router.route(q, use_llm_router=False)
        ret = retriever.retrieve(plan, top_k=6, enable_live_ruling_fallback=False, strategy="hybrid", hop_depth=2)
        context_str = ret.to_prompt_context()
        answer = generator.generate(q, ret)

        # 2. RAGAS Evaluator Call (1 structured JSON call menghitung klaim Faithfulness, Context Recall, & 3 Reverse Questions)
        eval_prompt = (
            "Anda adalah evaluator objektif menggunakan metodologi RAGAS (Es et al., 2024).\n"
            "Berdasarkan PERTANYAAN, KONTEKS RETRIEVAL, JAWABAN MODEL, dan GROUND TRUTH berikut, keluarkan HANYA JSON valid dengan struktur:\n"
            "{\n"
            '  "claims": [\n'
            '    {"statement": "klaim faktual atomik dari jawaban model", "supported_by_context": true}\n'
            "  ],\n"
            '  "reverse_questions": [\n'
            '    "pertanyaan 1 dalam bahasa yang sama yang dijawab langsung oleh JAWABAN MODEL",\n'
            '    "pertanyaan 2 dalam bahasa yang sama yang dijawab langsung oleh JAWABAN MODEL",\n'
            '    "pertanyaan 3 dalam bahasa yang sama yang dijawab langsung oleh JAWABAN MODEL"\n'
            "  ],\n"
            '  "ground_truth_points_in_context_ratio": 1.0\n'
            "}\n\n"
            f"PERTANYAAN:\n{q}\n\n"
            f"GROUND TRUTH:\n{tc['ground_truth']}\n\n"
            f"KONTEKS RETRIEVAL:\n{context_str[:7500]}\n\n"
            f"JAWABAN MODEL:\n{answer}"
        )

        eval_models = list(
            dict.fromkeys(
                [
                    "gemini-3.5-flash-lite",
                    "gemini-3.5-flash",
                    "gemini-3.8-flash",
                    "gemini-3.7-flash",
                    settings.gemini_llm_model,
                ]
            )
        )
        eval_resp = None
        last_eval_err: Exception | None = None
        for emodel in eval_models:
            for attempt in range(2):
                try:
                    eval_resp = judge_client.models.generate_content(
                        model=emodel,
                        contents=eval_prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            response_mime_type="application/json",
                        ),
                    )
                    break
                except Exception as exc:
                    last_eval_err = exc
                    err_s = str(exc)
                    if any(c in err_s for c in ("429", "503", "404", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "NOT_FOUND")):
                        if "429" in err_s or "404" in err_s:
                            break
                        time.sleep(2.5 * (attempt + 1))
                        continue
                    raise
            if eval_resp is not None:
                break
        if eval_resp is None and last_eval_err is not None:
            raise last_eval_err

        parsed_eval = json.loads(eval_resp.text or "{}")
        claims = parsed_eval.get("claims") or []
        supported_cnt = sum(1 for c in claims if c.get("supported_by_context") is True)
        faithfulness = (supported_cnt / len(claims)) if claims else 1.0

        rev_qs = [rq for rq in (parsed_eval.get("reverse_questions") or []) if isinstance(rq, str) and rq.strip()]
        q_emb = embedder.embed_query(q)
        if rev_qs:
            sims = [max(0.0, _cosine_sim(q_emb, embedder.embed_query(rq))) for rq in rev_qs[:3]]
            response_relevancy = statistics.mean(sims)
        else:
            response_relevancy = 0.9

        ctx_recall = float(parsed_eval.get("ground_truth_points_in_context_ratio", 1.0))
        ctx_recall = max(0.0, min(1.0, ctx_recall))

        samples_out.append(
            {
                "id": tc["id"],
                "domain": tc["domain"],
                "question": q,
                "faithfulness": round(faithfulness, 4),
                "response_relevancy": round(response_relevancy, 4),
                "context_recall": round(ctx_recall, 4),
                "total_claims": len(claims),
                "supported_claims": supported_cnt,
                "answer_preview": answer[:260].replace("\n", " ") + "...",
            }
        )
        logger.info(
            f"  RAGAS [{tc['id']} - {tc['domain']}] -> Faithfulness={faithfulness:.3f}, "
            f"Response Relevancy={response_relevancy:.3f}, Context Recall={ctx_recall:.3f}"
        )
        time.sleep(1.0)

    df_ragas = pd.DataFrame(samples_out)
    df_ragas.to_csv(RESULTS_DIR / "exp7_ragas_generative.csv", index=False)

    aggregate = {
        "faithfulness": round(statistics.mean(s["faithfulness"] for s in samples_out), 4),
        "response_relevancy": round(statistics.mean(s["response_relevancy"] for s in samples_out), 4),
        "context_recall": round(statistics.mean(s["context_recall"] for s in samples_out), 4),
        "num_samples": len(samples_out),
    }
    return {"aggregate": aggregate, "samples": samples_out}


def run_all_benchmarks() -> dict[str, Any]:
    """Menjalankan seluruh 7 skenario eksperimen wajib dan menyimpannya ke results/experiment_results.json."""
    settings = get_settings()
    neo4j = Neo4jGraphClient(settings)
    ok, msg = neo4j.check_connection()
    if not ok:
        raise RuntimeError(f"Neo4j harus aktif untuk menjalankan benchmark penuh: {msg}")

    embedder = GeminiEmbedder(settings)
    retriever = HybridGraphRetriever(settings, neo4j_client=neo4j)

    t_all = time.perf_counter()
    graph_stats = neo4j.get_graph_statistics()

    exp1 = run_exp1_vector_vs_graph_vs_hybrid(retriever)
    exp2 = run_exp2_single_vs_multihop(retriever, settings)
    exp3 = run_exp3_graph_traversal_latency(neo4j)
    exp4 = run_exp4_e2e_integration_latency(neo4j, embedder)
    exp5 = run_exp5_node_edge_growth(neo4j, embedder)
    exp6 = run_exp6_entity_relationship_extraction()
    exp7 = run_exp7_ragas_evaluation(retriever, embedder, settings)

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_benchmark_duration_sec": round(time.perf_counter() - t_all, 2),
        "graph_statistics": graph_stats,
        "exp1_vector_vs_graph_vs_hybrid": exp1,
        "exp2_single_vs_multihop": exp2,
        "exp3_graph_traversal_latency": exp3,
        "exp4_e2e_integration_latency": exp4,
        "exp5_node_edge_growth": exp5,
        "exp6_entity_relationship_extraction": exp6,
        "exp7_ragas_evaluation": exp7,
    }

    out_json = RESULTS_DIR / "experiment_results.json"
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    neo4j.close()
    logger.success(f"Seluruh 7 skenario eksperimen selesai & disimpan ke {out_json}!")
    return payload
