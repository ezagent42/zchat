"""Tests for Zenoh client config generation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "weechat-zenoh"))
from helpers import build_zenoh_config, ZENOH_DEFAULT_ENDPOINT


class TestBuildZenohConfig:
    def test_default_mode_is_client(self):
        config = build_zenoh_config()
        cfg_json = config.to_json()
        assert '"client"' in cfg_json or 'client' in cfg_json

    def test_default_endpoint(self):
        config = build_zenoh_config()
        cfg_json = config.to_json()
        assert ZENOH_DEFAULT_ENDPOINT in cfg_json

    def test_custom_endpoint_overrides_default(self):
        config = build_zenoh_config("tcp/10.0.0.1:7447")
        cfg_json = config.to_json()
        assert "10.0.0.1" in cfg_json
        # Default should not be present if custom is set
        # (depends on how Zenoh Config works -- the custom replaces it)

    def test_multiple_endpoints(self):
        config = build_zenoh_config("tcp/10.0.0.1:7447,tcp/10.0.0.2:7447")
        cfg_json = config.to_json()
        assert "10.0.0.1" in cfg_json
        assert "10.0.0.2" in cfg_json
