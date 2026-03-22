"""Tests for zenoh_sidecar.py — subprocess stdin/stdout protocol."""
import subprocess
import json
import os
import sys

SIDECAR_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "weechat-zenoh", "zenoh_sidecar.py")


def start_sidecar(mock=True):
    """Launch sidecar as subprocess. If mock=True, inject mock zenoh."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(
        os.path.dirname(__file__), "..", "..", "tests")
    args = [sys.executable, SIDECAR_PATH]
    if mock:
        args.append("--mock")
    return subprocess.Popen(
        args,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env, text=True, bufsize=1)


def send_cmd(proc, cmd: dict) -> None:
    proc.stdin.write(json.dumps(cmd) + "\n")
    proc.stdin.flush()


def read_event(proc, timeout=5.0) -> dict:
    import select
    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        raise TimeoutError("No response from sidecar")
    line = proc.stdout.readline()
    return json.loads(line)


class TestSidecarInit:
    def test_init_emits_ready(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            event = read_event(proc)
            assert event["event"] == "ready"
            assert "zid" in event
        finally:
            proc.terminate()
            proc.wait()

    def test_init_without_connect_uses_default(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "bob"})
            event = read_event(proc)
            assert event["event"] == "ready"
        finally:
            proc.terminate()
            proc.wait()


class TestSidecarJoinChannel:
    def test_join_channel_emits_presence_for_existing_members(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)  # ready
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            # With mock, liveliness.get() returns empty, so no presence events
            # Send a status to confirm sidecar is alive
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["event"] == "status_response"
            assert event["channels"] == 1
        finally:
            proc.terminate()
            proc.wait()

    def test_join_channel_twice_is_idempotent(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)  # ready
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["channels"] == 1
        finally:
            proc.terminate()
            proc.wait()


class TestSidecarPrivate:
    def test_join_private(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)  # ready
            send_cmd(proc, {"cmd": "join_private", "target_nick": "bob"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["privates"] == 1
        finally:
            proc.terminate()
            proc.wait()

    def test_leave_private(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)
            send_cmd(proc, {"cmd": "join_private", "target_nick": "bob"})
            send_cmd(proc, {"cmd": "leave_private", "target_nick": "bob"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["privates"] == 0
        finally:
            proc.terminate()
            proc.wait()


class TestSidecarSend:
    def test_send_does_not_error(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            send_cmd(proc, {"cmd": "send", "pub_key": "channel:general",
                            "type": "msg", "body": "hello"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["event"] == "status_response"
        finally:
            proc.terminate()
            proc.wait()


class TestSidecarNick:
    def test_set_nick(self):
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)
            send_cmd(proc, {"cmd": "set_nick", "nick": "alice2"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["nick"] == "alice2"
        finally:
            proc.terminate()
            proc.wait()

    def test_set_nick_updates_after_channel_join(self):
        """set_nick after init+join updates the nick for message filtering.

        Simulates the -r flag race: sidecar starts with wrong nick,
        then receives set_nick with the correct one.
        """
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "defaultuser",
                            "connect": "tcp/127.0.0.1:7447"})
            read_event(proc)  # ready
            send_cmd(proc, {"cmd": "join_channel", "channel_id": "general"})
            # Simulate -r flag setting the correct nick after init
            send_cmd(proc, {"cmd": "set_nick", "nick": "alice"})
            send_cmd(proc, {"cmd": "status"})
            event = read_event(proc)
            assert event["nick"] == "alice"
        finally:
            proc.terminate()
            proc.wait()


class TestSidecarBuildConfig:
    def test_init_with_custom_connect(self):
        """Sidecar accepts custom connect endpoint."""
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/10.0.0.1:7447"})
            event = read_event(proc)
            assert event["event"] == "ready"
        finally:
            proc.terminate()
            proc.wait()

    def test_init_with_multiple_endpoints(self):
        """Sidecar accepts comma-separated endpoints."""
        proc = start_sidecar(mock=True)
        try:
            send_cmd(proc, {"cmd": "init", "nick": "alice",
                            "connect": "tcp/10.0.0.1:7447,tcp/10.0.0.2:7447"})
            event = read_event(proc)
            assert event["event"] == "ready"
        finally:
            proc.terminate()
            proc.wait()
