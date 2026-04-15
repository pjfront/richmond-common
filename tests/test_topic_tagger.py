"""Tests for topic tagger — keyword-based topic assignment for agenda items."""

import uuid
from unittest.mock import MagicMock, patch, call

import pytest
import topic_tagger as tt
from topic_tagger import (
    tag_topics,
    TopicMatch,
    TopicDef,
    TOPIC_DEFS,
    _get_topic_id_map,
    load_item_topics_to_db,
    backfill_topics,
    load_topic_defs_from_db,
    reload_topic_defs,
    _get_active_topic_defs,
)


@pytest.fixture(autouse=True)
def _reset_topic_defs_cache():
    """Clear the module-level DB cache between tests so each test starts clean."""
    tt._TOPIC_DEFS_CACHE = None
    yield
    tt._TOPIC_DEFS_CACHE = None


# ── tag_topics: keyword matching ──


class TestTagTopics:
    """Core keyword matching logic."""

    def test_chevron_match(self):
        matches = tag_topics("Approve Chevron refinery air quality permit")
        slugs = [m.slug for m in matches]
        assert "chevron" in slugs

    def test_multi_topic_match(self):
        """An item can match multiple topics."""
        matches = tag_topics("Chevron refinery emissions air quality monitoring")
        slugs = [m.slug for m in matches]
        assert "chevron" in slugs
        assert "environment" in slugs

    def test_point_molate_variations(self):
        for text in ["Point Molate development", "Pt. Molate shoreline", "Pt Molate Navy"]:
            matches = tag_topics(text)
            assert any(m.slug == "point-molate" for m in matches), f"Failed for: {text}"

    def test_rent_board(self):
        matches = tag_topics("Rent Board annual adjustment hearing")
        assert any(m.slug == "rent-board" for m in matches)

    def test_police_reform(self):
        matches = tag_topics("Community Police Review Commission report")
        assert any(m.slug == "police-reform" for m in matches)

    def test_cannabis(self):
        matches = tag_topics("Cannabis dispensary permit application")
        assert any(m.slug == "cannabis" for m in matches)

    def test_housing_development(self):
        matches = tag_topics("Affordable housing element compliance update")
        assert any(m.slug == "housing-development" for m in matches)

    def test_political_statements(self):
        matches = tag_topics("Resolution opposing military intervention")
        assert any(m.slug == "political-statements" for m in matches)

    def test_labor(self):
        matches = tag_topics("SEIU Local 1021 memorandum of understanding")
        assert any(m.slug == "labor" for m in matches)

    def test_hilltop(self):
        matches = tag_topics("Hilltop Mall redevelopment plan")
        assert any(m.slug == "hilltop" for m in matches)

    def test_no_match(self):
        """Generic items should return empty."""
        matches = tag_topics("Approve minutes of previous meeting")
        assert matches == []

    def test_empty_text(self):
        assert tag_topics("") == []

    def test_none_text(self):
        assert tag_topics(None) == []

    def test_case_insensitive(self):
        matches = tag_topics("CHEVRON REFINERY PERMIT")
        assert any(m.slug == "chevron" for m in matches)


class TestConfidenceScoring:
    """Confidence is higher when multiple keywords match."""

    def test_single_keyword_lower_confidence(self):
        """One keyword match → 0.8 confidence."""
        matches = tag_topics("Something about cannabis regulations")
        cannabis = next(m for m in matches if m.slug == "cannabis")
        assert cannabis.confidence == 0.8

    def test_multi_keyword_full_confidence(self):
        """Two+ keyword matches → 1.0 confidence."""
        matches = tag_topics("Cannabis dispensary license application")
        cannabis = next(m for m in matches if m.slug == "cannabis")
        assert cannabis.confidence == 1.0

    def test_matched_keywords_tracked(self):
        """TopicMatch records which keywords hit."""
        matches = tag_topics("Chevron refinery flaring report")
        chevron = next(m for m in matches if m.slug == "chevron")
        assert "chevron" in chevron.matched_keywords
        assert "refinery" in chevron.matched_keywords
        assert chevron.source == "keyword"


class TestCustomTopicDefs:
    """Can pass custom topic definitions for testing."""

    def test_custom_defs(self):
        custom = [TopicDef(slug="test", name="Test", keywords=["foobar"])]
        matches = tag_topics("This is a foobar item", topic_defs=custom)
        assert len(matches) == 1
        assert matches[0].slug == "test"


# ── Topic definition coverage ──


class TestTopicDefinitions:
    """Verify all 14 Richmond local issues are defined."""

    EXPECTED_SLUGS = {
        "chevron", "point-molate", "rent-board", "hilltop",
        "terminal-port", "ford-point", "macdonald", "police-reform",
        "environment", "labor", "cannabis", "youth",
        "political-statements", "housing-development",
    }

    def test_all_14_topics_defined(self):
        slugs = {t.slug for t in TOPIC_DEFS}
        assert slugs == self.EXPECTED_SLUGS

    def test_all_topics_have_keywords(self):
        for topic in TOPIC_DEFS:
            assert len(topic.keywords) > 0, f"{topic.slug} has no keywords"

    def test_all_topics_have_primary_category(self):
        for topic in TOPIC_DEFS:
            assert topic.primary_category, f"{topic.slug} has no primary_category"

    def test_no_duplicate_slugs(self):
        slugs = [t.slug for t in TOPIC_DEFS]
        assert len(slugs) == len(set(slugs))


# ── Database operations (mocked) ──


