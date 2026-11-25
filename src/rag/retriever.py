"""Hybrid GraphRAG Retriever: Vector Search + Fulltext BM25 + Multi-Hop Cypher Traversal."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from src.config import Settings, get_settings
from src.graph.embedder import GeminiEmbedder
from src.graph.neo4j_client import Neo4jGraphClient
from src.ingestion.fetch_psct_rulings import fetch_single_card_rulings_live
from src.rag.router import QueryPlan


def sanitize_lucene_query(text: str) -> str:
    """Membersihkan karakter khusus Lucene agar db.index.fulltext.queryNodes tidak error."""
    cleaned = re.sub(r'[+\-&|!(){}\[\]^"~*?:\\/]', " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Batasi maks 12 kata kunci penting
    tokens = [t for t in cleaned.split(" ") if len(t) >= 2][:12]
    return " OR ".join(tokens) if tokens else "YuGiOh"


@dataclass
class RetrievalResult:
    """Hasil gabungan konteks dari Neo4j Hybrid GraphRAG (atau fallback lokal)."""

    mode: str
    plan: QueryPlan
    cards: list[dict[str, Any]] = field(default_factory=list)
    banlist_records: list[dict[str, Any]] = field(default_factory=list)
    psct_rules: list[dict[str, Any]] = field(default_factory=list)
    rulings: list[dict[str, Any]] = field(default_factory=list)
    rulebook_chunks: list[dict[str, Any]] = field(default_factory=list)
    graph_paths: list[str] = field(default_factory=list)
    cypher_traces: list[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Menyusun konteks terstruktur dari keempat dokumen & relasi graf untuk LLM Judge."""
        sections: list[str] = []

        if self.graph_paths:
            paths_str = "\n".join(f"- {p}" for p in self.graph_paths[:25])
            sections.append(f"=== KNOWLEDGE GRAPH MULTI-HOP RELATIONS ===\n{paths_str}")

        if self.cards:
            card_lines = []
            for c in self.cards[:10]:
                stats = []
                if c.get("attribute"):
                    stats.append(f"Attr: {c['attribute']}")
                if c.get("race"):
                    stats.append(f"Type/Race: {c['race']}")
                if c.get("level") is not None:
                    stats.append(f"Lv/Rank: {c['level']}")
                if c.get("linkval") is not None:
                    stats.append(f"Link-{c['linkval']}")
                if c.get("atk") is not None:
                    stats.append(f"ATK/DEF: {c['atk']}/{c.get('def')}")
                if c.get("archetype"):
                    stats.append(f"Archetype: {c['archetype']}")
                stats.append(
                    f"Banlist [TCG: {c.get('ban_tcg', 'Unlimited')} | OCG: {c.get('ban_ocg', 'Unlimited')}]"
                )
                psct_flags = (
                    f"Spell Speed {c.get('spell_speed', 1)}, "
                    f"Targets: {c.get('has_targeting', False)}, "
                    f"Has Cost (;): {c.get('has_cost', False)}, "
                    f"Conjunctions: {c.get('conjunctions', [])}"
                )
                card_lines.append(
                    f"[Card: {c['name']}] ({c.get('type', '')} | {' | '.join(stats)})\n"
                    f"  PSCT Grammar Analysis: {psct_flags}\n"
                    f"  Official Text: {c.get('desc', '')}"
                )
            sections.append("=== DOKUMEN 2: INFORMASI KARTU ===\n" + "\n\n".join(card_lines))

        if self.banlist_records:
            ban_lines = [
                f"- {b['card_name']} ({b.get('card_type', '')}, Archetype: {b.get('archetype') or '-'}) "
                f"-> {b['format']}: {b['status']} (Maks {b['max_copies']} copy)"
                for b in self.banlist_records[:35]
            ]
            sections.append("=== DOKUMEN 4: DAFTAR KARTU BANNED / LIMITED ===\n" + "\n".join(ban_lines))

        if self.psct_rules:
            psct_lines = [
                f"[{p['name']}] Pattern: `{p.get('pattern', '')}`\n  Explanation: {p['explanation']}"
                for p in self.psct_rules[:8]
            ]
            sections.append("=== DOKUMEN 3A: ATURAN PSCT (PROBLEM-SOLVING CARD TEXT) ===\n" + "\n\n".join(psct_lines))

        if self.rulings:
            ruling_lines = []
            for r in self.rulings[:10]:
                if "question" in r and r.get("question"):
                    ruling_lines.append(
                        f"[Official Ruling {r['id']} | {r.get('source_url', '')}]\n"
                        f"  Q: {r['question']}\n"
                        f"  A: {r['answer']}"
                    )
                elif r.get("text"):
                    ruling_lines.append(
                        f"[Official Card FAQ {r['id']} | {r.get('source_url', '')}]\n  {r['text']}"
                    )
            sections.append("=== DOKUMEN 3B: OFFICIAL CARD RULINGS & FAQ ===\n" + "\n\n".join(ruling_lines))

        if self.rulebook_chunks:
            rb_lines = [
                f"[{rb.get('source', 'Rulebook')} — {rb.get('section_title', '')}]\n  {rb['text']}"
                for rb in self.rulebook_chunks[:6]
            ]
            sections.append("=== DOKUMEN 1: OFFICIAL RULEBOOK & MASTER RULE UPDATE ===\n" + "\n\n".join(rb_lines))

        return "\n\n".join(sections) if sections else "Tidak ditemukan konteks spesifik di database."


