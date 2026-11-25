"""Skema Knowledge Graph Neo4j, pembuatan Vector/Fulltext Index, dan Ingesti Batch 4 Dokumen."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.config import Settings, get_settings
from src.graph.embedder import GeminiEmbedder
from src.graph.neo4j_client import Neo4jGraphClient


def setup_neo4j_schema(client: Neo4jGraphClient, embedding_dim: int = 768) -> None:
    """Membuat Unique Constraints, Fulltext BM25 Indexes, dan Vector Cosine Indexes di Neo4j 5+."""
    constraints = [
        "CREATE CONSTRAINT card_id_unique IF NOT EXISTS FOR (c:Card) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT card_name_idx IF NOT EXISTS FOR (c:Card) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT archetype_name_unique IF NOT EXISTS FOR (a:Archetype) REQUIRE a.name IS UNIQUE",
        "CREATE CONSTRAINT attribute_name_unique IF NOT EXISTS FOR (at:Attribute) REQUIRE at.name IS UNIQUE",
        "CREATE CONSTRAINT race_name_unique IF NOT EXISTS FOR (r:MonsterRace) REQUIRE r.name IS UNIQUE",
        "CREATE CONSTRAINT cardtype_name_unique IF NOT EXISTS FOR (ct:CardType) REQUIRE ct.name IS UNIQUE",
        "CREATE CONSTRAINT format_name_unique IF NOT EXISTS FOR (f:Format) REQUIRE f.name IS UNIQUE",
        "CREATE CONSTRAINT banstatus_unique IF NOT EXISTS FOR (b:BanStatus) REQUIRE b.status IS UNIQUE",
        "CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (g:GameConcept) REQUIRE g.name IS UNIQUE",
        "CREATE CONSTRAINT rulesection_title_unique IF NOT EXISTS FOR (s:RuleSection) REQUIRE s.title IS UNIQUE",
        "CREATE CONSTRAINT rulechunk_id_unique IF NOT EXISTS FOR (rc:RuleChunk) REQUIRE rc.id IS UNIQUE",
        "CREATE CONSTRAINT psctrule_id_unique IF NOT EXISTS FOR (p:PSCTRule) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT ruling_id_unique IF NOT EXISTS FOR (ru:Ruling) REQUIRE ru.id IS UNIQUE",
        "CREATE CONSTRAINT cardfaq_id_unique IF NOT EXISTS FOR (fq:CardFAQ) REQUIRE fq.id IS UNIQUE",
    ]

    regular_indexes = [
        "CREATE INDEX card_konami_id_idx IF NOT EXISTS FOR (c:Card) ON (c.konami_id)",
        "CREATE INDEX card_ban_tcg_idx IF NOT EXISTS FOR (c:Card) ON (c.ban_tcg)",
        "CREATE INDEX card_ban_ocg_idx IF NOT EXISTS FOR (c:Card) ON (c.ban_ocg)",
    ]

    fulltext_indexes = [
        """
        CREATE FULLTEXT INDEX card_fulltext IF NOT EXISTS
        FOR (c:Card) ON EACH [c.name, c.desc, c.archetype, c.type, c.race]
        """,
        """
        CREATE FULLTEXT INDEX rulebook_fulltext IF NOT EXISTS
        FOR (rc:RuleChunk) ON EACH [rc.section_title, rc.text, rc.category]
        """,
        """
        CREATE FULLTEXT INDEX psct_fulltext IF NOT EXISTS
        FOR (p:PSCTRule) ON EACH [p.name, p.pattern, p.explanation]
        """,
        """
        CREATE FULLTEXT INDEX ruling_fulltext IF NOT EXISTS
        FOR (ru:Ruling|CardFAQ) ON EACH [ru.title, ru.question, ru.answer, ru.text, ru.card_name]
        """,
    ]

    vector_indexes = [
        f"""
        CREATE VECTOR INDEX card_vector_idx IF NOT EXISTS
        FOR (c:Card) ON (c.embedding)
        OPTIONS {{indexConfig: {{`vector.dimensions`: {embedding_dim}, `vector.similarity_function`: 'cosine'}}}}
        """,
        f"""
        CREATE VECTOR INDEX rulebook_vector_idx IF NOT EXISTS
        FOR (rc:RuleChunk) ON (rc.embedding)
        OPTIONS {{indexConfig: {{`vector.dimensions`: {embedding_dim}, `vector.similarity_function`: 'cosine'}}}}
        """,
        f"""
        CREATE VECTOR INDEX psct_vector_idx IF NOT EXISTS
        FOR (p:PSCTRule) ON (p.embedding)
        OPTIONS {{indexConfig: {{`vector.dimensions`: {embedding_dim}, `vector.similarity_function`: 'cosine'}}}}
        """,
        f"""
        CREATE VECTOR INDEX ruling_vector_idx IF NOT EXISTS
        FOR (ru:Ruling) ON (ru.embedding)
        OPTIONS {{indexConfig: {{`vector.dimensions`: {embedding_dim}, `vector.similarity_function`: 'cosine'}}}}
        """,
        f"""
        CREATE VECTOR INDEX faq_vector_idx IF NOT EXISTS
        FOR (fq:CardFAQ) ON (fq.embedding)
        OPTIONS {{indexConfig: {{`vector.dimensions`: {embedding_dim}, `vector.similarity_function`: 'cosine'}}}}
        """,
    ]

    logger.info("Menyiapkan Constraints, Fulltext Indexes, dan Vector Indexes di Neo4j...")
    for stmt in constraints + regular_indexes + fulltext_indexes + vector_indexes:
        client.run_query(stmt)
    logger.success("Skema Neo4j siap!")


def ingest_rulebook_to_neo4j(client: Neo4jGraphClient, rule_chunks: list[dict[str, Any]]) -> None:
    """Ingesti Dokumen 1: Official Rulebook v10 + Master Rule 2020/2021 Updates."""
    logger.info(f"Mengingesti {len(rule_chunks)} chunk Rulebook ke Neo4j...")
    cypher = """
    UNWIND $batch AS row
    MERGE (sec:RuleSection {title: row.section_title})
      ON CREATE SET sec.category = row.category
    MERGE (ch:RuleChunk {id: row.id})
    SET ch.section_title = row.section_title,
        ch.category = row.category,
        ch.page = row.page,
        ch.source = row.source,
        ch.text = row.text
    MERGE (sec)-[:HAS_CHUNK]->(ch)
    WITH ch, row
    UNWIND row.concepts AS concept_name
    MERGE (gc:GameConcept {name: concept_name})
    MERGE (ch)-[:EXPLAINS_CONCEPT]->(gc)
    """
    client.run_batch_write(cypher, rule_chunks, batch_size=200)


def ingest_psct_rules_to_neo4j(client: Neo4jGraphClient, psct_rules: list[dict[str, Any]]) -> None:
    """Ingesti Dokumen 3A: Aturan Tata Bahasa Problem-Solving Card Text (PSCT)."""
    logger.info(f"Mengingesti {len(psct_rules)} aturan PSCT ke Neo4j...")
    cypher = """
    UNWIND $batch AS row
    MERGE (p:PSCTRule {id: row.id})
    SET p.name = row.name,
        p.pattern = row.pattern,
        p.category = row.category,
        p.simultaneous = row.simultaneous,
        p.part_a_required_for_b = row.part_a_required_for_b,
        p.explanation = row.explanation
    """
    client.run_batch_write(cypher, psct_rules, batch_size=100)


def ingest_cards_and_banlist_to_neo4j(
    client: Neo4jGraphClient,
    cards_enriched: list[dict[str, Any]],
    banlist_entries: list[dict[str, Any]],
) -> None:
    """Ingesti Dokumen 2 (~14.000+ Kartu + Relasi Mekanik/PSCT/Referensi) & Dokumen 4 (Banlist)."""
    # 1. Buat Format & BanStatus dasar
    formats = [
        {"name": "TCG", "description": "Yu-Gi-Oh! Trading Card Game (International / Western Format)"},
        {"name": "OCG", "description": "Yu-Gi-Oh! Official Card Game (Japan & Asian Format)"},
        {"name": "Goat", "description": "Classic 2005 Goat Control Historical Format"},
    ]
    statuses = [
        {"status": "Forbidden", "max_copies": 0, "description": "Banned — 0 copies allowed in Main/Extra/Side Deck"},
        {"status": "Limited", "max_copies": 1, "description": "Maximum 1 copy allowed in Deck"},
        {"status": "Semi-Limited", "max_copies": 2, "description": "Maximum 2 copies allowed in Deck"},
        {"status": "Unlimited", "max_copies": 3, "description": "Up to 3 copies allowed in Deck"},
    ]
    client.run_batch_write(
        "UNWIND $batch AS r MERGE (f:Format {name: r.name}) SET f.description = r.description",
        formats,
    )
    client.run_batch_write(
        "UNWIND $batch AS r MERGE (b:BanStatus {status: r.status}) SET b.max_copies = r.max_copies, b.description = r.description",
        statuses,
    )

    # 2. Ingesti Node (:Card) dan taksonomi utamanya
    logger.info(f"Mengingesti {len(cards_enriched):,} node Kartu & taksonomi ke Neo4j...")
    card_nodes_payload = []
    psct_links = []
    concept_links = []
    card_mentions = []
    arch_mentions = []

    for c in cards_enriched:
        psct = c.get("psct") or {}
        card_nodes_payload.append(
            {
                "id": c["id"],
                "konami_id": c.get("konami_id"),
                "name": c["name"],
                "type": c.get("type", ""),
                "frameType": c.get("frameType", ""),
                "desc": c.get("desc", ""),
                "atk": c.get("atk"),
                "def": c.get("def"),
                "level": c.get("level"),
                "scale": c.get("scale"),
                "linkval": c.get("linkval"),
                "race": c.get("race", ""),
                "attribute": c.get("attribute", ""),
                "archetype": c.get("archetype", ""),
                "tcg_date": c.get("tcg_date", ""),
                "ocg_date": c.get("ocg_date", ""),
                "views": c.get("views", 0),
                "image_url": c.get("image_url", ""),
                "ban_tcg": c.get("ban_tcg", "Unlimited"),
                "ban_ocg": c.get("ban_ocg", "Unlimited"),
                "ban_goat": c.get("ban_goat", "Unlimited"),
                "spell_speed": psct.get("spell_speed", 1),
                "has_targeting": psct.get("has_targeting", False),
                "has_cost": psct.get("has_cost", False),
                "has_activated_effect": psct.get("has_activated_effect", False),
                "conjunctions": psct.get("conjunctions", []),
            }
        )
        for pid in psct.get("psct_rule_ids", []):
            psct_links.append({"card_id": c["id"], "psct_id": pid})
        for cname in psct.get("concepts", []):
            concept_links.append({"card_id": c["id"], "concept": cname})
        for target_card in psct.get("mentioned_cards", []):
            card_mentions.append({"card_id": c["id"], "target_name": target_card})
        for target_arch in psct.get("mentioned_archetypes", []):
            arch_mentions.append({"card_id": c["id"], "archetype": target_arch})

    cypher_cards = """
    UNWIND $batch AS row
    MERGE (c:Card {id: row.id})
    SET c.konami_id = row.konami_id,
        c.name = row.name,
        c.type = row.type,
        c.frameType = row.frameType,
        c.desc = row.desc,
        c.atk = row.atk,
        c.def = row.def,
        c.level = row.level,
        c.scale = row.scale,
        c.linkval = row.linkval,
        c.race = row.race,
        c.attribute = row.attribute,
        c.archetype = row.archetype,
        c.tcg_date = row.tcg_date,
        c.ocg_date = row.ocg_date,
        c.views = row.views,
        c.image_url = row.image_url,
        c.ban_tcg = row.ban_tcg,
        c.ban_ocg = row.ban_ocg,
        c.ban_goat = row.ban_goat,
        c.spell_speed = row.spell_speed,
        c.has_targeting = row.has_targeting,
        c.has_cost = row.has_cost,
        c.has_activated_effect = row.has_activated_effect,
        c.conjunctions = row.conjunctions
    FOREACH (_ IN CASE WHEN row.archetype <> '' THEN [1] ELSE [] END |
        MERGE (a:Archetype {name: row.archetype})
        MERGE (c)-[:BELONGS_TO_ARCHETYPE]->(a)
    )
    FOREACH (_ IN CASE WHEN row.attribute <> '' THEN [1] ELSE [] END |
        MERGE (at:Attribute {name: row.attribute})
        MERGE (c)-[:HAS_ATTRIBUTE]->(at)
    )
    FOREACH (_ IN CASE WHEN row.race <> '' THEN [1] ELSE [] END |
        MERGE (mr:MonsterRace {name: row.race})
        MERGE (c)-[:HAS_RACE]->(mr)
    )
    FOREACH (_ IN CASE WHEN row.type <> '' THEN [1] ELSE [] END |
        MERGE (ct:CardType {name: row.type})
        MERGE (c)-[:IS_CARD_TYPE]->(ct)
    )
    """
    client.run_batch_write(cypher_cards, card_nodes_payload, batch_size=800)

    # 3. Relasi PSCT Pattern, Game Concepts, dan Referensi Antar-Kartu
    logger.info(
        f"Menghubungkan relasi PSCT ({len(psct_links):,}), Konsep Mekanik ({len(concept_links):,}), "
        f"dan Referensi Kartu ({len(card_mentions):,})..."
    )
    client.run_batch_write(
        """
        UNWIND $batch AS r
        MATCH (c:Card {id: r.card_id})
        MATCH (p:PSCTRule {id: r.psct_id})
        MERGE (c)-[:HAS_PSCT_PATTERN]->(p)
        """,
        psct_links,
        batch_size=1200,
    )
    client.run_batch_write(
        """
        UNWIND $batch AS r
        MATCH (c:Card {id: r.card_id})
        MERGE (g:GameConcept {name: r.concept})
        MERGE (c)-[:USES_MECHANIC]->(g)
        """,
        concept_links,
        batch_size=1200,
    )
    client.run_batch_write(
        """
        UNWIND $batch AS r
        MATCH (src:Card {id: r.card_id})
        MATCH (dst:Card {name: r.target_name})
        MERGE (src)-[:MENTIONS_CARD]->(dst)
        """,
        card_mentions,
        batch_size=1000,
    )
    client.run_batch_write(
        """
        UNWIND $batch AS r
        MATCH (src:Card {id: r.card_id})
        MERGE (a:Archetype {name: r.archetype})
        MERGE (src)-[:MENTIONS_ARCHETYPE]->(a)
        """,
        arch_mentions,
        batch_size=1000,
    )

    # 4. Ingesti Dokumen 4: Banlist Relasi
    logger.info(f"Mengingesti {len(banlist_entries):,} relasi Banlist (TCG/OCG/Goat)...")
    cypher_banlist = """
    UNWIND $batch AS row
    MATCH (c:Card {id: row.card_id})
    MATCH (f:Format {name: row.format})
    MATCH (b:BanStatus {status: row.status})
    MERGE (c)-[rel:BANNED_IN]->(f)
    SET rel.status = row.status, rel.max_copies = row.max_copies
    MERGE (c)-[:HAS_BAN_STATUS {format: row.format}]->(b)
    """
    client.run_batch_write(cypher_banlist, banlist_entries, batch_size=800)


def ingest_rulings_to_neo4j(
    client: Neo4jGraphClient,
    rulings_bundle: dict[str, list[dict[str, Any]]],
) -> None:
    """Ingesti Dokumen 3B: Official Card FAQs & Q&A Rulings dari db.ygoresources.com."""
    faqs = rulings_bundle.get("faqs") or []
    rulings = rulings_bundle.get("rulings") or []

    if faqs:
        logger.info(f"Mengingesti {len(faqs):,} Card FAQ resmi ke Neo4j...")
        cypher_faq = """
        UNWIND $batch AS row
        MERGE (fq:CardFAQ {id: row.id})
        SET fq.konami_id = row.konami_id,
            fq.card_name = row.card_name,
            fq.text = row.text,
            fq.source_url = row.source_url
        WITH fq, row
        MATCH (c:Card {konami_id: row.konami_id})
        MERGE (c)-[:HAS_FAQ]->(fq)
        """
        client.run_batch_write(cypher_faq, faqs, batch_size=300)

    if rulings:
        logger.info(f"Mengingesti {len(rulings):,} Q&A Rulings & relasi RULES_ON ke Neo4j...")
        cypher_rulings = """
        UNWIND $batch AS row
        MERGE (ru:Ruling {id: row.id})
        SET ru.qa_id = row.qa_id,
            ru.title = row.title,
            ru.question = row.question,
            ru.answer = row.answer,
            ru.date = row.date,
            ru.language = row.language,
            ru.source_url = row.source_url
        WITH ru, row
        UNWIND row.konami_ids AS kid
        MATCH (c:Card {konami_id: kid})
        MERGE (ru)-[:RULES_ON]->(c)
        """
        client.run_batch_write(cypher_rulings, rulings, batch_size=300)


def format_card_for_embedding(card: dict[str, Any]) -> str:
    """Menyusun representasi teks kaya untuk embedding semantik satu kartu."""
    stats_parts = []
    if card.get("attribute"):
        stats_parts.append(f"Attribute: {card['attribute']}")
    if card.get("race"):
        stats_parts.append(f"Sub-type/Race: {card['race']}")
    if card.get("level") is not None:
        stats_parts.append(f"Level/Rank: {card['level']}")
    if card.get("linkval") is not None:
        stats_parts.append(f"Link-{card['linkval']}")
    if card.get("atk") is not None:
        stats_parts.append(f"ATK: {card['atk']} / DEF: {card.get('def')}")
    if card.get("archetype"):
        stats_parts.append(f"Archetype: {card['archetype']}")
    stats_parts.append(f"TCG Banlist: {card.get('ban_tcg', 'Unlimited')}, OCG Banlist: {card.get('ban_ocg', 'Unlimited')}")

    return (
        f"Card Name: {card['name']}\n"
        f"Card Type: {card.get('type', '')}\n"
        f"{' | '.join(stats_parts)}\n"
        f"Effect / Text: {card.get('desc', '')}"
    )


def ensure_vector_indexes(client: Neo4jGraphClient, embedding_dim: int) -> None:
    """Memastikan kelima Vector Index di Neo4j sesuai dengan dimensi model aktif (384d atau 768d)."""
    idx_specs = [
        ("card_vector_idx", "Card"),
        ("rulebook_vector_idx", "RuleChunk"),
        ("psct_vector_idx", "PSCTRule"),
        ("ruling_vector_idx", "Ruling"),
        ("faq_vector_idx", "CardFAQ"),
    ]
    existing = client.run_query("SHOW VECTOR INDEXES YIELD name, options RETURN name, options")
    recreate_needed = False
    for row in existing:
        opts = row.get("options") or {}
        cfg = opts.get("indexConfig") or {}
        curr_dim = cfg.get("vector.dimensions")
        if curr_dim is not None and int(curr_dim) != int(embedding_dim):
            recreate_needed = True
            break

    if recreate_needed:
        logger.info(
            f"Menyesuaikan dimensi Vector Index Neo4j ke {embedding_dim}d..."
        )
        for idx_name, _ in idx_specs:
            client.run_query(f"DROP INDEX {idx_name} IF EXISTS")
        client.run_query(
            "MATCH (n) WHERE n.embedding IS NOT NULL AND size(n.embedding) <> $dim REMOVE n.embedding",
            {"dim": int(embedding_dim)},
        )

    for idx_name, label in idx_specs:
        client.run_query(
            f"""
            CREATE VECTOR INDEX {idx_name} IF NOT EXISTS
            FOR (n:{label}) ON (n.embedding)
            OPTIONS {{indexConfig: {{`vector.dimensions`: {int(embedding_dim)}, `vector.similarity_function`: 'cosine'}}}}
            """
        )


def embed_and_index_nodes(
    client: Neo4jGraphClient,
    embedder: GeminiEmbedder,
    rule_chunks: list[dict[str, Any]],
    psct_rules: list[dict[str, Any]],
    rulings_bundle: dict[str, list[dict[str, Any]]],
    cards_enriched: list[dict[str, Any]],
    max_card_embeddings: int | None = 600,
) -> dict[str, int]:
    """Menghitung vektor embedding Gemini & menyimpannya ke Vector Index Neo4j.

    Catatan: Seluruh 14.000+ kartu tetap terindeks penuh di Neo4j Graph & Fulltext BM25 Index.
    Parameter `max_card_embeddings` mengontrol berapa banyak kartu terpopuler/banlist yang
    dihitung vektornya pada satu sesi (set `None` untuk embed seluruh ~14.000 kartu).
    """
    counts: dict[str, int] = {}
    ensure_vector_indexes(client, embedder.dimension)

    # 1. Embed Rulebook Chunks
    rb_items = [
        {"id": r["id"], "embed_text": f"{r['section_title']}\n{r['text']}"}
        for r in rule_chunks
    ]
    rb_vecs = embedder.embed_documents(rb_items)
    client.run_batch_write(
        "UNWIND $batch AS r MATCH (n:RuleChunk {id: r.id}) SET n.embedding = r.vec",
        [{"id": k, "vec": v} for k, v in rb_vecs.items()],
        batch_size=200,
    )
    counts["RuleChunk"] = len(rb_vecs)

    # 2. Embed PSCT Rules
    psct_items = [
        {"id": p["id"], "embed_text": f"{p['name']} ({p['pattern']})\n{p['explanation']}"}
        for p in psct_rules
    ]
    psct_vecs = embedder.embed_documents(psct_items)
    client.run_batch_write(
        "UNWIND $batch AS r MATCH (n:PSCTRule {id: r.id}) SET n.embedding = r.vec",
        [{"id": k, "vec": v} for k, v in psct_vecs.items()],
        batch_size=100,
    )
    counts["PSCTRule"] = len(psct_vecs)

    # 3. Embed Card FAQs & Q&A Rulings
    faqs = rulings_bundle.get("faqs") or []
    faq_items = [{"id": f["id"], "embed_text": f["text"]} for f in faqs]
    faq_vecs = embedder.embed_documents(faq_items)
    client.run_batch_write(
        "UNWIND $batch AS r MATCH (n:CardFAQ {id: r.id}) SET n.embedding = r.vec",
        [{"id": k, "vec": v} for k, v in faq_vecs.items()],
        batch_size=200,
    )
    counts["CardFAQ"] = len(faq_vecs)

    rulings = rulings_bundle.get("rulings") or []
    ruling_items = [
        {
            "id": ru["id"],
            "embed_text": f"Cards: {', '.join(ru.get('card_names', []))}\nQuestion: {ru['question']}\nAnswer: {ru['answer']}",
        }
        for ru in rulings
    ]
    ruling_vecs = embedder.embed_documents(ruling_items)
    client.run_batch_write(
        "UNWIND $batch AS r MATCH (n:Ruling {id: r.id}) SET n.embedding = r.vec",
        [{"id": k, "vec": v} for k, v in ruling_vecs.items()],
        batch_size=200,
    )
    counts["Ruling"] = len(ruling_vecs)

    # 4. Embed Cards (prioritaskan Banlist + kartu dengan views tertinggi)
    sorted_cards = sorted(
        cards_enriched,
        key=lambda c: (
            1 if (c.get("ban_tcg") != "Unlimited" or c.get("ban_ocg") != "Unlimited") else 0,
            int(c.get("views", 0)),
        ),
        reverse=True,
    )
    target_cards = sorted_cards if max_card_embeddings is None else sorted_cards[:max_card_embeddings]
    card_items = [
        {"id": c["id"], "embed_text": format_card_for_embedding(c)}
        for c in target_cards
    ]
    total_card_embedded = 0
    chunk_step = 1000
    for start_idx in range(0, len(card_items), chunk_step):
        sub_items = card_items[start_idx : start_idx + chunk_step]
        card_vecs = embedder.embed_documents(sub_items)
        client.run_batch_write(
            "UNWIND $batch AS r MATCH (n:Card {id: r.id}) SET n.embedding = r.vec",
            [{"id": k, "vec": v} for k, v in card_vecs.items()],
            batch_size=400,
        )
        total_card_embedded += len(card_vecs)
        logger.success(
            f"Neo4j Vector Index (:Card) terupdate: {total_card_embedded:,}/{len(card_items):,} kartu"
        )
    counts["Card"] = total_card_embedded

    logger.success(f"Selesai mengindeks vektor ke Neo4j: {counts}")
    return counts
