from __future__ import annotations

import pytest

from mtg_prices.suggest import (
    classify_roles,
    extract_oracle_keywords,
    find_suggestions,
    score_candidate,
    score_cmc,
    score_edhrec_rank,
    score_keywords,
    score_oracle_text,
    score_power_toughness,
    score_roles,
)

# ---------------------------------------------------------------------------
# Mock card data
# ---------------------------------------------------------------------------

SWORDS = {
    "name": "Swords to Plowshares",
    "type_line": "Instant",
    "color_identity": ["W"],
    "cmc": 1.0,
    "oracle_text": (
        "Exile target creature. Its controller gains life equal to its power."
    ),
    "keywords": [],
    "edhrec_rank": 5,
    "legalities": {"commander": "legal"},
    "prices": {"usd": "1.50"},
}

PATH_TO_EXILE = {
    "name": "Path to Exile",
    "type_line": "Instant",
    "color_identity": ["W"],
    "cmc": 1.0,
    "oracle_text": (
        "Exile target creature. Its controller may search their library "
        "for a basic land card, put that card onto the battlefield tapped, "
        "then shuffle."
    ),
    "keywords": [],
    "edhrec_rank": 10,
    "legalities": {"commander": "legal"},
    "prices": {"usd": "1.00"},
}

MURDER = {
    "name": "Murder",
    "type_line": "Instant",
    "color_identity": ["B"],
    "cmc": 3.0,
    "oracle_text": "Destroy target creature.",
    "keywords": [],
    "edhrec_rank": 200,
    "legalities": {"commander": "legal"},
    "prices": {"usd": "0.10"},
}


# ---------------------------------------------------------------------------
# TestExtractOracleKeywords
# ---------------------------------------------------------------------------


class TestExtractOracleKeywords:
    def test_destroy(self):
        result = extract_oracle_keywords("Destroy target creature.")
        assert "destroy" in result

    def test_draw(self):
        result = extract_oracle_keywords("Draw a card.")
        assert "draw" in result

    def test_multiple(self):
        result = extract_oracle_keywords("Destroy target creature. Draw a card.")
        assert "destroy" in result
        assert "draw" in result

    def test_empty(self):
        assert extract_oracle_keywords("") == set()

    def test_none(self):
        assert extract_oracle_keywords(None) == set()


# ---------------------------------------------------------------------------
# TestScoreCmc
# ---------------------------------------------------------------------------


class TestScoreCmc:
    def test_exact_match(self):
        assert score_cmc(3.0, 3.0) == 2

    def test_off_by_one(self):
        assert score_cmc(3.0, 4.0) == 1

    def test_off_by_two(self):
        assert score_cmc(3.0, 5.0) == 0

    def test_too_far(self):
        assert score_cmc(1.0, 6.0) == 0


# ---------------------------------------------------------------------------
# TestScoreEdhrecRank
# ---------------------------------------------------------------------------


class TestScoreEdhrecRank:
    def test_rank_1(self):
        assert score_edhrec_rank(1) == pytest.approx(2.0, abs=0.01)

    def test_rank_5000(self):
        assert score_edhrec_rank(5000) == pytest.approx(1.0)

    def test_rank_10000(self):
        assert score_edhrec_rank(10000) == 0.0

    def test_above_10000(self):
        assert score_edhrec_rank(20000) == 0.0

    def test_none(self):
        assert score_edhrec_rank(None) == 0.0


# ---------------------------------------------------------------------------
# TestScoreKeywords
# ---------------------------------------------------------------------------


class TestScoreKeywords:
    def test_shared(self):
        assert score_keywords(["flying"], ["flying"]) == 2

    def test_no_shared(self):
        assert score_keywords(["flying"], ["trample"]) == 0

    def test_empty(self):
        assert score_keywords([], []) == 0

    def test_capped_at_4(self):
        kws = ["flying", "trample", "haste", "vigilance", "menace"]
        assert score_keywords(kws, kws) == 4


# ---------------------------------------------------------------------------
# TestScoreOracleText
# ---------------------------------------------------------------------------


class TestScoreOracleText:
    def test_shared(self):
        assert (
            score_oracle_text("Destroy target creature.", "Destroy all creatures.") == 3
        )

    def test_no_shared(self):
        assert score_oracle_text("Draw a card.", "Gain 3 life.") == 0

    def test_capped_at_6(self):
        text = (
            "Destroy target creature. Exile it. Draw a card. "
            "Sacrifice a token. Discard a card. Counter target spell. "
            "Search your library. Mill two cards."
        )
        assert score_oracle_text(text, text) == 6


# ---------------------------------------------------------------------------
# TestScorePowerToughness
# ---------------------------------------------------------------------------


