"""Shared test fixtures for zchat tests."""
import pytest


@pytest.fixture
def agent_name():
    """Default agent name for tests (scoped to creator per issue #2)."""
    return "alice-agent0"
