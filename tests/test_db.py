"""Unit tests for the clip database storage layer."""

import tempfile
from pathlib import Path

import pytest

from clipd.db import ClipDatabase
from clip_common.types import ContentType


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_clips.db"
    database = ClipDatabase(db_path=db_path)
    yield database
    database.close()


class TestInsertAndRetrieve:
    def test_insert_and_get_recent(self, db):
        entry = db.insert_clip("hello world")
        assert entry is not None
        assert entry.content == "hello world"
        assert entry.content_type == ContentType.TEXT

        recent = db.get_recent(10)
        assert len(recent) == 1
        assert recent[0].content == "hello world"

    def test_insert_multiple_ordered_by_recency(self, db):
        db.insert_clip("first")
        db.insert_clip("second")
        db.insert_clip("third")

        recent = db.get_recent(10)
        assert len(recent) == 3
        assert recent[0].content == "third"
        assert recent[1].content == "second"
        assert recent[2].content == "first"


class TestDeduplication:
    def test_duplicate_skipped(self, db):
        entry1 = db.insert_clip("same text")
        entry2 = db.insert_clip("same text")
        assert entry1 is not None
        assert entry2 is None
        assert db.count() == 1

    def test_different_content_not_deduped(self, db):
        db.insert_clip("text one")
        db.insert_clip("text two")
        assert db.count() == 2

    def test_same_content_after_different_not_deduped(self, db):
        db.insert_clip("hello")
        db.insert_clip("world")
        entry3 = db.insert_clip("hello")
        assert entry3 is not None
        assert db.count() == 3


class TestPruning:
    def test_prune_to_max(self, db):
        for i in range(501):
            db.insert_clip(f"clip {i}")
        assert db.count() == 501

        db.delete_old(max_entries=500)
        assert db.count() == 500

        # Most recent should survive
        recent = db.get_recent(1)
        assert recent[0].content == "clip 500"

    def test_pinned_survive_pruning(self, db):
        for i in range(10):
            db.insert_clip(f"clip {i}")

        # Pin the oldest clip
        oldest = db.get_recent(10)[-1]
        db.pin(oldest.id)

        db.delete_old(max_entries=5)

        # Pinned clip should survive
        pinned_entry = db.get_by_id(oldest.id)
        assert pinned_entry is not None
        assert pinned_entry.pinned is True

        # Total count: 5 unpinned + 1 pinned = 6
        assert db.count() == 6


class TestSearch:
    def test_fts_search(self, db):
        db.insert_clip("the quick brown fox")
        db.insert_clip("lazy dog sleeps")
        db.insert_clip("fox and dog are friends")

        results = db.search("fox")
        assert len(results) == 2
        contents = [r.content for r in results]
        assert "the quick brown fox" in contents
        assert "fox and dog are friends" in contents

    def test_search_no_results(self, db):
        db.insert_clip("hello world")
        results = db.search("zebra")
        assert len(results) == 0


class TestPinUnpin:
    def test_pin_and_unpin(self, db):
        entry = db.insert_clip("pin me")
        db.pin(entry.id)

        fetched = db.get_by_id(entry.id)
        assert fetched.pinned is True

        db.unpin(entry.id)
        fetched = db.get_by_id(entry.id)
        assert fetched.pinned is False
