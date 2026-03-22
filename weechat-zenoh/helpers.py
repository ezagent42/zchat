"""Pure helper functions extracted from weechat-zenoh for testability."""

ZENOH_DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"

def build_zenoh_config(connect: str | None = None):
    """Build Zenoh client config. Connects to local zenohd by default."""
    import zenoh
    import json
    config = zenoh.Config()
    config.insert_json5("mode", '"client"')
    if connect:
        config.insert_json5("connect/endpoints", json.dumps(connect.split(",")))
    else:
        config.insert_json5("connect/endpoints", f'["{ZENOH_DEFAULT_ENDPOINT}"]')
    return config


def target_to_buffer_label(target: str, my_nick: str) -> str:
    """Convert internal target key to WeeChat-style buffer label.
    'channel:general' → 'channel:#general'
    'private:alice_bob' → 'private:@alice' (the other nick)
    """
    if target.startswith("channel:"):
        return f"channel:#{target[8:]}"
    pair = target.split(":", 1)[1]
    nicks = pair.split("_")
    other = [n for n in nicks if n != my_nick]
    return f"private:@{other[0]}" if other else f"private:@{pair}"


def parse_input(input_data: str) -> tuple[str, str]:
    """Parse user input into (msg_type, body).
    '/me waves' → ('action', 'waves')
    'hello' → ('msg', 'hello')
    """
    if input_data.startswith("/me ") or input_data == "/me":
        body = input_data[4:] if len(input_data) > 4 else ""
        return ("action", body)
    return ("msg", input_data)
