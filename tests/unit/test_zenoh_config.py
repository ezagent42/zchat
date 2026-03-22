"""Verify build_zenoh_config was removed from helpers (moved to sidecar)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "weechat-zenoh"))
import helpers


def test_build_zenoh_config_removed_from_helpers():
    assert not hasattr(helpers, "build_zenoh_config"), \
        "build_zenoh_config should be in zenoh_sidecar.py, not helpers.py"


def test_helpers_has_no_zenoh_import():
    """helpers.py must not import zenoh (PyO3 incompatible)."""
    import importlib
    source = importlib.util.find_spec("helpers").origin
    with open(source) as f:
        content = f.read()
    assert "import zenoh" not in content
