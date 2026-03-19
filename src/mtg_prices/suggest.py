from __future__ import annotations

import re

from mtg_prices.models import Suggestion

ORACLE_KEYWORDS = frozenset({
    "destroy", "draw", "life", "exile", "counter", "sacrifice",
    "search", "token", "damage", "discard", "mill", "scry",
    "return", "tap", "untap", "flash", "haste", "trample",
    "flying", "deathtouch", "lifelink", "vigilance", "menace",
    "hexproof", "indestructible", "ward",
})

_WORD_RE = re.compile(r"[a-z]+")


def extract_oracle_keywords(oracle_text: str | None) -> set[str]:
    if not oracle_text:
        return set()
    words = set(_WORD_RE.findall(oracle_text.lower()))
    return words & ORACLE_KEYWORDS


def score_cmc(original_cmc: float, candidate_cmc: float) -> int:
    diff = abs(original_cmc - candidate_cmc)
    if diff == 0:
        return 2
    if diff <= 1:
        return 1
    return 0


def score_edhrec_rank(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return max(0.0, (10000 - rank) / 10000 * 2)


def score_keywords(original_kws: list[str], candidate_kws: list[str]) -> int:
    shared = set(original_kws) & set(candidate_kws)
    return min(len(shared) * 2, 4)  # Capped at 4


def score_oracle_text(original_text: str | None, candidate_text: str | None) -> int:
    orig_kws = extract_oracle_keywords(original_text)
    cand_kws = extract_oracle_keywords(candidate_text)
    shared = orig_kws & cand_kws
    return min(len(shared) * 3, 6)  # Capped at 6


def score_power_toughness(
    orig_power: str | None, orig_toughness: str | None,
    cand_power: str | None, cand_toughness: str | None,
) -> int:
    try:
        op, ot = int(orig_power), int(orig_toughness)  # type: ignore[arg-type]
        cp, ct = int(cand_power), int(cand_toughness)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if abs(op - cp) <= 1 and abs(ot - ct) <= 1:
        return 1
    return 0


def score_candidate(original: dict, candidate: dict) -> float:
    score = 0.0
    score += score_cmc(original.get("cmc", 0), candidate.get("cmc", 0))
    score += score_oracle_text(
        original.get("oracle_text"), candidate.get("oracle_text"),
    )
    score += score_keywords(
        original.get("keywords", []), candidate.get("keywords", []),
    )
    score += score_edhrec_rank(candidate.get("edhrec_rank"))
    score += score_power_toughness(
        original.get("power"), original.get("toughness"),
        candidate.get("power"), candidate.get("toughness"),
    )
    return score


def find_suggestions(
    original_card: dict,
    candidates: list[dict],
    deck_format: str,
    max_suggestions: int = 5,
) -> list[Suggestion]:
    original_usd_str = original_card.get("prices", {}).get("usd")
    if original_usd_str is None:
        return []
    original_price = float(original_usd_str)

    scored: list[tuple[float, dict]] = []
    for cand in candidates:
        if cand.get("name") == original_card.get("name"):
            continue
        legalities = cand.get("legalities", {})
        if legalities.get(deck_format) != "legal":
            continue
        cand_usd_str = cand.get("prices", {}).get("usd")
        if cand_usd_str is None:
            continue
        cand_price = float(cand_usd_str)
        if cand_price >= original_price:
            continue
        s = score_candidate(original_card, cand)
        scored.append((s, cand))

    scored.sort(key=lambda x: (-x[0], float(x[1]["prices"]["usd"])))

    results: list[Suggestion] = []
    seen_names: set[str] = set()
    for s, cand in scored[:max_suggestions * 2]:
        name = cand["name"]
        if name in seen_names:
            continue
        seen_names.add(name)
        cand_price = float(cand["prices"]["usd"])
        edhrec_rank = cand.get("edhrec_rank")
        edhrec_url = (
            f"https://edhrec.com/cards/"
            f"{name.lower().replace(' ', '-').replace(',', '')}"
            if edhrec_rank is not None else None
        )
        results.append(Suggestion(
            original_name=original_card["name"],
            original_price=original_price,
            suggested_name=name,
            suggested_price=cand_price,
            score=s,
            saving=original_price - cand_price,
            edhrec_url=edhrec_url,
        ))
        if len(results) >= max_suggestions:
            break
    return results
