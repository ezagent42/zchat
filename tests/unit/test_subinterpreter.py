"""Verify WeeChat plugin files have no PyO3-dependent imports.

WeeChat runs Python plugins in subinterpreters. PyO3-based modules
(zenoh, pydantic, etc.) crash in subinterpreters. This test catches
the issue at CI time instead of at runtime inside WeeChat.
"""
import ast
import os

PLUGIN_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "weechat-zenoh")

# Modules known to use PyO3 (will crash in subinterpreter)
PYO3_MODULES = {"zenoh", "pydantic", "pydantic_core", "orjson"}


def _get_imports(filepath: str) -> set[str]:
    """Extract top-level module names from all import statements."""
    with open(filepath) as f:
        tree = ast.parse(f.read(), filename=filepath)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def test_weechat_zenoh_no_pyo3_imports():
    """weechat-zenoh.py must not import any PyO3-based module."""
    plugin_file = os.path.join(PLUGIN_DIR, "weechat-zenoh.py")
    imports = _get_imports(plugin_file)
    bad = imports & PYO3_MODULES
    assert not bad, (
        f"weechat-zenoh.py imports PyO3 modules {bad} which crash in "
        f"WeeChat's subinterpreter. Move these to zenoh_sidecar.py.")


def test_wc_protocol_no_pyo3_imports():
    """wc_protocol/ must not import any PyO3-based module."""
    protocol_dir = os.path.join(os.path.dirname(__file__), "..", "..", "wc_protocol")
    for fname in os.listdir(protocol_dir):
        if fname.endswith(".py"):
            imports = _get_imports(os.path.join(protocol_dir, fname))
            bad = imports & PYO3_MODULES
            assert not bad, (
                f"wc_protocol/{fname} imports PyO3 modules {bad} which crash in "
                f"WeeChat's subinterpreter.")
