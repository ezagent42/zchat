"""Verify wc_protocol.config has no zenoh import (PyO3 safe)."""
import importlib


def test_config_has_no_zenoh_import():
    """wc_protocol.config must not import zenoh (PyO3 incompatible)."""
    import ast
    source = importlib.util.find_spec("wc_protocol.config").origin
    with open(source) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "zenoh"
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] != "zenoh"


def test_topics_has_no_zenoh_import():
    """wc_protocol.topics must not import zenoh (PyO3 incompatible)."""
    source = importlib.util.find_spec("wc_protocol.topics").origin
    with open(source) as f:
        content = f.read()
    assert "import zenoh" not in content
