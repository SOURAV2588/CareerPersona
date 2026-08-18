import os, pytest

pytestmark = [pytest.mark.db,
              pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),
                                 reason="TEST_DATABASE_URL not set")]


@pytest.fixture(autouse=True)
def clean_table(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    import services.db as db
    db._pool = None                      # force a fresh pool on the test DSN
    db.init_db()
    with db.get_pool().connection() as conn:
        conn.execute("TRUNCATE unknown_questions RESTART IDENTITY")
    yield