class TestGetTopicIdMap:
    def test_returns_slug_to_id_map(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.return_value = [
            ("chevron", "uuid-1"),
            ("environment", "uuid-2"),
        ]
        result = _get_topic_id_map(mock_conn, "0660620")
        assert result == {"chevron": "uuid-1", "environment": "uuid-2"}


class TestLoadItemTopics:
    def test_saves_matches(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value

        matches = [
            TopicMatch(slug="chevron", confidence=1.0, source="keyword"),
            TopicMatch(slug="environment", confidence=0.8, source="keyword"),
        ]
        topic_map = {"chevron": "topic-uuid-1", "environment": "topic-uuid-2"}

        saved = load_item_topics_to_db(mock_conn, "item-uuid", matches, topic_map)
        assert saved == 2
        assert mock_cur.execute.call_count == 2

    def test_skips_unknown_slugs(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value

        matches = [TopicMatch(slug="unknown-topic", confidence=1.0)]
        topic_map = {"chevron": "topic-uuid-1"}

        saved = load_item_topics_to_db(mock_conn, "item-uuid", matches, topic_map)
        assert saved == 0
        assert mock_cur.execute.call_count == 0

    def test_empty_matches(self):
        mock_conn = MagicMock()
        saved = load_item_topics_to_db(mock_conn, "item-uuid", [], {})
        assert saved == 0


class TestLoadTopicDefsFromDb:
    """DB-backed topic taxonomy loader added in S28.0."""

    def test_returns_topicdefs_from_db_rows(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.return_value = [
            ("chevron", "Chevron & the Refinery",
             ["chevron", "refinery", "flaring"], "environment"),
            ("housing-development", "Housing & Homelessness",
             ["affordable housing", "homelessness"], "housing"),
        ]
        defs = load_topic_defs_from_db(conn=mock_conn, city_fips="0660620")
        assert len(defs) == 2
        assert defs[0].slug == "chevron"
        assert defs[0].name == "Chevron & the Refinery"
        assert "flaring" in defs[0].keywords
        assert defs[0].primary_category == "environment"
        assert defs[1].slug == "housing-development"

    def test_populates_module_cache(self):
        assert tt._TOPIC_DEFS_CACHE is None
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.return_value = [
            ("test-topic", "Test", ["keyword"], "governance"),
        ]
        load_topic_defs_from_db(conn=mock_conn)
        assert tt._TOPIC_DEFS_CACHE is not None
        assert len(tt._TOPIC_DEFS_CACHE) == 1
        assert tt._TOPIC_DEFS_CACHE[0].slug == "test-topic"

    def test_reload_refreshes_cache(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.side_effect = [
            [("chevron", "Chevron", ["chevron"], "environment")],
            [("chevron", "Chevron", ["chevron"], "environment"),
             ("new-topic", "New Topic", ["new"], "governance")],
        ]
        first = load_topic_defs_from_db(conn=mock_conn)
        assert len(first) == 1
        second = reload_topic_defs(conn=mock_conn)
        assert len(second) == 2
        assert any(t.slug == "new-topic" for t in second)

    def test_query_filters_by_city_fips_and_status(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.return_value = []
        load_topic_defs_from_db(conn=mock_conn, city_fips="0660620")
        # The SQL must filter by both city_fips and status='active'
        query_sql = mock_cur.execute.call_args[0][0]
        assert "city_fips" in query_sql
        assert "'active'" in query_sql.lower() or "status" in query_sql.lower()
        # Must only select the four TopicDef fields
        assert "slug" in query_sql
        assert "name" in query_sql
        assert "keywords" in query_sql
        assert "primary_category" in query_sql

    def test_get_active_returns_cache_when_populated(self):
        cached = [TopicDef(slug="cached", name="Cached", keywords=["c"], primary_category="x")]
        tt._TOPIC_DEFS_CACHE = cached
        result = _get_active_topic_defs()
        assert result is cached

    def test_get_active_falls_back_to_hardcoded_when_db_fails(self):
        """When no cache and DB is unreachable, fall back to hardcoded TOPIC_DEFS."""
        tt._TOPIC_DEFS_CACHE = None
        with patch("topic_tagger.load_topic_defs_from_db", side_effect=RuntimeError("no db")):
            result = _get_active_topic_defs()
        assert result is TOPIC_DEFS
        # Fallback must NOT populate the cache — so a later successful load still wins
        assert tt._TOPIC_DEFS_CACHE is None


class TestBackfillTopics:
    def test_dry_run_does_not_write(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value

        # First call: _get_topic_id_map
        # Second call: fetch agenda items
        mock_cur.fetchall.side_effect = [
            [("chevron", "topic-uuid-1")],  # topic map
            [("item-1", "Chevron refinery permit")],  # agenda items
        ]

        stats = backfill_topics(mock_conn, dry_run=True)
        assert stats["items_scanned"] == 1
        assert stats["items_tagged"] == 1
        assert stats["assignments_created"] >= 1
        # No commit on dry run
        mock_conn.commit.assert_not_called()

    def test_no_topics_returns_early(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.return_value = []  # no topics

        stats = backfill_topics(mock_conn)
        assert stats["items_scanned"] == 0

    def test_limit_param(self):
        mock_conn = MagicMock()
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.side_effect = [
            [("chevron", "topic-uuid-1")],  # topic map
            [],  # agenda items (empty for this test)
        ]

        backfill_topics(mock_conn, limit=10)
        # Check that LIMIT was in the query
        calls = mock_cur.execute.call_args_list
        # Second execute call is the agenda items query
        query_str = calls[1][0][0]
        assert "LIMIT" in query_str
