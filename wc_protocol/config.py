"""Zenoh configuration constants and builders.

NOTE: This module does NOT import zenoh. It produces plain dicts
that callers apply to zenoh.Config() themselves. This keeps the
module safe for WeeChat subinterpreters.
"""

ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"


def build_zenoh_config_dict(connect: str | None = None) -> dict:
    """Build a Zenoh client config as a plain dict.

    Args:
        connect: Comma-separated endpoint list, or None for default.

    Returns:
        Dict with keys 'mode' and 'connect/endpoints' ready to be
        applied via zenoh.Config.insert_json5().
    """
    endpoints = connect.split(",") if connect else [ZENOH_DEFAULT_ENDPOINT]
    return {
        "mode": "client",
        "connect/endpoints": endpoints,
    }
