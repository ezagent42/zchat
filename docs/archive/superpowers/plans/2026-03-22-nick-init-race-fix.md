# Fix Nick Initialization Race Condition

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the bug where two WeeChat users can't see each other's messages because `-r` flag sets nick AFTER plugin init, causing both sidecars to use the same `$USER` nick.

**Architecture:** Add a `weechat.hook_config()` callback in `weechat-zenoh.py` that detects nick changes to `plugins.var.python.weechat-zenoh.nick` and forwards the new nick to the running sidecar via `set_nick` command. This reuses the existing `handle_set_nick()` in the sidecar.

**Tech Stack:** Python, WeeChat plugin API, zenoh_sidecar.py subprocess IPC

---

## Chunk 1: The Fix

### Task 1: Add config hook for nick changes

**Files:**
- Modify: `weechat-zenoh/weechat-zenoh.py:192-206` (zc_init)

- [ ] **Step 1: Write the config change callback**

Add after `_handle_sidecar_crash()` (line 186), before the Init section:

```python
def _on_nick_config_changed(data, option, value):
    """hook_config callback — nick changed externally (e.g. via -r flag)."""
    global my_nick
    if value and value != my_nick:
        old = my_nick
        my_nick = value
        if sidecar_connected:
            _sidecar_send({"cmd": "set_nick", "nick": my_nick})
            weechat.prnt("", f"[zenoh] Nick changed: {old} → {my_nick}")
    return weechat.WEECHAT_RC_OK
```

- [ ] **Step 2: Register the config hook in zc_init**

In `zc_init()`, after the `_sidecar_send(cmd)` call (line 206), add:

```python
    weechat.hook_config("plugins.var.python.weechat-zenoh.nick",
                        "_on_nick_config_changed", "")
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `pytest tests/unit/test_sidecar.py -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add weechat-zenoh/weechat-zenoh.py
git commit -m "fix: hook config change to fix nick init race with -r flag

When WeeChat starts with -r '/set ...nick alice', the -r command
runs AFTER plugin init. The sidecar was already started with the
wrong nick ($USER). Now we hook config changes and forward the
correct nick to the running sidecar via set_nick command."
```

### Task 2: Add test for config-driven nick update

**Files:**
- Modify: `tests/unit/test_sidecar.py`

- [ ] **Step 1: Write test for nick re-init after sidecar is already running**

Add to `TestSidecarNick` class:

```python
    def test_set_nick_updates_liveliness(self):
        """set_nick after init updates the nick used for message filtering."""
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
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/unit/test_sidecar.py::TestSidecarNick -v`
Expected: Both nick tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_sidecar.py
git commit -m "test: add sidecar nick re-init test for -r flag race fix"
```
