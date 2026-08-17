"""Tests for services.question_store — the JSONL-backed pending/archive store."""

import json

import pytest

from services import question_store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Point the module's file paths at a throwaway directory for every test."""
    pending = tmp_path / "unknown_questions.jsonl"
    archive = tmp_path / "sent_questions.jsonl"
    monkeypatch.setattr(question_store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(question_store, "PENDING_FILE", str(pending))
    monkeypatch.setattr(question_store, "ARCHIVE_FILE", str(archive))
    return pending, archive


def test_read_pending_returns_empty_list_when_file_missing():
    assert question_store.read_pending() == []


def test_store_question_creates_data_dir_and_appends_entry(isolated_store):
    question_store.store_question("What is your favorite language?")

    entries = question_store.read_pending()
    assert len(entries) == 1
    assert entries[0]["question"] == "What is your favorite language?"
    assert "timestamp" in entries[0]
    # ISO-8601 timestamps parse cleanly and round-trip.
    from datetime import datetime
    datetime.fromisoformat(entries[0]["timestamp"])


def test_store_question_appends_multiple_in_order():
    question_store.store_question("first")
    question_store.store_question("second")
    question_store.store_question("third")

    entries = question_store.read_pending()
    assert [e["question"] for e in entries] == ["first", "second", "third"]


def test_read_pending_skips_blank_lines(isolated_store):
    pending, _ = isolated_store
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(
        json.dumps({"question": "a", "timestamp": "t"}) + "\n"
        "\n"
        "   \n"
        + json.dumps({"question": "b", "timestamp": "t"}) + "\n",
        encoding="utf-8",
    )

    entries = question_store.read_pending()
    assert [e["question"] for e in entries] == ["a", "b"]


def test_clear_pending_archives_entries_and_truncates_pending(isolated_store):
    pending, archive = isolated_store
    question_store.store_question("q1")
    question_store.store_question("q2")
    entries = question_store.read_pending()

    question_store.clear_pending(entries)

    assert question_store.read_pending() == []
    archived = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()]
    assert [e["question"] for e in archived] == ["q1", "q2"]


def test_clear_pending_appends_to_existing_archive_without_overwriting(isolated_store):
    pending, archive = isolated_store
    question_store.store_question("q1")
    question_store.clear_pending(question_store.read_pending())

    question_store.store_question("q2")
    question_store.clear_pending(question_store.read_pending())

    archived = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()]
    assert [e["question"] for e in archived] == ["q1", "q2"]


def test_clear_pending_with_empty_list_still_truncates_pending_file(isolated_store):
    pending, archive = isolated_store
    question_store.store_question("orphaned")

    question_store.clear_pending([])

    assert question_store.read_pending() == []
    # No entries were passed in, so nothing should have been archived.
    assert not archive.exists()
