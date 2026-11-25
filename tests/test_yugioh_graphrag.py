"""Unit & Integration Tests untuk Yu-Gi-Oh! Hybrid GraphRAG (Core Engine + FastAPI)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import app, get_local_store
from src.graph.local_subgraph import build_local_subgraph
from src.ingestion.psct_analyzer import analyze_card_psct
from src.rag.retriever import HybridGraphRetriever
from src.rag.router import heuristic_route_query


def test_psct_ash_blossom() -> None:
    card = {
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
    }
    res = analyze_card_psct(card)
    assert res["spell_speed"] == 2
    assert res["has_activated_effect"] is True
    assert res["has_condition"] is True
    assert res["has_cost"] is True
    assert res["has_targeting"] is False
    assert "psct_quick_effect" in res["psct_rule_ids"]
    assert "psct_hard_opt" in res["psct_rule_ids"]


def test_psct_mirrorjade_non_targeting() -> None:
    card = {
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
    }
    res = analyze_card_psct(card, known_card_names={"Fallen of Albaz"})
    assert res["has_targeting"] is False
    assert "psct_non_targeting" in res["psct_rule_ids"]
    assert "psct_conj_also" in res["psct_rule_ids"]
    assert "Fallen of Albaz" in res["mentioned_cards"]
    assert "Fusion Summon" in res["concepts"]


def test_psct_infinite_impermanence_targeting_and_then() -> None:
    card = {
        "name": "Infinite Impermanence",
        "type": "Trap Card",
        "frameType": "trap",
        "race": "Normal",
        "desc": (
            "Target 1 face-up monster your opponent controls; negate its effects (until the end of this turn), "
            "then, if this card was Set before activation and is on the field at resolution, for the rest of this turn "
            "all other Spell/Trap effects in this column are negated."
        ),
    }
    res = analyze_card_psct(card)
    assert res["spell_speed"] == 2
    assert res["has_targeting"] is True
    assert "psct_targeting" in res["psct_rule_ids"]
    assert "psct_conj_then" in res["psct_rule_ids"]


def test_query_router_heuristics() -> None:
    p1 = heuristic_route_query('Apa status banlist Maxx "C" di TCG vs OCG?')
    assert "banlist" in p1.intents
    assert 'Maxx "C"' in p1.card_names
    assert "TCG" in p1.formats and "OCG" in p1.formats

    p2 = heuristic_route_query("Apakah Ash Blossom bisa negate efek saat Damage Step?")
    assert "ruling_psct" in p2.intents
    assert "rulebook" in p2.intents
    assert "Ash Blossom & Joyous Spring" in p2.card_names


def test_subgraph_and_fastapi_endpoints() -> None:
    store = get_local_store()
    if store["cards"]:
        sg = build_local_subgraph("Ash Blossom & Joyous Spring", store)
        assert len(sg["nodes"]) >= 3
        assert len(sg["links"]) >= 2

        plan = heuristic_route_query("Apakah Ash Blossom bisa negate efek saat Damage Step?")
        ret = HybridGraphRetriever().retrieve(plan, top_k=4)
        assert len(ret.cards) >= 1

    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert "corpus" in health.json()

    cards_resp = client.get("/api/cards?page=1&page_size=10")
    assert cards_resp.status_code == 200
    assert "items" in cards_resp.json()

    ban_resp = client.get("/api/banlist?format=TCG")
    assert ban_resp.status_code == 200
    assert "summary" in ban_resp.json()

    graph_resp = client.get("/api/graph?q=Dark%20Magician")
    assert graph_resp.status_code == 200
    assert "nodes" in graph_resp.json()
