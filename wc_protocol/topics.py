"""Zenoh topic builders, target key parsing, and input parsing."""


def make_private_pair(nick_a: str, nick_b: str) -> str:
    """Create a sorted private pair key from two nicknames."""
    return "_".join(sorted([nick_a, nick_b]))


def channel_topic(channel_id: str) -> str:
    """Zenoh topic for channel messages."""
    return f"wc/channels/{channel_id}/messages"


def private_topic(pair: str) -> str:
    """Zenoh topic for private messages."""
    return f"wc/private/{pair}/messages"


def presence_topic(nick: str) -> str:
    """Zenoh topic for global presence."""
    return f"wc/presence/{nick}"


def channel_presence_topic(channel_id: str, nick: str) -> str:
    """Zenoh topic for per-channel presence token."""
    return f"wc/channels/{channel_id}/presence/{nick}"


def channel_presence_glob(channel_id: str) -> str:
    """Zenoh key expression for subscribing to all presence in a channel."""
    return f"wc/channels/{channel_id}/presence/*"


def target_to_buffer_label(target: str, my_nick: str) -> str:
    """Convert internal target key to WeeChat-style buffer label.
    'channel:general' → 'channel:#general'
    'private:alice_bob' → 'private:@alice' (the other nick)
    """
    if target.startswith("channel:"):
        return f"channel:#{target[8:]}"
    pair = target.split(":", 1)[1]
    other = extract_other_nick(pair, my_nick)
    return f"private:@{other}"


def extract_other_nick(pair: str, my_nick: str) -> str:
    """Extract the other party's nick from a sorted pair key."""
    nicks = pair.split("_")
    others = [n for n in nicks if n != my_nick]
    return others[0] if others else pair


def parse_target_key(target: str) -> tuple[str, str]:
    """Split 'channel:general' → ('channel', 'general')."""
    kind, _, value = target.partition(":")
    return (kind, value)


def parse_input(input_data: str) -> tuple[str, str]:
    """Parse user input into (msg_type, body).
    '/me waves' → ('action', 'waves')
    'hello' → ('msg', 'hello')
    """
    if input_data.startswith("/me ") or input_data == "/me":
        body = input_data[4:] if len(input_data) > 4 else ""
        return ("action", body)
    return ("msg", input_data)
