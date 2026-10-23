"""Database-backed conversation memory against a REAL Postgres (not the FakeConversationStore
used elsewhere) - skipped unless TEST_DATABASE_URL is set, exactly like the other integration
tests. Uses its own scratch schema and drops it afterwards; never touches the RAG chunk/document
tables, which this feature was explicitly required not to damage.
"""
import pytest
from sqlalchemy import text

from backend.database.connection import get_engine
from backend.database.conversations import ConversationStore
from backend.database.schema import render_migrations


@pytest.fixture
def store(real_env, make_settings):
    url = real_env.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    s = make_settings(supabase_db_url=url, db_schema="rag_conv_it")
    engine = get_engine(s)
    with engine.begin() as conn:
        conn.execute(text("drop schema if exists rag_conv_it cascade"))
    for sql in render_migrations(s).values():
        with engine.begin() as conn:
            conn.exec_driver_sql(sql.replace("%", "%%"))
    yield ConversationStore(engine, s)
    with engine.begin() as conn:
        conn.execute(text("drop schema if exists rag_conv_it cascade"))


def test_rls_is_enabled_on_the_new_tables(store):
    schema = store.conversations.split(".")[0]
    rows = store._run(
        """select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = :s and c.relname in ('conversations', 'messages')""",
        {"s": schema}, fetch=True,
    )
    assert {r["relname"]: r["relrowsecurity"] for r in rows} == {"conversations": True, "messages": True}


def test_round_trip_a_multi_turn_conversation(store):
    sid = "it-session-1"
    store.add_message(sid, "user", "Tell me about the Banarasi Silk Dupatta.")
    store.add_message(sid, "assistant", "It is a silk dupatta from Varanasi.", product_ids=[1], sources=["product/01_x.docx"])
    store.add_message(sid, "user", "What is its price?")
    store.add_message(sid, "assistant", "It costs ₹4,200.", product_ids=[1])

    messages = store.recent_messages(sid, limit=10)
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0]["content"] == "Tell me about the Banarasi Silk Dupatta."
    assert messages[1]["product_ids"] == [1]
    assert store.last_product_ids(sid) == [1]
    assert store.session_exists(sid) is True
    assert store.session_exists("never-created") is False


def test_recent_messages_respects_the_limit_and_stays_in_order(store):
    sid = "it-session-2"
    for i in range(5):
        store.add_message(sid, "user", f"question {i}")
        store.add_message(sid, "assistant", f"answer {i}")

    last_four = store.recent_messages(sid, limit=4)
    assert [m["content"] for m in last_four] == ["question 3", "answer 3", "question 4", "answer 4"]
