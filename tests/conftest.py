"""
Shared test fixtures for weechat-claude tests.
"""

import sys
import os
import pytest

# Add project root for wc_protocol
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Add weechat-channel-server to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                "..", "weechat-channel-server"))


class MockZenohSession:
    """Mock Zenoh session for unit testing."""

    def __init__(self):
        self.published = []  # list of (key, payload) tuples

    def put(self, key: str, payload: str):
        self.published.append((key, payload))

    def declare_publisher(self, key: str):
        return MockPublisher(key, self)

    def declare_subscriber(self, key, handler):
        return MockSubscriber(key, handler)

    def liveliness(self):
        return MockLiveliness()

    def close(self):
        pass


class MockPublisher:
    def __init__(self, key, session):
        self.key = key
        self._session = session

    def put(self, payload):
        self._session.published.append((self.key, payload))

    def undeclare(self):
        pass


class MockSubscriber:
    def __init__(self, key, handler):
        self.key = key
        self.handler = handler

    def undeclare(self):
        pass


class MockLiveliness:
    def declare_token(self, key):
        return MockToken()

    def declare_subscriber(self, key, handler):
        return MockSubscriber(key, handler)

    def get(self, key):
        return []


class MockToken:
    def undeclare(self):
        pass


@pytest.fixture
def mock_zenoh_session():
    """Provide a mock Zenoh session."""
    return MockZenohSession()


@pytest.fixture
def agent_name():
    """Default agent name for tests (scoped to creator per issue #2)."""
    return "alice:agent0"
