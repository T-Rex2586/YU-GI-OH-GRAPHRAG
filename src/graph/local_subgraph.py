"""Pembangun sub-graf dari dataset JSON lokal saat server Neo4j sedang offline."""

from __future__ import annotations

from typing import Any


def build_local_subgraph(
    entity_query: str,
    local_data: dict[str, Any],
    max_edges: int = 50,
) -> dict[str, Any]:
    """Membangun struktur sub-graf (nodes, links, categories) dari JSON lokal."""
    cards = local_data.get("cards") or []
    psct_map = {p["id"]: p["name"] for p in (local_data.get("psct") or [])}
    rulings = local_data.get("rulings") or []

    category_order = [
        "Card",
        "Archetype",
        "Ruling",
        "PSCTRule",
        "GameConcept",
        "Format",
    ]
    cat_idx = {name: i for i, name in enumerate(category_order)}

    q_low = entity_query.lower().strip()
    matched = [
        c
        for c in cards
        if q_low in c["name"].lower() or q_low in (c.get("archetype") or "").lower()
    ]
    matched.sort(
        key=lambda c: (0 if c["name"].lower() == q_low else 1, -int(c.get("views", 0)))
    )
    if not matched:
        return {"nodes": [], "links": [], "categories": [{"name": c} for c in category_order]}

    center = matched[0]
    nodes: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []

    def _add_node(nid: str, name: str, cat: str, size: int = 20) -> None:
        if nid not in nodes:
            short = name if len(name) <= 40 else name[:37] + "..."
            nodes[nid] = {
                "id": nid,
                "name": short,
                "value": f"[{cat}] {name}",
                "category": cat_idx[cat],
                "symbolSize": size,
            }

    cid = f"card_{center['id']}"
    _add_node(cid, center["name"], "Card", size=36)

    if center.get("archetype"):
        aid = f"arch_{center['archetype']}"
        _add_node(aid, center["archetype"], "Archetype", size=26)
        links.append({"source": cid, "target": aid, "value": "BELONGS_TO_ARCHETYPE"})
        peers = [
            p for p in cards if p.get("archetype") == center["archetype"] and p["id"] != center["id"]
        ][:5]
        for peer in peers:
            pid = f"card_{peer['id']}"
            _add_node(pid, peer["name"], "Card", size=22)
            links.append({"source": pid, "target": aid, "value": "BELONGS_TO_ARCHETYPE"})

    for fmt, field_name in (("TCG", "ban_tcg"), ("OCG", "ban_ocg")):
        st_val = center.get(field_name, "Unlimited")
        if st_val != "Unlimited":
            fid = f"fmt_{fmt}"
            _add_node(fid, f"{fmt} ({st_val})", "Format", size=24)
            links.append({"source": cid, "target": fid, "value": f"BANNED_IN ({st_val})"})

    psct_info = center.get("psct") or {}
    for prid in psct_info.get("psct_rule_ids", [])[:6]:
        pname = psct_map.get(prid, prid)
        nid = f"psct_{prid}"
        _add_node(nid, pname, "PSCTRule", size=20)
        links.append({"source": cid, "target": nid, "value": "HAS_PSCT_PATTERN"})

    for concept in psct_info.get("concepts", [])[:6]:
        gid = f"gc_{concept}"
        _add_node(gid, concept, "GameConcept", size=20)
        links.append({"source": cid, "target": gid, "value": "USES_MECHANIC"})

    for mcard in psct_info.get("mentioned_cards", [])[:5]:
        mid = f"mcard_{mcard}"
        _add_node(mid, mcard, "Card", size=22)
        links.append({"source": cid, "target": mid, "value": "MENTIONS_CARD"})

    if center.get("konami_id"):
        kid = int(center["konami_id"])
        rel_rulings = [r for r in rulings if kid in (r.get("konami_ids") or [])][:4]
        for ru in rel_rulings:
            rid = ru["id"]
            _add_node(rid, f"{ru['id']}: {ru.get('question', '')[:35]}", "Ruling", size=19)
            links.append({"source": rid, "target": cid, "value": "RULES_ON"})

    return {
        "nodes": list(nodes.values()),
        "links": links[:max_edges],
        "categories": [{"name": c} for c in category_order],
    }
