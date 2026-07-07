"""Tests for session_store.py — thread-safe session ID store."""

import time

from tracey.slack_agent.session_store import SessionStore


class TestSessionStore:
    def itShould_return_None_for_unknown_session(self):
        store = SessionStore(ttl_seconds=10, max_entries=5)
        result = store.get_session("C123", "ts.001")
        assert result is None

    def itShould_store_and_retrieve_session(self):
        store = SessionStore(ttl_seconds=10, max_entries=5)
        store.set_session("C123", "ts.001", "session_abc")
        result = store.get_session("C123", "ts.001")
        assert result == "session_abc"

    def itShould_return_None_after_expiry(self):
        store = SessionStore(ttl_seconds=-1, max_entries=5)
        store.set_session("C123", "ts.001", "session_abc")
        result = store.get_session("C123", "ts.001")
        assert result is None

    def itShould_differentiate_by_channel(self):
        store = SessionStore(ttl_seconds=10, max_entries=5)
        store.set_session("C123", "ts.001", "session_a")
        store.set_session("C456", "ts.001", "session_b")
        assert store.get_session("C123", "ts.001") == "session_a"
        assert store.get_session("C456", "ts.001") == "session_b"

    def itShould_differentiate_by_thread_ts(self):
        store = SessionStore(ttl_seconds=10, max_entries=5)
        store.set_session("C123", "ts.001", "session_a")
        store.set_session("C123", "ts.002", "session_b")
        assert store.get_session("C123", "ts.001") == "session_a"
        assert store.get_session("C123", "ts.002") == "session_b"

    def itShould_evict_oldest_when_over_max_entries(self):
        store = SessionStore(ttl_seconds=3600, max_entries=3)
        store.set_session("C1", "t1", "s1")
        time.sleep(0.01)
        store.set_session("C2", "t2", "s2")
        time.sleep(0.01)
        store.set_session("C3", "t3", "s3")
        time.sleep(0.01)
        store.set_session("C4", "t4", "s4")

        assert store.get_session("C1", "t1") is None
        assert store.get_session("C2", "t2") == "s2"
        assert store.get_session("C3", "t3") == "s3"
        assert store.get_session("C4", "t4") == "s4"

    def itShould_replace_existing_session(self):
        store = SessionStore(ttl_seconds=10, max_entries=5)
        store.set_session("C123", "ts.001", "session_a")
        store.set_session("C123", "ts.001", "session_b")
        result = store.get_session("C123", "ts.001")
        assert result == "session_b"
