"""Akuisisi Dokumen 3: Panduan Resmi PSCT & Database Card Rulings (db.ygoresources.com)."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.config import Settings, get_settings

YGORESOURCES_BASE = "https://db.ygoresources.com"

KONAMI_PSCT_ARTICLES = [
    ("psct_blog_part3", "PSCT Part 3: Conditions, Activations, and Effects", "https://yugiohblog.konami.com/articles/?p=2947"),
    ("psct_blog_part4", "PSCT Part 4: Targeting & Card Clues", "https://yugiohblog.konami.com/articles/?p=2962"),
    ("psct_blog_part7", "PSCT Part 7: Conjunction Functions", "https://yugiohblog.konami.com/articles/?p=4514"),
]

# Aturan resmi PSCT Konami yang dipetakan langsung ke node (:PSCTRule) di Neo4j
AUTHORITATIVE_PSCT_RULES: list[dict[str, Any]] = [
    {
        "id": "psct_colon_condition",
        "name": "PSCT Colon (:) — Activation Condition & Trigger",
        "pattern": "<Activation Condition> : <Activation/Cost> ; <Effect>",
        "category": "Sentence Structure",
        "simultaneous": None,
        "part_a_required_for_b": True,
        "explanation": (
            "In Problem-Solving Card Text (PSCT), anything written BEFORE a colon (:) is the Activation Condition "
            "or Trigger requirement (such as 'During the Main Phase:', 'If this card is Normal or Special Summoned:', "
            "or 'Once per turn:'). If an effect contains a colon (:) or semicolon (;), that monster/spell/trap effect "
            "ACTIVATES and starts a Chain Link, allowing the opponent to respond with Fast Effects. If a monster effect "
            "has NO colon (:) and NO semicolon (;), it does NOT start a Chain (Continuous, Unclassified, or Summoning Condition)."
        ),
    },
    {
        "id": "psct_semicolon_cost_target",
        "name": "PSCT Semicolon (;) — Actions at Activation (Cost & Targeting)",
        "pattern": "<Condition> : <Cost / Targeting / Declarations> ; <Resolution Effect>",
        "category": "Sentence Structure",
        "simultaneous": False,
        "part_a_required_for_b": True,
        "explanation": (
            "In PSCT, everything written BEFORE a semicolon (;) (and after the colon, if any) happens immediately when "
            "the card or effect is ACTIVATED (placed on the Chain), BEFORE the opponent decides whether to chain a response. "
            "This includes paying LP, discarding, sending to GY for cost, Tributing for cost, banishing for cost, and choosing "
            "targets. Costs paid before ';' are NEVER refunded even if the activation or effect is negated (e.g., by Ash Blossom "
            "or Solemn Judgment), and paying a cost does NOT trigger effects that say 'If this card is sent to the GY by a card effect'."
        ),
    },
    {
        "id": "psct_targeting",
        "name": "PSCT Targeting — Explicit Word 'target' Before Semicolon (;)",
        "pattern": "... target X ... ; <Effect on that target>",
        "category": "Targeting",
        "simultaneous": False,
        "part_a_required_for_b": True,
        "explanation": (
            "Under PSCT, an effect targets ONLY if it explicitly uses the word 'target' BEFORE the semicolon (;) "
            "(aside from Equip Spells, which inherently target the monster they equip to). Targets are declared at Chain Link "
            "creation. Cards with protection like 'Neither player can target this card with card effects' CANNOT be chosen as "
            "targets at activation."
        ),
    },
    {
        "id": "psct_non_targeting",
        "name": "PSCT Non-Targeting Selection — Chosen at Resolution (After ';' or No ';')",
        "pattern": "<Activation> ; ... choose / send / banish / destroy 1 card ...",
        "category": "Targeting",
        "simultaneous": False,
        "part_a_required_for_b": False,
        "explanation": (
            "If an effect does NOT use the word 'target' before the semicolon (;)—for example, Mirrorjade the Iceblade Dragon "
            "('banish 1 monster on the field'), Forbidden Droplet, or Zeus—the card is chosen when the Chain Link RESOLVES, "
            "not at activation! Therefore, non-targeting effects BYPASS 'cannot be targeted' protection, and your opponent does "
            "not know which card you will pick until resolution."
        ),
    },
    {
        "id": "psct_conj_and_if_you_do",
        "name": "PSCT Conjunction: 'and if you do' (A, and if you do, B)",
        "pattern": "Do A, and if you do, do B",
        "category": "Conjunctions",
        "simultaneous": True,
        "part_a_required_for_b": True,
        "explanation": (
            "PSCT Conjunction 'A, and if you do, B': "
            "1) Timeline: A and B are treated as happening SIMULTANEOUSLY for timing purposes (so optional 'When... you can' "
            "triggers triggered by A will NOT miss the timing!). "
            "2) Causality: A IS REQUIRED for B. If A fails to happen completely, B does NOT happen. However, B is NOT required for A."
        ),
    },
    {
        "id": "psct_conj_then",
        "name": "PSCT Conjunction: 'then' (A, then B)",
        "pattern": "Do A, then do B",
        "category": "Conjunctions",
        "simultaneous": False,
        "part_a_required_for_b": True,
        "explanation": (
            "PSCT Conjunction 'A, then B': "
            "1) Timeline: Sequential—A happens first, and AFTER that, B happens. Because B is the last thing to happen during resolution, "
            "any optional 'When ...: You can' effect whose trigger occurred during A WILL MISS THE TIMING (if this resolved at Chain Link 1)! "
            "2) Causality: A IS REQUIRED for B. If A does not happen, B will not happen."
        ),
    },
    {
        "id": "psct_conj_also",
        "name": "PSCT Conjunction: 'also' (A, also B)",
        "pattern": "Do A, also do B",
        "category": "Conjunctions",
        "simultaneous": True,
        "part_a_required_for_b": False,
        "explanation": (
            "PSCT Conjunction 'A, also B': "
            "1) Timeline: A and B happen SIMULTANEOUSLY (neither causes optional 'When... you can' effects to miss timing). "
            "2) Causality: NEITHER is required for the other! Even if A fails or is prevented, B still resolves as much as possible, "
            "and even if B cannot happen, A still happens."
        ),
    },
    {
        "id": "psct_conj_also_after_that",
        "name": "PSCT Conjunction: 'also, after that' (A, also, after that, B)",
        "pattern": "Do A, also, after that, do B",
        "category": "Conjunctions",
        "simultaneous": False,
        "part_a_required_for_b": False,
        "explanation": (
            "PSCT Conjunction 'A, also, after that, B': "
            "1) Timeline: Sequential—B happens AFTER A (so A is NOT considered simultaneous with B for timing!). "
            "2) Causality: A is NOT required for B! Even if A fails to happen, B still proceeds."
        ),
    },
    {
        "id": "psct_conj_at_the_same_time",
        "name": "PSCT Conjunction: 'and' / 'at the same time' (Both Required)",
        "pattern": "Do A and B / at the same time",
        "category": "Conjunctions",
        "simultaneous": True,
        "part_a_required_for_b": True,
        "explanation": (
            "PSCT Conjunction 'and' / 'at the same time': "
            "1) Timeline: Simultaneous. "
            "2) Causality: BOTH A and B are required! If you cannot perform ALL parts at resolution, NOTHING happens at all."
        ),
    },
    {
        "id": "psct_when_optional_timing",
        "name": "PSCT Timing: Optional 'When ...: You can' (Missing the Timing)",
        "pattern": "When <event>: You can ...",
        "category": "Timing & Chains",
        "simultaneous": None,
        "part_a_required_for_b": True,
        "explanation": (
            "An optional Trigger Effect worded 'When <event>: You can ...' can ONLY activate if <event> was the VERY LAST thing "
            "to happen in the game state! It WILL MISS THE TIMING if: (a) <event> occurred as a Cost before ';' (e.g., Tributed for "
            "a Tribute Summon or sent to GY for cost), (b) <event> occurred at Chain Link 2 or higher (since Chain Link 1 resolves afterward), "
            "or (c) <event> was part A of a 'Do A, then do B' effect."
        ),
    },
    {
        "id": "psct_if_optional_timing",
        "name": "PSCT Timing: Optional 'If ...: You can' (Never Misses Chain Timing)",
        "pattern": "If <event>: You can ...",
        "category": "Timing & Chains",
        "simultaneous": None,
        "part_a_required_for_b": False,
        "explanation": (
            "A Trigger Effect worded 'If <event>: You can ...' (or mandatory 'When/If <event>: <effect>' without 'You can') "
            "DOES NOT miss the timing even if <event> happened as Cost, at Chain Link 2+, or before 'then'! It activates on a new Chain "
            "as soon as the current Chain or Summon window finishes resolving (provided the card remains in that trigger location per the 2021 update)."
        ),
    },
    {
        "id": "psct_hard_opt",
        "name": "PSCT Restriction: Hard Once Per Turn (HOPT — By Card Name)",
        "pattern": "You can only use / activate this effect of 'Card Name' once per turn.",
        "category": "Restrictions",
        "simultaneous": None,
        "part_a_required_for_b": False,
        "explanation": (
            "Hard Once Per Turn (HOPT) binds the restriction to the CARD'S NAME across all copies for that turn. "
            "Critical distinction: "
            "- 'You can only ACTIVATE 1 [Card Name] per turn': If the ACTIVATION itself is negated (e.g., Solemn Judgment / Baronne de Fleur), "
            "you CAN activate another copy that turn! (If only the EFFECT is negated, e.g., Ash Blossom / Infinite Impermanence, you CANNOT.) "
            "- 'You can only USE this effect of [Card Name] once per turn': Even if the activation IS negated, you CANNOT attempt to use it again that turn!"
        ),
    },
    {
        "id": "psct_soft_opt",
        "name": "PSCT Restriction: Soft Once Per Turn (SOPT — Per Face-Up Copy)",
        "pattern": "Once per turn: ...",
        "category": "Restrictions",
        "simultaneous": None,
        "part_a_required_for_b": False,
        "explanation": (
            "Soft Once Per Turn ('Once per turn:' without naming the card) applies ONLY to that specific face-up copy currently on the field. "
            "If you control a second copy, are flipped face-down and Flip Summoned, or leave the field and are Special Summoned back, "
            "you can activate 'Once per turn:' again in the same turn!"
        ),
    },
    {
        "id": "psct_quick_effect",
        "name": "PSCT Fast Effect: '(Quick Effect)' — Spell Speed 2 Monster Effect",
        "pattern": "(Quick Effect): ...",
        "category": "Spell Speed",
        "simultaneous": None,
        "part_a_required_for_b": False,
        "explanation": (
            "Monster effects labeled '(Quick Effect)' (formerly 'during either player's turn') are Spell Speed 2 Fast Effects. "
            "They can be activated during either player's turn whenever Fast Effects are legal and can chain to Spell Speed 1 or 2 effects, "
            "unless restricted to a specific phase (e.g., 'During the Main Phase (Quick Effect):'). They CANNOT respond to Spell Speed 3 Counter Traps."
        ),
    },
    {
        "id": "psct_nomi_summon_condition",
        "name": "PSCT Summoning Condition: 'Must be ... Summoned' (Nomi Monster)",
        "pattern": "Must be Special/Fusion/Synchro/Xyz/Ritual/Link Summoned by ...",
        "category": "Summoning Conditions",
        "simultaneous": None,
        "part_a_required_for_b": True,
        "explanation": (
            "'Must be [Method] Summoned' (Nomi) means the monster CANNOT be Special Summoned by other card effects (like Monster Reborn) "
            "even from the GY or banished zone, EVEN IF it was properly Summoned earlier—unless an effect explicitly states 'ignoring its Summoning conditions' "
            "(note: 'ignoring its Summoning conditions' still cannot revive an Extra Deck/Ritual/Nomi monster from GY/banished if it was NEVER properly Summoned first!)."
        ),
    },
    {
        "id": "psct_semi_nomi_summon",
        "name": "PSCT Summoning Condition: 'Must first be ... Summoned' (Semi-Nomi & Extra Deck Rule)",
        "pattern": "Must first be Special/Fusion/Synchro/Xyz/Ritual/Link Summoned ...",
        "category": "Summoning Conditions",
        "simultaneous": None,
        "part_a_required_for_b": True,
        "explanation": (
            "'Must first be [Method] Summoned' (as well as ALL Ritual, Fusion, Synchro, Xyz, and Link Monsters inherently by game rules) "
            "must first be properly Summoned via their required method. Once properly Summoned, if sent to the GY or banished face-up, "
            "they CAN then be Special Summoned by generic revival effects like Monster Reborn. If cheated out directly from the Extra Deck "
            "(e.g., via Waking the Dragon or Instant Fusion when not treated as a Fusion Summon), they were NOT properly Summoned and CANNOT be revived from GY!"
        ),
    },
    {
        "id": "psct_damage_step",
        "name": "PSCT & Rulebook: Damage Step Activation Legality",
        "pattern": "During the Damage Step ...",
        "category": "Damage Step",
        "simultaneous": None,
        "part_a_required_for_b": False,
        "explanation": (
            "During the Damage Step, ONLY specific Fast Effects and Trigger Effects may be activated: "
            "1) Counter Trap Cards (Spell Speed 3), "
            "2) Mandatory effects, "
            "3) Fast Effects that directly modify ATK or DEF (e.g., Forbidden Droplet, Honest — only BEFORE Damage Calculation!), "
            "4) Fast Effects that negate the ACTIVATION of a card/effect (e.g., Baronne de Fleur, Ghost Belle — NOT Ash Blossom or Effect Veiler, "
            "because Ash Blossom & Infinite Impermanence negate EFFECTS, not activations!), "
            "5) Trigger Effects triggered by the card itself moving/flipping/battling, or cards explicitly stating 'during the Damage Step'."
        ),
    },
]


def strip_html_and_card_links(raw_text: str, id_to_name: dict[int, str] | None = None) -> str:
    """Membersihkan tag HTML dan markup <<konami_id:Card Name>> dari db.ygoresources.com."""
    if not raw_text:
        return ""
    text = raw_text

    # Format db.ygoresources.com sering memakai <<12950>> atau <<12950:Ash Blossom>>
    def _replace_ref(match: re.Match[str]) -> str:
        inner = match.group(1)
        if ":" in inner:
            return f'"{inner.split(":", 1)[1]}"'
        if inner.isdigit() and id_to_name and int(inner) in id_to_name:
            return f'"{id_to_name[int(inner)]}"'
        return f"Card#{inner}"

    text = re.sub(r"<<([^>]+)>>", _replace_ref, text)
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _fetch_single_qa(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    qa_id: int,
    id_to_name: dict[int, str],
) -> dict[str, Any] | None:
    """Mengambil satu Q&A ruling resmi dari db.ygoresources.com/data/qa/<id>."""
    url = f"{YGORESOURCES_BASE}/data/qa/{qa_id}"
    async with sem:
        try:
            resp = await client.get(url, timeout=20.0)
            if resp.status_code != 200:
                return None
            payload = resp.json()
        except Exception:
            return None

    qa_data = payload.get("qaData") or {}
    locale = qa_data.get("en") or qa_data.get("ja")
    if not locale:
        return None
    lang = "en" if "en" in qa_data else "ja"

    title = strip_html_and_card_links(locale.get("title", ""), id_to_name)
    question = strip_html_and_card_links(locale.get("question", ""), id_to_name)
    answer = strip_html_and_card_links(locale.get("answer", ""), id_to_name)
    if not question and not answer:
        return None

    cards_involved_raw = locale.get("cards") or payload.get("cards") or []
    konami_ids = []
    for cid in cards_involved_raw:
        try:
            konami_ids.append(int(cid))
        except (TypeError, ValueError):
            continue

    card_names = [id_to_name[cid] for cid in konami_ids if cid in id_to_name]

    return {
        "id": f"qa_{qa_id}",
        "qa_id": int(qa_id),
        "title": title,
        "question": question,
        "answer": answer,
        "date": locale.get("thisSrc", {}).get("date", "") if isinstance(locale.get("thisSrc"), dict) else "",
        "language": lang,
        "konami_ids": konami_ids,
        "card_names": card_names,
        "source_url": f"https://db.ygoresources.com/qa#{qa_id}",
    }


async def _fetch_card_faq_and_qas(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    konami_id: int,
    id_to_name: dict[int, str],
) -> tuple[dict[str, Any] | None, list[int]]:
    """Mengambil ringkasan FAQ resmi kartu serta daftar ID Q&A terkait dari /data/card/<konami_id>."""
    url = f"{YGORESOURCES_BASE}/data/card/{konami_id}"
    async with sem:
        try:
            resp = await client.get(url, timeout=20.0)
            if resp.status_code != 200:
                return None, []
            payload = resp.json()
        except Exception:
            return None, []

    qa_ids_raw = payload.get("qaIndex") or []
    qa_ids = [int(qid) for qid in qa_ids_raw if str(qid).isdigit()]

    faq_data = payload.get("faqData") or {}
    en_faq = faq_data.get("en") or {}
    entries = en_faq.get("entries") or []
    cleaned_entries = [strip_html_and_card_links(str(e), id_to_name) for e in entries if e]
    cleaned_entries = [e for e in cleaned_entries if e]

    faq_record = None
    if cleaned_entries:
        card_name = id_to_name.get(konami_id, f"Card #{konami_id}")
        faq_record = {
            "id": f"faq_{konami_id}",
            "konami_id": konami_id,
            "card_name": card_name,
            "entries": cleaned_entries,
            "text": f"Official Konami Card FAQ Notes for {card_name}:\n- " + "\n- ".join(cleaned_entries),
            "source_url": f"https://db.ygoresources.com/card#{konami_id}",
        }

    return faq_record, qa_ids


async def fetch_rulings_async(
    cards_enriched: list[dict[str, Any]],
    max_priority_cards: int = 350,
    max_qa_entries: int = 900,
) -> dict[str, list[dict[str, Any]]]:
    """Mengambil Card FAQ & Q&A Rulings secara paralel untuk kartu populer, staple, & banlist."""
    id_to_name = {
        int(c["konami_id"]): c["name"]
        for c in cards_enriched
        if c.get("konami_id") is not None and c.get("name")
    }

    # Prioritaskan kartu di Banlist TCG/OCG + kartu paling populer berdasarkan views
    priority_cards = [
        c
        for c in cards_enriched
        if c.get("konami_id") is not None
    ]
    priority_cards.sort(
        key=lambda c: (
            1 if (c.get("ban_tcg") != "Unlimited" or c.get("ban_ocg") != "Unlimited") else 0,
            int(c.get("views", 0)),
        ),
        reverse=True,
    )
    selected_konami_ids = [int(c["konami_id"]) for c in priority_cards[:max_priority_cards]]

    sem = asyncio.Semaphore(16)
    headers = {"User-Agent": "YuGiOh-GraphRAG-AcademicProject/1.0"}

    faqs: list[dict[str, Any]] = []
    discovered_qa_ids: set[int] = set()

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # 1. Ambil juga recent English Q&A terbaru dari db.ygoresources.com
        try:
            recent_resp = await client.get(f"{YGORESOURCES_BASE}/data/meta/recent/en/qa", timeout=20.0)
            if recent_resp.status_code == 200:
                recent_data = recent_resp.json()
                if isinstance(recent_data, list):
                    for item in recent_data[:200]:
                        if str(item).isdigit():
                            discovered_qa_ids.add(int(item))
                        elif isinstance(item, dict) and str(item.get("id", "")).isdigit():
                            discovered_qa_ids.add(int(item["id"]))
        except Exception as exc:
            logger.debug(f"Info recent QA dilewati: {exc}")

        # 2. Ambil Card FAQ + indeks QA untuk kartu-kartu prioritas
        logger.info(
            f"Mengambil FAQ & indeks Ruling dari db.ygoresources.com untuk {len(selected_konami_ids)} kartu prioritas..."
        )
        card_tasks = [
            _fetch_card_faq_and_qas(client, sem, kid, id_to_name)
            for kid in selected_konami_ids
        ]
        card_results = await asyncio.gather(*card_tasks)
        for faq_rec, qids in card_results:
            if faq_rec:
                faqs.append(faq_rec)
            # Ambil maks 4 Q&A per kartu agar distribusi merata di ratusan kartu berbeda
            for qid in qids[:4]:
                discovered_qa_ids.add(qid)

        qa_list_sorted = sorted(discovered_qa_ids, reverse=True)[:max_qa_entries]
        logger.info(f"Mengunduh detail {len(qa_list_sorted)} Q&A Rulings resmi...")

        qa_tasks = [
            _fetch_single_qa(client, sem, qid, id_to_name)
            for qid in qa_list_sorted
        ]
        qa_results = await asyncio.gather(*qa_tasks)
        rulings = [r for r in qa_results if r is not None]

    return {"faqs": faqs, "rulings": rulings}


def fetch_single_card_rulings_live(
    konami_id: int,
    id_to_name: dict[int, str] | None = None,
    max_qas: int = 8,
) -> dict[str, Any]:
    """Mengambil FAQ & Ruling spesifik satu kartu secara on-demand saat user bertanya kartu langka."""
    mapping = id_to_name or {}

    async def _run() -> dict[str, Any]:
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient(
            headers={"User-Agent": "YuGiOh-GraphRAG-LiveLookup/1.0"},
            follow_redirects=True,
        ) as client:
            faq_rec, qids = await _fetch_card_faq_and_qas(client, sem, konami_id, mapping)
            qa_tasks = [_fetch_single_qa(client, sem, qid, mapping) for qid in qids[:max_qas]]
            qas = [r for r in await asyncio.gather(*qa_tasks) if r is not None]
            return {"faq": faq_rec, "rulings": qas}

    try:
        return asyncio.run(_run())
    except RuntimeError:
        # Jika event loop sudah berjalan
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


def process_psct_and_rulings(
    cards_enriched: list[dict[str, Any]],
    settings: Settings | None = None,
    max_priority_cards: int = 350,
    max_qa_entries: int = 900,
    force: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Menyusun dataset PSCT Rules dan mengunduh Card Rulings & FAQ resmi."""
    cfg = settings or get_settings()

    # 1. Simpan PSCT Rules
    psct_rules = list(AUTHORITATIVE_PSCT_RULES)
    with cfg.psct_rules_path.open("w", encoding="utf-8") as f:
        json.dump(psct_rules, f, ensure_ascii=False, indent=2)

    # 2. Ambil atau muat Card Rulings & FAQs
    if cfg.rulings_processed_path.exists() and not force:
        logger.info(f"Memuat Card Rulings & FAQ dari {cfg.rulings_processed_path}")
        with cfg.rulings_processed_path.open("r", encoding="utf-8") as f:
            rulings_bundle = json.load(f)
        return psct_rules, rulings_bundle

    rulings_bundle = asyncio.run(
        fetch_rulings_async(
            cards_enriched=cards_enriched,
            max_priority_cards=max_priority_cards,
            max_qa_entries=max_qa_entries,
        )
    )

    with cfg.rulings_processed_path.open("w", encoding="utf-8") as f:
        json.dump(rulings_bundle, f, ensure_ascii=False, indent=2)

    logger.success(
        f"Berhasil menyimpan {len(psct_rules)} aturan PSCT, "
        f"{len(rulings_bundle['faqs'])} Card FAQ, dan {len(rulings_bundle['rulings'])} Q&A Rulings!"
    )
    return psct_rules, rulings_bundle
