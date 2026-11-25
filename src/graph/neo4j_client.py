"""Klien koneksi Neo4j, pemeriksaan status, statistik Knowledge Graph, dan ekstraksi Subgraph ECharts."""

from __future__ import annotations

import socket
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from neo4j import Driver, GraphDatabase

from src.config import Settings, get_settings


class Neo4jGraphClient:
    """Wrapper resmi Neo4j Python Driver untuk kueri Cypher & visualisasi Knowledge Graph."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._driver: Driver | None = None

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_username, self.settings.neo4j_password),
                connection_timeout=6.0,
            )
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def check_connection(self) -> tuple[bool, str]:
        """Memeriksa apakah database Neo4j aktif dan dapat diakses dengan pre-check cepat."""
        try:
            parsed = urlparse(self.settings.neo4j_uri)
            host = parsed.hostname or "localhost"
            port = parsed.port or 7687
            with socket.create_connection((host, port), timeout=0.6):
                pass
        except OSError as sock_err:
            return False, f"Port Neo4j {host}:{port} belum aktif ({sock_err})"

        try:
            self.driver.verify_connectivity()
            records = self.run_query("RETURN 'connected' AS status")
            if records:
                return True, f"Terhubung ke Neo4j ({self.settings.neo4j_uri})"
            return False, "Tidak mendapat respons dari Neo4j."
        except Exception as exc:
            return False, str(exc)

    def run_query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Menjalankan kueri Cypher baca/tulis dan mengembalikan list dictionary."""
        with self.driver.session(database=self.settings.neo4j_database) as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def run_batch_write(
        self,
        cypher: str,
        rows: list[dict[str, Any]],
        batch_size: int = 800,
    ) -> int:
        """Menjalankan UNWIND $batch dalam potongan batch agar hemat memori untuk 14.000+ kartu."""
        if not rows:
            return 0
        total = 0
        with self.driver.session(database=self.settings.neo4j_database) as session:
            for i in range(0, len(rows), batch_size):
                chunk = rows[i : i + batch_size]
                session.execute_write(lambda tx, b=chunk: tx.run(cypher, batch=b).consume())
                total += len(chunk)
        return total

    def get_graph_statistics(self) -> dict[str, int]:
        """Mengambil jumlah masing-masing tipe Node dan Relasi di Neo4j."""
        node_labels = [
            "Card",
            "Archetype",
            "RuleChunk",
            "RuleSection",
            "PSCTRule",
            "Ruling",
            "CardFAQ",
            "Format",
            "BanStatus",
            "GameConcept",
        ]
        stats: dict[str, int] = {}
        for label in node_labels:
            res = self.run_query(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
            stats[label] = int(res[0]["cnt"]) if res else 0

        rel_res = self.run_query("MATCH ()-[r]->() RETURN count(r) AS cnt")
        stats["Relationships"] = int(rel_res[0]["cnt"]) if rel_res else 0

        emb_res = self.run_query(
            "MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n) AS cnt"
        )
        stats["EmbeddedNodes"] = int(emb_res[0]["cnt"]) if emb_res else 0
        return stats

    def get_subgraph_for_echarts(
        self,
        entity_query: str = "Ash Blossom & Joyous Spring",
        hop_depth: int = 1,
        max_edges: int = 60,
    ) -> dict[str, Any]:
        """Mengambil subgraph di sekitar kartu/archetype/konsep dalam format siap pakai ECharts."""
        cypher_1hop = """
        MATCH (center)
        WHERE (center:Card AND toLower(center.name) CONTAINS toLower($q))
           OR (center:Archetype AND toLower(center.name) CONTAINS toLower($q))
           OR (center:GameConcept AND toLower(center.name) CONTAINS toLower($q))
           OR (center:PSCTRule AND toLower(center.name) CONTAINS toLower($q))
        WITH center
        ORDER BY CASE WHEN toLower(coalesce(center.name, '')) = toLower($q) THEN 0 ELSE 1 END,
                 coalesce(center.views, 0) DESC
        LIMIT 1
        MATCH (center)-[r]-(neighbor)
        RETURN
            elementId(center) AS src_id,
            labels(center)[0] AS src_label,
            coalesce(center.name, center.title, center.status, center.id) AS src_name,
            coalesce(center.type, center.category, center.description, '') AS src_detail,
            type(r) AS rel_type,
            coalesce(r.status, r.format, '') AS rel_prop,
            startNode(r) = center AS is_outgoing,
            elementId(neighbor) AS dst_id,
            labels(neighbor)[0] AS dst_label,
            coalesce(neighbor.name, neighbor.title, neighbor.question, neighbor.section_title, neighbor.status, neighbor.id) AS dst_name,
            coalesce(neighbor.type, neighbor.category, neighbor.answer, neighbor.text, '') AS dst_detail
        LIMIT $max_edges
        """

        cypher_2hop = """
        MATCH (center)
        WHERE (center:Card AND toLower(center.name) CONTAINS toLower($q))
           OR (center:Archetype AND toLower(center.name) CONTAINS toLower($q))
           OR (center:GameConcept AND toLower(center.name) CONTAINS toLower($q))
        WITH center
        ORDER BY CASE WHEN toLower(coalesce(center.name, '')) = toLower($q) THEN 0 ELSE 1 END,
                 coalesce(center.views, 0) DESC
        LIMIT 1
        MATCH p = (center)-[*1..2]-(neighbor)
        UNWIND relationships(p) AS r
        WITH DISTINCT r, startNode(r) AS s, endNode(r) AS e
        RETURN
            elementId(s) AS src_id,
            labels(s)[0] AS src_label,
            coalesce(s.name, s.title, s.question, s.section_title, s.status, s.id) AS src_name,
            coalesce(s.type, s.category, '') AS src_detail,
            type(r) AS rel_type,
            coalesce(r.status, r.format, '') AS rel_prop,
            true AS is_outgoing,
            elementId(e) AS dst_id,
            labels(e)[0] AS dst_label,
            coalesce(e.name, e.title, e.question, e.section_title, e.status, e.id) AS dst_name,
            coalesce(e.type, e.category, '') AS dst_detail
        LIMIT $max_edges
        """

        query = cypher_2hop if hop_depth >= 2 else cypher_1hop
        rows = self.run_query(query, {"q": entity_query, "max_edges": int(max_edges)})

        category_order = [
            "Card",
            "Archetype",
            "Ruling",
            "CardFAQ",
            "PSCTRule",
            "GameConcept",
            "RuleChunk",
            "Format",
            "BanStatus",
            "Attribute",
            "MonsterRace",
            "CardType",
        ]
        cat_index = {name: idx for idx, name in enumerate(category_order)}

        nodes_map: dict[str, dict[str, Any]] = {}
        links: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str]] = set()

        for row in rows:
            for prefix in ("src", "dst"):
                nid = str(row[f"{prefix}_id"])
                nlabel = str(row[f"{prefix}_label"] or "Node")
                raw_name = str(row[f"{prefix}_name"] or nid)
                short_name = raw_name if len(raw_name) <= 42 else raw_name[:39] + "..."
                if nlabel not in cat_index:
                    cat_index[nlabel] = len(category_order)
                    category_order.append(nlabel)
                if nid not in nodes_map:
                    size = 34 if (prefix == "src" and len(nodes_map) == 0) else (24 if nlabel == "Card" else 19)
                    nodes_map[nid] = {
                        "id": nid,
                        "name": short_name,
                        "value": f"[{nlabel}] {raw_name}",
                        "category": cat_index[nlabel],
                        "symbolSize": size,
                    }

            s_id = str(row["src_id"]) if row["is_outgoing"] else str(row["dst_id"])
            t_id = str(row["dst_id"]) if row["is_outgoing"] else str(row["src_id"])
            rel_label = str(row["rel_type"])
            if row.get("rel_prop"):
                rel_label = f"{rel_label} ({row['rel_prop']})"

            edge_key = (s_id, t_id, rel_label)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                links.append(
                    {
                        "source": s_id,
                        "target": t_id,
                        "value": rel_label,
                    }
                )

        categories = [{"name": c} for c in category_order]
        return {
            "nodes": list(nodes_map.values()),
            "links": links,
            "categories": categories,
        }
