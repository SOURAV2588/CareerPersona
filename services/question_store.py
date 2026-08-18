"""File-based storage for unanswered questions.

The chat handler appends questions here as they come in; the daily digest
job (running on a background scheduler thread) reads and clears them. A
plain JSONL file is used so questions survive app restarts and need no
extra dependency.

.. note::
   This module is superseded by :mod:`services.question_store_db`, which
   stores questions in PostgreSQL instead. See ``services/digest.py`` for
   which store is currently wired up.
"""

import json
import os
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PENDING_FILE = os.path.join(DATA_DIR, "unknown_questions.jsonl")
ARCHIVE_FILE = os.path.join(DATA_DIR, "sent_questions.jsonl")

def store_question(question):
    """
    Append a single unanswered question to the pending store.

    Creates ``DATA_DIR`` if it does not yet exist. Each entry is written as
    one JSON object per line, with a UTC ISO-8601 timestamp attached.

    :param question: The unanswered question to store.
    :type question: str
    :return: None
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    entry = {"question": question, "timestamp": datetime.now(timezone.utc).isoformat()}
    with open(PENDING_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_pending():
    """
    Return all pending questions as a list of dicts ([] if none).

    Reads and parses ``PENDING_FILE`` line by line; returns an empty list
    if the file does not exist yet.

    :return: A list of dictionaries, each with ``question`` and
        ``timestamp`` keys.
    :rtype: list[dict]
    """
    if not os.path.exists(PENDING_FILE):
        return []
    entries = []
    with open(PENDING_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def clear_pending(entries):
    """
    Archive the given entries and truncate the pending store.

    Called only after a digest has been sent successfully, so questions are
    never lost if sending fails.

    :param entries: The pending-question dicts to append to
        ``ARCHIVE_FILE``. If empty, nothing is written to the archive, but
        the pending file is still truncated.
    :type entries: list[dict]
    :return: None
    """
    if entries:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ARCHIVE_FILE, "a", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
    open(PENDING_FILE, "w", encoding="utf-8").close()
