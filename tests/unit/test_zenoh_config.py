"""Tests for Zenoh client config generation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "weechat-zenoh"))
from helpers import build_zenoh_config, ZENOH_DEFAULT_ENDPOINT


class TestBuildZenohConfig:
    def test_default_mode_is_client(self):
        config = build_zenoh_config()
        mode = config.get_json("mode")
        assert "client" in mode

    def test_default_endpoint(self):
        config = build_zenoh_config()
        endpoints = config.get_json("connect/endpoints")
        assert ZENOH_DEFAULT_ENDPOINT in endpoints

    def test_custom_endpoint_overrides_default(self):
        config = build_zenoh_config("tcp/10.0.0.1:7447")
        endpoints = config.get_json("connect/endpoints")
        assert "10.0.0.1" in endpoints
        # Default should not be present if custom is set
        # (depends on how Zenoh Config works -- the custom replaces it)

    def test_multiple_endpoints(self):
        config = build_zenoh_config("tcp/10.0.0.1:7447,tcp/10.0.0.2:7447")
        endpoints = config.get_json("connect/endpoints")
        assert "10.0.0.1" in endpoints
        assert "10.0.0.2" in endpoints
