# tests/e2e/irc_probe.py
"""IRC probe client for e2e test verification."""

import irc.client
import threading
import time


class IrcProbe:
    """Lightweight IRC client that joins a channel and records messages."""

    def __init__(self, server: str, port: int, nick: str = "e2e-probe"):
        self.server = server
        self.port = port
        self.nick = nick
        self.messages: list[dict] = []  # {"nick": str, "channel": str, "text": str}
        self._lock = threading.Lock()   # Protects self.messages (thread-safe appends)
        self._reactor = irc.client.Reactor()
        self._conn = None
        self._thread = None

    def connect(self):
        """Connect to IRC server and start reactor in background thread."""
        self._conn = self._reactor.server().connect(self.server, self.port, self.nick)
        self._conn.add_global_handler("pubmsg", self._on_pubmsg)
        self._conn.add_global_handler("privmsg", self._on_privmsg)
        self._thread = threading.Thread(target=self._reactor.process_forever, daemon=True)
        self._thread.start()

    def join(self, channel: str):
        """Join a channel to receive messages."""
        self._conn.join(channel)

    def disconnect(self):
        """Disconnect from IRC."""
        if self._conn:
            self._conn.disconnect()

    def nick_exists(self, nick: str, timeout: float = 3.0) -> bool:
        """Check if a nick is online via WHOIS on the persistent connection."""
        result = {"found": False, "done": False}

        def on_whoisuser(conn, event):
            result["found"] = True
            result["done"] = True

        def on_endofwhois(conn, event):
            result["done"] = True

        self._conn.add_global_handler("whoisuser", on_whoisuser)
        self._conn.add_global_handler("endofwhois", on_endofwhois)
        self._conn.whois([nick])
        deadline = time.time() + timeout
        while time.time() < deadline and not result["done"]:
            time.sleep(0.1)
        # Remove handlers to avoid accumulation across calls
        self._conn.remove_global_handler("whoisuser", on_whoisuser)
        self._conn.remove_global_handler("endofwhois", on_endofwhois)
        return result["found"]

    def wait_for_nick(self, nick: str, timeout: int = 5) -> bool:
        """Poll until nick appears on IRC."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.nick_exists(nick):
                return True
            time.sleep(1)
        return False

    def wait_for_nick_gone(self, nick: str, timeout: int = 10) -> bool:
        """Poll until nick disappears from IRC."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.nick_exists(nick):
                return True
            time.sleep(1)
        return False

    def wait_for_message(self, pattern: str, timeout: int = 15) -> dict | None:
        """Wait for a message matching pattern. Returns the message dict or None."""
        import re
        deadline = time.time() + timeout
        with self._lock:
            seen = len(self.messages)
        while time.time() < deadline:
            with self._lock:
                for msg in self.messages[seen:]:
                    if re.search(pattern, msg["text"], re.IGNORECASE):
                        return msg
                seen = len(self.messages)
            time.sleep(0.5)
        return None

    def _on_pubmsg(self, conn, event):
        with self._lock:
            self.messages.append({
                "nick": event.source.nick,
                "channel": event.target,
                "text": event.arguments[0],
            })

    def _on_privmsg(self, conn, event):
        with self._lock:
            self.messages.append({
                "nick": event.source.nick,
                "channel": None,
                "text": event.arguments[0],
            })
