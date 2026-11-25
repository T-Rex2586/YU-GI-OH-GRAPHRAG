"""Parser otomatis Problem-Solving Card Text (PSCT) untuk kartu Yu-Gi-Oh!.

Membedah teks efek kartu menggunakan standar tata bahasa Konami PSCT:
    [Kondisi Aktivasi] : [Tindakan saat Aktivasi / Cost / Target] ; [Efek saat Resolusi]
Serta mendeteksi konjungsi ('and if you do', 'then', 'also', 'at the same time'),
jenis pembatasan Once Per Turn (Soft vs Hard OPT), Spell Speed, potensi Missing the Timing,
referensi kartu/archetype dalam tanda kutip, dan konsep mekanik permainan.
"""

from __future__ import annotations

import re
from typing import Any

QUOTED_NAME_RE = re.compile(r'"([^"\n]{2,80})"')
CONJUNCTION_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "psct_conj_and_if_you_do",
        "and if you do",
        re.compile(r"\band if you do\b", re.IGNORECASE),
    ),
    (
        "psct_conj_also_after_that",
        "also, after that",
        re.compile(r"\balso,\s*after that\b", re.IGNORECASE),
    ),
    (
        "psct_conj_then",
        "then",
        re.compile(r"(?:,\s*|\b)then\b", re.IGNORECASE),
    ),
    (
        "psct_conj_also",
        "also",
        re.compile(r"(?:,\s*|\b)also\b", re.IGNORECASE),
    ),
    (
        "psct_conj_at_the_same_time",
        "at the same time",
        re.compile(r"\bat the same time\b", re.IGNORECASE),
    ),
]

GENERIC_QUOTED_PHRASES = {
    "atk",
    "def",
    "token",
    "tokens",
    "spell",
    "trap",
    "monster",
    "monsters",
    "fusion",
    "synchro",
    "xyz",
    "pendulum",
    "link",
}


def split_effect_clauses(desc: str) -> list[str]:
    """Memecah teks efek kartu menjadi klausa efek individual."""
    if not desc:
        return []
    cleaned = desc.replace("\r\n", "\n")
    # Pisahkan header Pendulum / Monster Effect
    cleaned = re.sub(r"\[\s*(?:Pendulum|Monster)\s+Effect\s*\]", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"---+", "\n", cleaned)
    raw_lines = []
    for line in cleaned.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Pisahkan bullet point '●'
        if "●" in line:
            parts = [p.strip() for p in line.split("●") if p.strip()]
            raw_lines.extend(parts)
        else:
            raw_lines.append(line)

    clauses: list[str] = []
    sentence_split = re.compile(r"(?<=\.)\s+(?=[A-Z(\"])")
    for line in raw_lines:
        for sent in sentence_split.split(line):
            sent = sent.strip()
            if sent:
                clauses.append(sent)
    return clauses


def parse_psct_clause(clause: str) -> dict[str, Any]:
    """Membedah satu kalimat klausa efek berdasarkan ':' (kondisi) dan ';' (aktivasi/cost/target)."""
    has_colon = ":" in clause
    has_semicolon = ";" in clause

    condition = ""
    activation_and_cost = ""
    resolution_effect = clause

    if has_colon and has_semicolon:
        colon_idx = clause.find(":")
        semi_idx = clause.find(";", colon_idx + 1)
        if semi_idx != -1:
            condition = clause[:colon_idx].strip()
            activation_and_cost = clause[colon_idx + 1 : semi_idx].strip()
            resolution_effect = clause[semi_idx + 1 :].strip()
        else:
            # Kasus jarang ';' muncul sebelum ':'
            semi_idx = clause.find(";")
            activation_and_cost = clause[:semi_idx].strip()
            resolution_effect = clause[semi_idx + 1 :].strip()
    elif has_colon:
        colon_idx = clause.find(":")
        condition = clause[:colon_idx].strip()
        resolution_effect = clause[colon_idx + 1 :].strip()
    elif has_semicolon:
        semi_idx = clause.find(";")
        activation_and_cost = clause[:semi_idx].strip()
        resolution_effect = clause[semi_idx + 1 :].strip()

    starts_chain = has_colon or has_semicolon
    targets_on_activation = bool(re.search(r"\btarget\b", activation_and_cost, re.IGNORECASE))
    non_targeting_selection = (not targets_on_activation) and bool(
        re.search(
            r"\b(choose|send|banish|destroy|return|take control of|tribute)\b",
            resolution_effect,
            re.IGNORECASE,
        )
    )

    return {
        "raw": clause,
        "starts_chain": starts_chain,
        "condition": condition,
        "activation_and_cost": activation_and_cost,
        "resolution_effect": resolution_effect,
        "targets_on_activation": targets_on_activation,
        "non_targeting_selection": non_targeting_selection,
    }


