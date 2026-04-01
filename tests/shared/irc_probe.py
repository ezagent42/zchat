# tests/shared/irc_probe.py
"""IRC probe client for test verification (shared across E2E and pre-release suites)."""

import irc.client
import re
import subprocess
import random
import threading
import time


class IrcProbe:
    """Lightweight IRC client that joins a channel and records messages.

    All IRC operations are dispatched through the reactor thread to avoid
    thread-safety issues with the irc library (which is not thread-safe).
    """

    def __init__(self, server: str, port: int, nick: str = "e2e-probe",
                 tls: bool = False, sasl_login: str = "", sasl_pass: str = ""):
        self.server = server
        self.port = port
        self.nick = nick
        self.tls = tls
        self.sasl_login = sasl_login
        self.sasl_pass = sasl_pass
        self.messages: list[dict] = []
        self._lock = threading.Lock()
        self._reactor = irc.client.Reactor()
        self._conn = None
        self._thread = None
        self._whois_result: dict | None = None
        self._whois_event = threading.Event()

    def connect(self):
        """Connect to IRC server and start reactor in background thread."""
        import irc.connection
        connect_kwargs: dict = {}
        if self.tls:
            import ssl
            import functools
            ctx = ssl.create_default_context()
            wrapper = functools.partial(ctx.wrap_socket, server_hostname=self.server)
            connect_kwargs["connect_factory"] = irc.connection.Factory(wrapper=wrapper)
        if self.sasl_login and self.sasl_pass:
            connect_kwargs["sasl_login"] = self.sasl_login
            connect_kwargs["password"] = self.sasl_pass
        self._conn = self._reactor.server().connect(
            self.server, self.port, self.nick, **connect_kwargs
        )
        self._conn.add_global_handler("pubmsg", self._on_pubmsg)
        self._conn.add_global_handler("privmsg", self._on_privmsg)
        self._conn.add_global_handler("whoisuser", self._on_whoisuser)
        self._conn.add_global_handler("endofwhois", self._on_endofwhois)
        self._conn.add_global_handler("nosuchnick", self._on_endofwhois)
        self._thread = threading.Thread(target=self._reactor.process_forever, daemon=True)
        self._thread.start()

    def join(self, channel: str):
        """Join a channel to receive messages. Dispatched via reactor."""
        self._reactor.scheduler.execute_after(0, lambda: self._conn.join(channel))

    def disconnect(self):
        """Disconnect from IRC."""
        if self._conn:
            try:
                self._conn.disconnect()
            except Exception:
                pass

    def nick_exists(self, nick: str, timeout: float = 3.0) -> bool:
        """Check if a nick is online via WHOIS using nc subprocess."""
        probe_nick = f"e2e-chk-{random.randint(1000, 9999)}"
        try:
            script = (
                f"echo -e 'NICK {probe_nick}\\r'\n"
                f"echo -e 'USER probe 0 * probe\\r'\n"
                f"sleep 1\n"
                f"echo -e 'WHOIS {nick}\\r'\n"
                f"sleep 1\n"
                f"echo -e 'QUIT\\r'\n"
            )
            result = subprocess.run(
                ["bash", "-c", f"{{ {script} }} | nc -w 5 127.0.0.1 {self.port}"],
                capture_output=True, text=True, timeout=10,
            )
            return f" 311 " in result.stdout and nick in result.stdout
        except Exception:
            return False

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

    def privmsg(self, channel: str, text: str):
        """Send a PRIVMSG to a channel. Dispatched via reactor."""
        self._reactor.scheduler.execute_after(
            0, lambda: self._conn.privmsg(channel, text)
        )

    # --- Handlers (called by reactor thread) ---

    def _on_whoisuser(self, conn, event):
        self._whois_result = {"found": True}
        self._whois_event.set()

    def _on_endofwhois(self, conn, event):
        if self._whois_result is None:
            self._whois_result = {"found": False}
        self._whois_event.set()

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
