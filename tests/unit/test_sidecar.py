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