def analyze_card_psct(
    card: dict[str, Any],
    known_card_names: set[str] | None = None,
    known_archetypes: set[str] | None = None,
) -> dict[str, Any]:
    """Menganalisis struktur PSCT, konsep mekanik, dan relasi referensi dari satu kartu."""
    desc = card.get("desc") or ""
    card_type = card.get("type") or ""
    frame_type = (card.get("frameType") or "").lower()
    race = card.get("race") or ""
    name = card.get("name") or ""

    is_normal_monster = "Normal" in card_type and "Pendulum" not in card_type
    clauses = [] if is_normal_monster else split_effect_clauses(desc)
    parsed_clauses = [parse_psct_clause(c) for c in clauses]

    psct_rule_ids: set[str] = set()
    conjunctions_found: list[str] = []

    has_activated_effect = any(c["starts_chain"] for c in parsed_clauses)
    has_condition = any(bool(c["condition"]) for c in parsed_clauses)
    has_cost = any(bool(c["activation_and_cost"]) for c in parsed_clauses)
    has_targeting = any(c["targets_on_activation"] for c in parsed_clauses)

    if has_condition:
        psct_rule_ids.add("psct_colon_condition")
    if has_cost:
        psct_rule_ids.add("psct_semicolon_cost_target")
    if has_targeting:
        psct_rule_ids.add("psct_targeting")
    elif not is_normal_monster and any(c["non_targeting_selection"] for c in parsed_clauses):
        psct_rule_ids.add("psct_non_targeting")

    if not is_normal_monster:
        for rule_id, label, pattern in CONJUNCTION_PATTERNS:
            if pattern.search(desc):
                psct_rule_ids.add(rule_id)
                conjunctions_found.append(label)

        # Deteksi Optional "When ... you can" (Missing the Timing) vs "If ... you can"
        if re.search(r"\bWhen\b[^:;]*:\s*You can\b", desc):
            psct_rule_ids.add("psct_when_optional_timing")
        if re.search(r"\bIf\b[^:;]*:\s*You can\b", desc):
            psct_rule_ids.add("psct_if_optional_timing")

        # Deteksi Hard Once Per Turn vs Soft Once Per Turn
        if re.search(r"You can only (?:use|activate)\b", desc, re.IGNORECASE):
            psct_rule_ids.add("psct_hard_opt")
        if re.search(r"\bOnce per turn\s*:", desc, re.IGNORECASE):
            psct_rule_ids.add("psct_soft_opt")

        # Deteksi Nomi / Semi-Nomi Summoning Condition
        if re.search(r"Must be (?:Special |Fusion |Synchro |Xyz |Ritual |Link )?Summoned", desc):
            psct_rule_ids.add("psct_nomi_summon_condition")
        elif re.search(r"Must first be (?:Special |Fusion |Synchro |Xyz |Ritual |Link )?Summoned", desc):
            psct_rule_ids.add("psct_semi_nomi_summon")

    # Penentuan Spell Speed & Game Concepts
    concepts: set[str] = set()
    spell_speed = 1

    if "Spell Card" in card_type:
        if race == "Quick-Play":
            spell_speed = 2
            concepts.update(["Spell Speed 2", "Quick-Play Spell", "Chain"])
        elif race == "Field":
            concepts.add("Field Spell")
        elif race == "Equip":
            concepts.add("Equip Spell")
        elif race == "Continuous":
            concepts.add("Continuous Spell")
        elif race == "Ritual":
            concepts.update(["Ritual Summon", "Spell Speed 1"])
        else:
            concepts.add("Spell Speed 1")
    elif "Trap Card" in card_type:
        if race == "Counter":
            spell_speed = 3
            concepts.update(["Spell Speed 3", "Counter Trap", "Chain"])
        elif race == "Continuous":
            spell_speed = 2
            concepts.update(["Spell Speed 2", "Continuous Trap", "Chain"])
        else:
            spell_speed = 2
            concepts.update(["Spell Speed 2", "Normal Trap", "Chain"])
    else:
        # Monster Cards
        if re.search(r"\(Quick Effect\)|during either player's", desc, re.IGNORECASE):
            spell_speed = 2
            concepts.update(["Spell Speed 2", "Quick Effect", "Chain"])
            psct_rule_ids.add("psct_quick_effect")
        if "fusion" in frame_type:
            concepts.update(["Fusion Summon", "Extra Deck", "Special Summon"])
        if "synchro" in frame_type:
            concepts.update(["Synchro Summon", "Extra Deck", "Special Summon"])
        if "xyz" in frame_type:
            concepts.update(["Xyz Summon", "Extra Deck", "Special Summon"])
        if "pendulum" in frame_type:
            concepts.update(["Pendulum Summon", "Pendulum Scale"])
        if "link" in frame_type:
            concepts.update(["Link Summon", "Extra Monster Zone", "Extra Deck", "Special Summon"])
        if "ritual" in frame_type:
            concepts.update(["Ritual Summon", "Special Summon"])
        if "Tuner" in card_type:
            concepts.add("Synchro Summon")
        if "Flip" in card_type or re.search(r"\bFLIP:", desc):
            concepts.add("Flip Effect")

    # Konsep tambahan di teks efek
    if not is_normal_monster:
        if re.search(r"\bDamage Step\b|\bATK\b|\bDEF\b", desc):
            if re.search(r"\bDamage Step\b", desc, re.IGNORECASE):
                concepts.add("Damage Step")
                psct_rule_ids.add("psct_damage_step")
        if re.search(r"\bGY\b|\bGraveyard\b", desc):
            concepts.add("Graveyard")
        if re.search(r"\bbanish(?:ed)?\b", desc, re.IGNORECASE):
            concepts.add("Banished")
        if re.search(r"\bSpecial Summon\b", desc):
            concepts.add("Special Summon")
        if re.search(r"\bTribute\b", desc):
            concepts.add("Tribute")

    # Ekstrak referensi nama kartu dan archetype dalam tanda kutip "..."
    mentioned_cards: list[str] = []
    mentioned_archetypes: list[str] = []
    seen_quotes: set[str] = set()

    for match in QUOTED_NAME_RE.finditer(desc):
        quoted = match.group(1).strip()
        if not quoted or quoted == name or quoted.lower() in GENERIC_QUOTED_PHRASES:
            continue
        if quoted in seen_quotes:
            continue
        seen_quotes.add(quoted)

        # Cek apakah sesudah tanda kutip ada kata 'card', 'monster', 'Spell', 'Trap'
        after_text = desc[match.end() : match.end() + 25].lower()
        is_archetype_pattern = bool(
            re.match(r"^\s*(?:card|cards|monster|monsters|spell|trap|tuner|synchro|xyz|fusion|link)", after_text)
        )

        if known_card_names and quoted in known_card_names and not is_archetype_pattern:
            mentioned_cards.append(quoted)
        elif known_archetypes and quoted in known_archetypes:
            mentioned_archetypes.append(quoted)
        elif known_card_names and quoted in known_card_names:
            mentioned_cards.append(quoted)
        elif is_archetype_pattern:
            mentioned_archetypes.append(quoted)

    return {
        "is_normal_monster": is_normal_monster,
        "spell_speed": spell_speed,
        "has_activated_effect": has_activated_effect,
        "has_condition": has_condition,
        "has_cost": has_cost,
        "has_targeting": has_targeting,
        "conjunctions": conjunctions_found,
        "psct_rule_ids": sorted(psct_rule_ids),
        "concepts": sorted(concepts),
        "mentioned_cards": mentioned_cards,
        "mentioned_archetypes": mentioned_archetypes,
        "clauses": parsed_clauses,
    }
