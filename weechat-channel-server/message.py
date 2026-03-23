"""
Message utilities for weechat-channel-server.
Handles deduplication, mention detection, and text chunking.
"""

from collections import OrderedDict

# Maximum number of message IDs to track for deduplication
DEDUP_CAPACITY = 500

# Maximum message length before chunking
MAX_MESSAGE_LENGTH = 4000


class MessageDedup:
    """Track recent message IDs to prevent duplicate processing."""

    def __init__(self, capacity: int = DEDUP_CAPACITY):
        self._capacity = capacity
        self._seen: OrderedDict[str, None] = OrderedDict()

    def is_duplicate(self, message_id: str) -> bool:
        """Return True if this message ID has been seen before."""
        if message_id in self._seen:
            return True
        self._seen[message_id] = None
        # Evict oldest entries when over capacity
        while len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return False

    def __len__(self) -> int:
        return len(self._seen)


def detect_mention(body: str, agent_name: str) -> bool:
    """Check if a message body contains an @mention of the agent."""
    return f"@{agent_name}" in body


def clean_mention(body: str, agent_name: str) -> str:
    """Remove @mention from message body and strip whitespace."""
    return body.replace(f"@{agent_name}", "").strip()


def chunk_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a message into chunks, breaking at paragraph boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to break at a paragraph boundary
        cut = remaining[:max_length].rfind("\n\n")
        if cut == -1 or cut < max_length // 2:
            # Fall back to newline
            cut = remaining[:max_length].rfind("\n")
        if cut == -1 or cut < max_length // 2:
            # Fall back to space
            cut = remaining[:max_length].rfind(" ")
        if cut == -1:
            # Hard cut
            cut = max_length

        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()

    return chunks
