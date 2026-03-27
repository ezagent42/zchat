"""Shared fixtures for integration tests requiring a real IRC server.

Start ergo before running: `zchat irc daemon start`
"""

import pytest


@pytest.fixture
def irc_server_address():
    """IRC server connection details for integration tests."""
    return {"host": "127.0.0.1", "port": 6667}
