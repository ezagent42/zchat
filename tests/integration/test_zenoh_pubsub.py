"""Integration test: Zenoh pub/sub round-trip.

Requires a real Zenoh session (client mode, connects to local zenohd).
"""

import json
import time
import threading
import pytest

pytestmark = pytest.mark.integration



# zenoh_sessions fixture provided by tests/integration/conftest.py


class TestZenohPubSub:
    def test_channel_message_roundtrip(self, zenoh_sessions):
        session_a, session_b = zenoh_sessions
        received = []
        topic = "wc/channels/test/messages"

        session_b.declare_subscriber(
            topic,
            lambda sample: received.append(
                json.loads(sample.payload.to_string())
            ),
        )

        # Allow subscriber to settle
        time.sleep(0.5)

        msg = {
            "id": "test-001",
            "nick": "alice",
            "type": "msg",
            "body": "hello from integration test",
            "ts": time.time(),
        }
        session_a.put(topic, json.dumps(msg))

        # Wait for message delivery
        deadline = time.time() + 2.0
        while not received and time.time() < deadline:
            time.sleep(0.1)

        assert len(received) == 1
        assert received[0]["nick"] == "alice"
        assert received[0]["body"] == "hello from integration test"

    def test_private_message_roundtrip(self, zenoh_sessions):
        session_a, session_b = zenoh_sessions
        received = []
        topic = "wc/private/alice_bob/messages"

        session_b.declare_subscriber(
            topic,
            lambda sample: received.append(
                json.loads(sample.payload.to_string())
            ),
        )

        time.sleep(0.5)

        msg = {
            "id": "private-001",
            "nick": "alice",
            "type": "msg",
            "body": "private message",
            "ts": time.time(),
        }
        session_a.put(topic, json.dumps(msg))

        deadline = time.time() + 2.0
        while not received and time.time() < deadline:
            time.sleep(0.1)

        assert len(received) == 1
        assert received[0]["body"] == "private message"

    def test_client_sees_router(self, zenoh_sessions):
        """Verify client session can see the zenohd router."""
        session_a, session_b = zenoh_sessions
        routers_a = list(session_a.info.routers_zid())
        routers_b = list(session_b.info.routers_zid())
        assert len(routers_a) >= 1, "Client A should see at least one router"
        assert len(routers_b) >= 1, "Client B should see at least one router"

    def test_liveliness_token(self, zenoh_sessions):
        session_a, session_b = zenoh_sessions
        events = []

        session_b.liveliness().declare_subscriber(
            "wc/presence/*",
            lambda sample: events.append(str(sample.key_expr)),
        )

        time.sleep(0.5)

        token = session_a.liveliness().declare_token("wc/presence/test-user")
        time.sleep(0.5)

        # Query liveliness
        replies = list(session_b.liveliness().get("wc/presence/*"))
        nicks = [str(r.ok.key_expr).rsplit("/", 1)[-1] for r in replies]
        assert "test-user" in nicks

        token.undeclare()