class HybridGraphRetriever:
    """Mesin pencari Hybrid GraphRAG di atas Neo4j (Vector + Fulltext BM25 + Multi-hop Cypher)."""

    def __init__(
        self,
        settings: Settings | None = None,
        neo4j_client: Neo4jGraphClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.neo4j = neo4j_client or Neo4jGraphClient(self.settings)
        self._embedder: GeminiEmbedder | None = None
        self._local_cache: dict[str, Any] | None = None

    def _get_embedder(self) -> GeminiEmbedder | None:
        if self._embedder is None and (
            self.settings.embedding_provider == "fastembed" or self.settings.gemini_api_key
        ):
            try:
                self._embedder = GeminiEmbedder(self.settings)
            except Exception as exc:
                logger.warning(f"Embedder tidak aktif: {exc}")
        return self._embedder

    def retrieve(
        self,
        plan: QueryPlan,
        top_k: int = 6,
        enable_live_ruling_fallback: bool = True,
        strategy: str = "hybrid",
        hop_depth: int = 2,
    ) -> RetrievalResult:
        """Menjalankan pengambilan konteks dengan strategi 'vector', 'graph', atau 'hybrid'."""
        strategy = (strategy or "hybrid").lower().strip()
        use_vector = strategy in ("vector", "hybrid")
        use_graph = strategy in ("graph", "hybrid")

        ok, _ = self.neo4j.check_connection()
        if not ok:
            logger.warning("Neo4j belum aktif — beralih otomatis ke Local Processed Graph Fallback.")
            return self._retrieve_local_fallback(plan, top_k=top_k)

        mode_label = {
            "vector": "Neo4j Vector-Only RAG",
            "graph": f"Neo4j Graph-Only ({hop_depth}-Hop Cypher)",
            "hybrid": f"Neo4j Hybrid GraphRAG (Vector + {hop_depth}-Hop Graph)",
        }.get(strategy, "Neo4j Hybrid GraphRAG")

        res = RetrievalResult(mode=mode_label, plan=plan)
        lucene_q = sanitize_lucene_query(
            " ".join([plan.english_search_query] + plan.card_names + plan.archetypes)
        )

        # Hitung vektor query (hanya bila strategi menggunakan vektor)
        query_vec: list[float] | None = None
        if use_vector:
            embedder = self._get_embedder()
            if embedder is not None:
                try:
                    query_vec = embedder.embed_query(plan.english_search_query)
                except Exception as exc:
                    logger.warning(f"Gagal menghitung query embedding: {exc}")

        cards_by_id: dict[int, dict[str, Any]] = {}
        psct_by_id: dict[str, dict[str, Any]] = {}
        rulings_by_id: dict[str, dict[str, Any]] = {}
        rb_by_id: dict[str, dict[str, Any]] = {}

        # ---------------------------------------------------------------------
        # 1. Exact / Partial Card Lookup & Fulltext (untuk mode Graph / Hybrid)
        # ---------------------------------------------------------------------
        if use_graph and plan.card_names:
            res.cypher_traces.append("Cypher Exact/Fuzzy Card Match pada (:Card)")
            rows = self.neo4j.run_query(
                """
                UNWIND $names AS target
                MATCH (c:Card)
                WHERE toLower(c.name) = toLower(target)
                   OR toLower(c.name) CONTAINS toLower(target)
                RETURN c
                ORDER BY CASE WHEN toLower(c.name) = toLower(target) THEN 0 ELSE 1 END,
                         coalesce(c.views, 0) DESC
                LIMIT 8
                """,
                {"names": plan.card_names},
            )
            for r in rows:
                cnode = dict(r["c"])
                cnode.pop("embedding", None)
                cards_by_id[int(cnode["id"])] = cnode

        if use_graph and len(cards_by_id) < top_k:
            res.cypher_traces.append("Fulltext BM25 Index `card_fulltext`")
            ft_cards = self.neo4j.run_query(
                """
                CALL db.index.fulltext.queryNodes('card_fulltext', $q, {limit: $k})
                YIELD node, score
                RETURN node AS c, score
                """,
                {"q": lucene_q, "k": top_k},
            )
            for r in ft_cards:
                cnode = dict(r["c"])
                cnode.pop("embedding", None)
                cards_by_id.setdefault(int(cnode["id"]), cnode)

        if use_vector and query_vec is not None:
            try:
                res.cypher_traces.append("Vector Cosine Index `card_vector_idx`")
                vec_cards = self.neo4j.run_query(
                    """
                    CALL db.index.vector.queryNodes('card_vector_idx', $k, $vec)
                    YIELD node, score
                    RETURN node AS c, score
                    """,
                    {"k": top_k, "vec": query_vec},
                )
                for r in vec_cards:
                    cnode = dict(r["c"])
                    cnode.pop("embedding", None)
                    cards_by_id.setdefault(int(cnode["id"]), cnode)
            except Exception as exc:
                logger.debug(f"Vector card query info: {exc}")

        # ---------------------------------------------------------------------
        # 2. Multi-Hop Knowledge Graph Expansion (hanya aktif pada Graph & Hybrid!)
        # ---------------------------------------------------------------------
        seed_card_ids = list(cards_by_id.keys())[:8]
        if use_graph and seed_card_ids:
            res.cypher_traces.append(
                f"Graph Traversal ({hop_depth}-Hop): (:Card)-[:HAS_PSCT_PATTERN|RULES_ON|BANNED_IN|MENTIONS_CARD]-(...)"
            )
            hop_rows = self.neo4j.run_query(
                """
                MATCH (c:Card) WHERE c.id IN $cids
                OPTIONAL MATCH (c)-[:HAS_PSCT_PATTERN]->(p:PSCTRule)
                OPTIONAL MATCH (c)<-[:RULES_ON]-(ru:Ruling)
                OPTIONAL MATCH (c)-[b:BANNED_IN]->(fmt:Format)
                OPTIONAL MATCH (c)-[:MENTIONS_CARD]-(mc:Card)
                RETURN c.name AS card_name,
                       c.konami_id AS konami_id,
                       collect(DISTINCT p)[0..6] AS pscts,
                       collect(DISTINCT ru)[0..6] AS rulings,
                       collect(DISTINCT {format: fmt.name, status: b.status, max_copies: b.max_copies}) AS bans,
                       collect(DISTINCT mc)[0..5] AS mentioned_cards
                """,
                {"cids": seed_card_ids},
            )
            for row in hop_rows:
                cname = row["card_name"]
                for p in row.get("pscts") or []:
                    if p:
                        pd = dict(p)
                        pd.pop("embedding", None)
                        psct_by_id[pd["id"]] = pd
                        res.graph_paths.append(f"({cname}) -[:HAS_PSCT_PATTERN]-> ({pd['name']})")
                for ru in row.get("rulings") or []:
                    if ru:
                        rud = dict(ru)
                        rud.pop("embedding", None)
                        rulings_by_id[rud["id"]] = rud
                        res.graph_paths.append(f"({rud['id']}) -[:RULES_ON]-> ({cname})")
                for b in row.get("bans") or []:
                    if b and b.get("format"):
                        res.graph_paths.append(
                            f"({cname}) -[:BANNED_IN {{status: '{b['status']}', max: {b['max_copies']}}}]-> ({b['format']})"
                        )
                for mc in row.get("mentioned_cards") or []:
                    if mc:
                        mcd = dict(mc)
                        mcd.pop("embedding", None)
                        res.graph_paths.append(f"({cname}) -[:MENTIONS_CARD]- ({mcd.get('name', '')})")
                        if hop_depth >= 2 and "id" in mcd:
                            cards_by_id.setdefault(int(mcd["id"]), mcd)

                if (
                    enable_live_ruling_fallback
                    and "ruling_psct" in plan.intents
                    and row.get("konami_id")
                    and not row.get("rulings")
                ):
                    live = fetch_single_card_rulings_live(
                        int(row["konami_id"]),
                        id_to_name={int(row["konami_id"]): cname},
                        max_qas=5,
                    )
                    if live.get("faq"):
                        rulings_by_id[live["faq"]["id"]] = live["faq"]
                        res.graph_paths.append(f"({cname}) -[:LIVE_FAQ_LOOKUP]-> ({live['faq']['id']})")
                    for lqa in live.get("rulings") or []:
                        rulings_by_id[lqa["id"]] = lqa
                        res.graph_paths.append(f"({lqa['id']}) -[:LIVE_RULING_ON]-> ({cname})")

            # Hop ke-2: (:Card)-[:USES_MECHANIC]->(:GameConcept)<-[:EXPLAINS_CONCEPT]-(:RuleChunk)
            if hop_depth >= 2:
                concept_rb = self.neo4j.run_query(
                    """
                    MATCH (c:Card)-[:USES_MECHANIC]->(g:GameConcept)<-[:EXPLAINS_CONCEPT]-(rc:RuleChunk)
                    WHERE c.id IN $cids
                    RETURN DISTINCT g.name AS concept, rc
                    LIMIT 5
                    """,
                    {"cids": seed_card_ids[:4]},
                )
                for r in concept_rb:
                    rcd = dict(r["rc"])
                    rcd.pop("embedding", None)
                    rb_by_id[rcd["id"]] = rcd
                    res.graph_paths.append(
                        f"(:Card) -[:USES_MECHANIC]-> ({r['concept']}) <-[:EXPLAINS_CONCEPT]- ({rcd['section_title']})"
                    )

        # ---------------------------------------------------------------------
        # 3. Kueri Khusus Dokumen 4: Banlist Graph Traversal
        # ---------------------------------------------------------------------
        if use_graph and ("banlist" in plan.intents or plan.archetypes or plan.ban_status_filter):
            res.cypher_traces.append("Cypher Traversal (:Card)-[:BANNED_IN]->(:Format)")
            ban_cypher = """
            MATCH (c:Card)-[b:BANNED_IN]->(f:Format)
            WHERE ($formats = [] OR f.name IN $formats)
              AND ($status IS NULL OR b.status = $status)
              AND ($archetypes = [] OR any(a IN $archetypes WHERE toLower(c.archetype) CONTAINS toLower(a) OR toLower(c.name) CONTAINS toLower(a)))
            RETURN c.id AS card_id, c.name AS card_name, c.type AS card_type,
                   c.archetype AS archetype, f.name AS format,
                   b.status AS status, b.max_copies AS max_copies, coalesce(c.views, 0) AS views
            ORDER BY b.max_copies ASC, views DESC
            LIMIT 35
            """
            res.banlist_records = self.neo4j.run_query(
                ban_cypher,
                {
                    "formats": plan.formats,
                    "status": plan.ban_status_filter,
                    "archetypes": plan.archetypes,
                },
            )

        # ---------------------------------------------------------------------
        # 4. Pencarian Vektor & Fulltext untuk Rulebook, PSCT, dan Rulings
        # ---------------------------------------------------------------------
        if use_vector and query_vec is not None:
            for idx_name, target_dict in (
                ("rulebook_vector_idx", rb_by_id),
                ("psct_vector_idx", psct_by_id),
                ("ruling_vector_idx", rulings_by_id),
            ):
                try:
                    vrows = self.neo4j.run_query(
                        f"CALL db.index.vector.queryNodes('{idx_name}', $k, $vec) YIELD node, score RETURN node, score",
                        {"k": top_k, "vec": query_vec},
                    )
                    for r in vrows:
                        nd = dict(r["node"])
                        nd.pop("embedding", None)
                        target_dict.setdefault(nd["id"], nd)
                except Exception:
                    pass

        if use_graph:
            for ft_idx, target_dict in (
                ("rulebook_fulltext", rb_by_id),
                ("psct_fulltext", psct_by_id),
                ("ruling_fulltext", rulings_by_id),
            ):
                try:
                    frows = self.neo4j.run_query(
                        f"CALL db.index.fulltext.queryNodes('{ft_idx}', $q, {{limit: 4}}) YIELD node, score RETURN node",
                        {"q": lucene_q},
                    )
                    for r in frows:
                        nd = dict(r["node"])
                        nd.pop("embedding", None)
                        target_dict.setdefault(nd["id"], nd)
                except Exception:
                    pass

            if hop_depth >= 2 and any(
                kw in plan.english_search_query.lower()
                for kw in ("extra deck", "extra monster zone", "main monster zone", "master rule", "link arrow", "synchro", "xyz", "fusion", "pendulum")
            ):
                mr_rows = self.neo4j.run_query(
                    "MATCH (rc:RuleChunk {id: 'rule_mr2020_extra_deck_zones'}) RETURN rc"
                )
                for r in mr_rows:
                    nd = dict(r["rc"])
                    nd.pop("embedding", None)
                    rb_by_id[nd["id"]] = nd

        res.cards = list(cards_by_id.values())[:max(top_k, 8)]
        res.psct_rules = list(psct_by_id.values())[:8]
        res.rulings = list(rulings_by_id.values())[:10]
        res.rulebook_chunks = list(rb_by_id.values())[:6]
        return res

    # -------------------------------------------------------------------------
    # Fallback Lokal (jika Docker Neo4j belum dinyalakan saat demo berlangsung)
    # -------------------------------------------------------------------------
    def _load_local_data(self) -> dict[str, Any]:
        if self._local_cache is not None:
            return self._local_cache
        data: dict[str, Any] = {"cards": [], "banlist": [], "rulebook": [], "psct": [], "rulings": []}
        if self.settings.cards_processed_path.exists():
            data["cards"] = json.loads(self.settings.cards_processed_path.read_text(encoding="utf-8"))
        if self.settings.banlist_processed_path.exists():
            data["banlist"] = json.loads(self.settings.banlist_processed_path.read_text(encoding="utf-8"))
        if self.settings.rulebook_chunks_path.exists():
            data["rulebook"] = json.loads(self.settings.rulebook_chunks_path.read_text(encoding="utf-8"))
        if self.settings.psct_rules_path.exists():
            data["psct"] = json.loads(self.settings.psct_rules_path.read_text(encoding="utf-8"))
        if self.settings.rulings_processed_path.exists():
            rb = json.loads(self.settings.rulings_processed_path.read_text(encoding="utf-8"))
            data["rulings"] = (rb.get("faqs") or []) + (rb.get("rulings") or [])
        self._local_cache = data
        return data

    def _retrieve_local_fallback(self, plan: QueryPlan, top_k: int = 6) -> RetrievalResult:
        store = self._load_local_data()
        res = RetrievalResult(mode="Local Graph Fallback (Neo4j Offline)", plan=plan)
        terms = [
            t.lower()
            for t in re.findall(r"[a-zA-Z0-9']+", plan.english_search_query)
            if len(t) >= 3
        ]

        def _score_text(txt: str) -> int:
            low = txt.lower()
            return sum(2 if t in low else 0 for t in terms)

        # Match cards
        matched_cards: list[tuple[int, dict[str, Any]]] = []
        target_lower = [n.lower() for n in plan.card_names]
        for c in store["cards"]:
            cname_low = c["name"].lower()
            bonus = 50 if cname_low in target_lower else (25 if any(tl in cname_low for tl in target_lower) else 0)
            sc = bonus + _score_text(f"{c['name']} {c.get('archetype', '')} {c.get('desc', '')}")
            if sc > 0:
                matched_cards.append((sc, c))
        matched_cards.sort(key=lambda x: (x[0], x[1].get("views", 0)), reverse=True)
        res.cards = [
            {
                **c,
                "spell_speed": c.get("psct", {}).get("spell_speed", 1),
                "has_targeting": c.get("psct", {}).get("has_targeting", False),
                "has_cost": c.get("psct", {}).get("has_cost", False),
                "conjunctions": c.get("psct", {}).get("conjunctions", []),
            }
            for _, c in matched_cards[:top_k]
        ]

        psct_map = {p["id"]: p for p in store["psct"]}
        chosen_psct: dict[str, dict[str, Any]] = {}
        for c in res.cards[:4]:
            for pid in c.get("psct", {}).get("psct_rule_ids", []):
                if pid in psct_map:
                    chosen_psct[pid] = psct_map[pid]
                    res.graph_paths.append(f"({c['name']}) -[:HAS_PSCT_PATTERN]-> ({psct_map[pid]['name']})")

        for p in store["psct"]:
            if _score_text(f"{p['name']} {p['explanation']}") >= 4:
                chosen_psct.setdefault(p["id"], p)
        res.psct_rules = list(chosen_psct.values())[:6]

        if "banlist" in plan.intents or plan.ban_status_filter or plan.archetypes:
            bans = []
            for b in store["banlist"]:
                if plan.formats and b["format"] not in plan.formats:
                    continue
                if plan.ban_status_filter and b["status"] != plan.ban_status_filter:
                    continue
                if plan.archetypes and not any(
                    a.lower() in (b.get("archetype") or "").lower() or a.lower() in b["card_name"].lower()
                    for a in plan.archetypes
                ):
                    continue
                bans.append(b)
            res.banlist_records = bans[:30]

        scored_rulings = [
            (_score_text(f"{r.get('card_name', '')} {' '.join(r.get('card_names', []))} {r.get('question', '')} {r.get('answer', '')} {r.get('text', '')}"), r)
            for r in store["rulings"]
        ]
        scored_rulings = [x for x in scored_rulings if x[0] > 0]
        scored_rulings.sort(key=lambda x: x[0], reverse=True)
        res.rulings = [r for _, r in scored_rulings[:8]]

        scored_rb = [(_score_text(f"{rb['section_title']} {rb['text']}"), rb) for rb in store["rulebook"]]
        scored_rb = [x for x in scored_rb if x[0] > 0]
        scored_rb.sort(key=lambda x: x[0], reverse=True)
        res.rulebook_chunks = [rb for _, rb in scored_rb[:5]]

        return res