class TestScorePowerToughness:
    def test_exact(self):
        assert score_power_toughness("3", "3", "3", "3") == 1

    def test_close(self):
        assert score_power_toughness("3", "3", "4", "2") == 1

    def test_far(self):
        assert score_power_toughness("3", "3", "6", "6") == 0

    def test_non_numeric(self):
        assert score_power_toughness("*", "*", "3", "3") == 0

    def test_none(self):
        assert score_power_toughness(None, None, "3", "3") == 0


# ---------------------------------------------------------------------------
# TestClassifyRoles
# ---------------------------------------------------------------------------


class TestClassifyRoles:
    def test_tutor(self):
        text = "Search your library for a card and put it into your hand."
        assert "tutor" in classify_roles(text)

    def test_removal(self):
        text = "Destroy target creature."
        assert "removal" in classify_roles(text)

    def test_board_wipe(self):
        text = "Destroy all creatures."
        assert "board_wipe" in classify_roles(text)

    def test_card_draw(self):
        text = "Draw a card."
        assert "card_draw" in classify_roles(text)

    def test_ramp(self):
        text = "{T}: Add {B}{B}."
        assert "ramp" in classify_roles(text)

    def test_lifedrain(self):
        text = "Each opponent loses 2 life and you gain life equal to the life lost."
        roles = classify_roles(text)
        assert "lifedrain" in roles
        assert "lifegain" in roles

    def test_graveyard_hate(self):
        text = "Exile target card from a graveyard."
        assert "graveyard_hate" in classify_roles(text)

    def test_multiple_roles(self):
        text = "Search your library for a card. Draw a card."
        roles = classify_roles(text)
        assert "tutor" in roles
        assert "card_draw" in roles

    def test_empty(self):
        assert classify_roles("") == set()

    def test_none(self):
        assert classify_roles(None) == set()

    def test_no_match(self):
        text = "This creature gets +1/+1."
        assert classify_roles(text) == set()


# ---------------------------------------------------------------------------
# TestScoreRoles
# ---------------------------------------------------------------------------


class TestScoreRoles:
    def test_shared_role(self):
        tutor1 = "Search your library for a card."
        tutor2 = "Search your library for a creature card."
        assert score_roles(tutor1, tutor2) == 3

    def test_no_shared_role(self):
        tutor = "Search your library for a card."
        removal = "Destroy target creature."
        assert score_roles(tutor, removal) == 0

    def test_two_shared_roles(self):
        text = "Search your library for a card. Draw a card."
        assert score_roles(text, text) == 6

    def test_capped_at_6(self):
        text = (
            "Search your library for a card. Draw a card. "
            "Destroy target creature. Each opponent loses 2 life."
        )
        assert score_roles(text, text) == 6

    def test_none(self):
        assert score_roles(None, None) == 0


# ---------------------------------------------------------------------------
# TestScoreCandidate
# ---------------------------------------------------------------------------


class TestScoreCandidate:
    def test_similar_high(self):
        score = score_candidate(SWORDS, PATH_TO_EXILE)
        assert score > 5

    def test_same_role_but_different_profile(self):
        """SWORDS and MURDER share removal role but differ in CMC/color."""
        score = score_candidate(SWORDS, MURDER)
        assert score < score_candidate(SWORDS, PATH_TO_EXILE)

    def test_no_shared_role_scores_lower(self):
        """A card with no shared role should score lower than one with."""
        graveyard_hate = {
            **MURDER,
            "oracle_text": "Exile target card from a graveyard.",
            "edhrec_rank": 200,
        }
        no_role_score = score_candidate(SWORDS, graveyard_hate)
        same_role_score = score_candidate(SWORDS, PATH_TO_EXILE)
        assert no_role_score < same_role_score


# ---------------------------------------------------------------------------
# TestFindSuggestions
# ---------------------------------------------------------------------------


class TestFindSuggestions:
    def test_returns_cheaper(self):
        results = find_suggestions(SWORDS, [PATH_TO_EXILE, MURDER], "commander")
        assert len(results) > 0
        for s in results:
            assert s.suggested_price < s.original_price

    def test_filters_wrong_legality(self):
        banned_card = {
            **PATH_TO_EXILE,
            "legalities": {"commander": "banned"},
        }
        results = find_suggestions(SWORDS, [banned_card], "commander")
        assert len(results) == 0

    def test_respects_max(self):
        candidates = [
            {
                **MURDER,
                "name": f"Murder Variant {i}",
                "prices": {"usd": str(0.10 + i * 0.01)},
            }
            for i in range(10)
        ]
        results = find_suggestions(SWORDS, candidates, "commander", max_suggestions=3)
        assert len(results) <= 3

    def test_excludes_more_expensive(self):
        expensive = {**PATH_TO_EXILE, "prices": {"usd": "10.00"}}
        results = find_suggestions(SWORDS, [expensive], "commander")
        assert len(results) == 0
