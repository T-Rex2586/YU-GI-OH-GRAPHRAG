"""FastAPI Backend untuk Yu-Gi-Oh! Hybrid GraphRAG (REST + SSE Streaming)."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field

from src.config import get_settings
from src.graph.local_subgraph import build_local_subgraph
from src.graph.neo4j_client import Neo4jGraphClient
from src.rag.generator import GraphRAGGenerator
from src.rag.retriever import HybridGraphRetriever
from src.rag.router import QueryRouter

app = FastAPI(
    title="Yu-Gi-Oh! Hybrid GraphRAG API",
    version="2.0.0",
    description="Backend FastAPI untuk AI Head Judge, Neo4j Knowledge Graph, 14.704 Kartu, PSCT, & Banlist",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton Memory Store & Neo4j Client
_SETTINGS = get_settings()
_NEO4J = Neo4jGraphClient(_SETTINGS)
_RETRIEVER = HybridGraphRetriever(_SETTINGS, neo4j_client=_NEO4J)
_DATA_CACHE: dict[str, Any] | None = None


def get_local_store() -> dict[str, Any]:
    """Memuat seluruh dataset lokal sekali saja ke RAM untuk pencarian katalog <5ms."""
    global _DATA_CACHE
    if _DATA_CACHE is not None:
        return _DATA_CACHE

    t0 = time.perf_counter()
    cfg = get_settings()
    cards: list[dict[str, Any]] = []
    banlist: list[dict[str, Any]] = []
    rulebook: list[dict[str, Any]] = []
    psct: list[dict[str, Any]] = []
    rulings_bundle: dict[str, list[dict[str, Any]]] = {"faqs": [], "rulings": []}

    if cfg.cards_processed_path.exists():
        cards = json.loads(cfg.cards_processed_path.read_text(encoding="utf-8"))
    if cfg.banlist_processed_path.exists():
        banlist = json.loads(cfg.banlist_processed_path.read_text(encoding="utf-8"))
    if cfg.rulebook_chunks_path.exists():
        rulebook = json.loads(cfg.rulebook_chunks_path.read_text(encoding="utf-8"))
    if cfg.psct_rules_path.exists():
        psct = json.loads(cfg.psct_rules_path.read_text(encoding="utf-8"))
    if cfg.rulings_processed_path.exists():
        rulings_bundle = json.loads(cfg.rulings_processed_path.read_text(encoding="utf-8"))

    # Urutkan kartu dari yang terpopuler (views tertinggi) untuk default katalog
    cards_sorted = sorted(cards, key=lambda c: int(c.get("views", 0)), reverse=True)
    cards_by_id = {int(c["id"]): c for c in cards_sorted}
    cards_by_name_lower = {c["name"].lower(): c for c in cards_sorted}

    _DATA_CACHE = {
        "cards": cards_sorted,
        "cards_by_id": cards_by_id,
        "cards_by_name_lower": cards_by_name_lower,
        "banlist": banlist,
        "rulebook": rulebook,
        "psct": psct,
        "faqs": rulings_bundle.get("faqs", []),
        "rulings": rulings_bundle.get("rulings", []),
    }
    logger.success(
        f"Dataset dimuat ke RAM dalam {time.perf_counter() - t0:.2f}s ({len(cards_sorted):,} kartu)"
    )
    return _DATA_CACHE


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[ChatMessageIn] = Field(default_factory=list)
    use_llm_router: bool = True
    strategy: str = "hybrid"
    hop_depth: int = 2


def _sse_pack(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    store = get_local_store()
    neo_ok, neo_msg = _NEO4J.check_connection()
    neo_stats = _NEO4J.get_graph_statistics() if neo_ok else {}
    return {
        "neo4j_connected": neo_ok,
        "neo4j_message": neo_msg,
        "neo4j_stats": neo_stats,
        "corpus": {
            "rulebook_chunks": len(store["rulebook"]),
            "cards_total": len(store["cards"]),
            "psct_rules": len(store["psct"]),
            "rulings_total": len(store["rulings"]) + len(store["faqs"]),
            "banlist_entries": len(store["banlist"]),
        },
        "models": {
            "llm": _SETTINGS.gemini_llm_model,
            "embedding_provider": _SETTINGS.embedding_provider,
            "embedding_model": (
                _SETTINGS.fastembed_model
                if _SETTINGS.embedding_provider == "fastembed"
                else _SETTINGS.gemini_embedding_model
            ),
        },
    }


@app.post("/api/chat/stream")
def api_chat_stream(req: ChatRequest) -> StreamingResponse:
    cfg = get_settings()
    if not cfg.gemini_api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY belum diatur di .env")

    store = get_local_store()

    def event_generator() -> Iterator[str]:
        t0 = time.perf_counter()
        try:
            yield _sse_pack(
                "step",
                {
                    "stage": "routing",
                    "message": "Menganalisis niat pertanyaan & mengekstrak entitas kartu...",
                },
            )
            router = QueryRouter(cfg)
            plan = router.route(req.question, use_llm_router=req.use_llm_router)
            yield _sse_pack(
                "plan",
                {
                    "intents": plan.intents,
                    "english_query": plan.english_search_query,
                    "entities": plan.card_names + plan.archetypes,
                    "formats": plan.formats,
                },
            )

            yield _sse_pack(
                "step",
                {
                    "stage": "retrieving",
                    "message": "Menelusuri Neo4j Multi-Hop Knowledge Graph + Vector & BM25 Index...",
                },
            )
            retrieval = _RETRIEVER.retrieve(
                plan,
                top_k=6,
                strategy=req.strategy,
                hop_depth=req.hop_depth,
            )
            elapsed_ret = round(time.perf_counter() - t0, 2)

            # Perkaya kartu referensi dengan gambar resolusi tinggi & klausa PSCT dari RAM store
            enriched_ref_cards = []
            for rc in retrieval.cards[:6]:
                cid = int(rc["id"])
                full_card = store["cards_by_id"].get(cid, rc)
                enriched_ref_cards.append(
                    {
                        "id": cid,
                        "name": full_card.get("name", rc.get("name", "")),
                        "type": full_card.get("type", ""),
                        "frameType": full_card.get("frameType", ""),
                        "race": full_card.get("race", ""),
                        "attribute": full_card.get("attribute", ""),
                        "level": full_card.get("level"),
                        "linkval": full_card.get("linkval"),
                        "atk": full_card.get("atk"),
                        "def": full_card.get("def"),
                        "archetype": full_card.get("archetype", ""),
                        "desc": full_card.get("desc", ""),
                        "ban_tcg": full_card.get("ban_tcg", "Unlimited"),
                        "ban_ocg": full_card.get("ban_ocg", "Unlimited"),
                        "image_url": full_card.get("image_url_full") or full_card.get("image_url", ""),
                        "psct": full_card.get("psct", {}),
                    }
                )

            yield _sse_pack(
                "context",
                {
                    "mode": retrieval.mode,
                    "elapsed_sec": elapsed_ret,
                    "cards": enriched_ref_cards,
                    "psct_rules": [
                        {"id": p["id"], "name": p["name"], "pattern": p.get("pattern", "")}
                        for p in retrieval.psct_rules[:6]
                    ],
                    "rulings": [
                        {
                            "id": r["id"],
                            "title": r.get("title") or r.get("question", "")[:90],
                            "source_url": r.get("source_url", ""),
                        }
                        for r in retrieval.rulings[:6]
                    ],
                    "rulebook_sections": [
                        {
                            "id": rb["id"],
                            "section_title": rb.get("section_title", ""),
                            "source": rb.get("source", ""),
                        }
                        for rb in retrieval.rulebook_chunks[:4]
                    ],
                    "graph_paths": retrieval.graph_paths[:12],
                    "banlist_count": len(retrieval.banlist_records),
                },
            )

            yield _sse_pack(
                "step",
                {
                    "stage": "generating",
                    "message": "Menyusun putusan AI Head Judge dari bukti Knowledge Graph...",
                },
            )

            generator = GraphRAGGenerator(cfg)
            hist_dicts = [{"role": m.role, "content": m.content} for m in req.history]
            for chunk in generator.stream(req.question, retrieval, chat_history=hist_dicts):
                yield _sse_pack("token", {"text": chunk})

            yield _sse_pack("done", {"total_sec": round(time.perf_counter() - t0, 2)})
        except Exception as exc:
            logger.exception(f"Chat stream error: {exc}")
            yield _sse_pack("error", {"message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/graph")
def api_graph(
    q: str = Query("Ash Blossom & Joyous Spring"),
    hop: int = Query(1, ge=1, le=2),
    limit: int = Query(50, ge=10, le=120),
) -> dict[str, Any]:
    store = get_local_store()
    neo_ok, _ = _NEO4J.check_connection()
    if neo_ok:
        sg = _NEO4J.get_subgraph_for_echarts(entity_query=q, hop_depth=hop, max_edges=limit)
        source = "Neo4j Live Knowledge Graph"
    else:
        sg = build_local_subgraph(entity_query=q, local_data=store, max_edges=limit)
        source = "Local Processed Graph"

    # Perkaya node bertipe Card dengan data kartu dari RAM store bila cocok
    cat_list = sg.get("categories", [])
    for n in sg.get("nodes", []):
        cat_idx = n.get("category", 0)
        cat_name = cat_list[cat_idx]["name"] if 0 <= cat_idx < len(cat_list) else "Node"
        n["categoryName"] = cat_name
        raw_val = str(n.get("value", ""))
        clean_title = raw_val.split("] ", 1)[1] if "] " in raw_val else str(n.get("name", ""))
        n["fullName"] = clean_title
        card_match = store["cards_by_name_lower"].get(clean_title.lower())
        if card_match:
            n["card"] = {
                "id": card_match["id"],
                "name": card_match["name"],
                "type": card_match.get("type", ""),
                "archetype": card_match.get("archetype", ""),
                "atk": card_match.get("atk"),
                "def": card_match.get("def"),
                "ban_tcg": card_match.get("ban_tcg", "Unlimited"),
                "ban_ocg": card_match.get("ban_ocg", "Unlimited"),
                "image_url": card_match.get("image_url_full") or card_match.get("image_url", ""),
                "desc": card_match.get("desc", ""),
                "psct": card_match.get("psct", {}),
            }

    return {
        "source": source,
        "query": q,
        "hop": hop,
        "nodes": sg.get("nodes", []),
        "links": sg.get("links", []),
        "categories": cat_list,
    }


@app.get("/api/cards")
def api_cards(
    q: str = Query(""),
    category: str = Query("all"),
    ban_tcg: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
) -> dict[str, Any]:
    store = get_local_store()
    q_low = q.strip().lower()

    def _match(c: dict[str, Any]) -> bool:
        if ban_tcg != "all" and c.get("ban_tcg") != ban_tcg:
            return False
        if category != "all":
            ctype = c.get("type", "")
            ftype = (c.get("frameType") or "").lower()
            if category == "spell" and "Spell Card" not in ctype:
                return False
            if category == "trap" and "Trap Card" not in ctype:
                return False
            if category == "extradeck" and not any(
                k in ftype for k in ("fusion", "synchro", "xyz", "link")
            ):
                return False
            if category == "monster" and (
                "Monster" not in ctype
                or any(k in ftype for k in ("fusion", "synchro", "xyz", "link"))
            ):
                return False
        if q_low:
            return (
                q_low in c["name"].lower()
                or q_low in (c.get("archetype") or "").lower()
                or q_low in (c.get("desc") or "").lower()
                or q_low in (c.get("race") or "").lower()
            )
        return True

    matched = [c for c in store["cards"] if _match(c)]
    total = len(matched)
    start = (page - 1) * page_size
    slice_cards = matched[start : start + page_size]

    items = [
        {
            "id": c["id"],
            "konami_id": c.get("konami_id"),
            "name": c["name"],
            "type": c.get("type", ""),
            "frameType": c.get("frameType", ""),
            "race": c.get("race", ""),
            "attribute": c.get("attribute", ""),
            "level": c.get("level"),
            "scale": c.get("scale"),
            "linkval": c.get("linkval"),
            "atk": c.get("atk"),
            "def": c.get("def"),
            "archetype": c.get("archetype", ""),
            "desc": c.get("desc", ""),
            "ban_tcg": c.get("ban_tcg", "Unlimited"),
            "ban_ocg": c.get("ban_ocg", "Unlimited"),
            "ban_goat": c.get("ban_goat", "Unlimited"),
            "image_url": c.get("image_url_full") or c.get("image_url", ""),
            "image_url_small": c.get("image_url", ""),
            "psct": c.get("psct", {}),
        }
        for c in slice_cards
    ]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "items": items,
    }


@app.get("/api/banlist")
def api_banlist(
    format_name: str = Query("TCG", alias="format"),
    status: str = Query("all"),
    q: str = Query(""),
) -> dict[str, Any]:
    store = get_local_store()
    ban_rows = store["banlist"]
    q_low = q.strip().lower()

    # Ringkasan lintas format untuk grafik perbandingan
    summary: dict[str, dict[str, int]] = {
        "TCG": {"Forbidden": 0, "Limited": 0, "Semi-Limited": 0},
        "OCG": {"Forbidden": 0, "Limited": 0, "Semi-Limited": 0},
        "Goat": {"Forbidden": 0, "Limited": 0, "Semi-Limited": 0},
    }
    for b in ban_rows:
        fmt = b["format"]
        st_name = b["status"]
        if fmt in summary and st_name in summary[fmt]:
            summary[fmt][st_name] += 1

    filtered = []
    for b in ban_rows:
        if b["format"] != format_name:
            continue
        if status != "all" and b["status"] != status:
            continue
        if q_low and (
            q_low not in b["card_name"].lower()
            and q_low not in (b.get("archetype") or "").lower()
        ):
            continue
        full_card = store["cards_by_id"].get(int(b["card_id"]), {})
        filtered.append(
            {
                **b,
                "image_url": full_card.get("image_url_full") or full_card.get("image_url", ""),
                "image_url_small": full_card.get("image_url", ""),
                "desc": full_card.get("desc", ""),
                "atk": full_card.get("atk"),
                "def": full_card.get("def"),
                "level": full_card.get("level"),
                "linkval": full_card.get("linkval"),
                "race": full_card.get("race", ""),
                "attribute": full_card.get("attribute", ""),
                "ban_tcg": full_card.get("ban_tcg", "Unlimited"),
                "ban_ocg": full_card.get("ban_ocg", "Unlimited"),
                "psct": full_card.get("psct", {}),
            }
        )

    return {
        "format": format_name,
        "summary": summary,
        "total": len(filtered),
        "items": filtered,
    }


@app.get("/api/benchmarks")
def api_benchmarks() -> dict[str, Any]:
    res_file = PROJECT_ROOT / "results" / "experiment_results.json"
    if not res_file.exists():
        return {"available": False}
    data = json.loads(res_file.read_text(encoding="utf-8"))
    return {"available": True, **data}


# Sajikan bundle produksi React otomatis jika `frontend/dist` tersedia
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if (FRONTEND_DIST / "index.html").exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
