import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from wc_agent.config import load_config


def test_load_config_from_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[irc]\nserver = "10.0.0.1"\nport = 6667\ntls = false\npassword = ""\n\n[agents]\ndefault_channels = ["#general"]\nusername = "testuser"\n')
        f.flush()
        cfg = load_config(f.name)
    os.unlink(f.name)
    assert cfg["irc"]["server"] == "10.0.0.1"
    assert cfg["irc"]["port"] == 6667
    assert cfg["agents"]["username"] == "testuser"
    assert cfg["agents"]["default_channels"] == ["#general"]


def test_load_config_default_username():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[irc]\nserver = "localhost"\nport = 6667\n\n[agents]\ndefault_channels = ["#general"]\nusername = ""\n')
        f.flush()
        cfg = load_config(f.name)
    os.unlink(f.name)
    assert cfg["agents"]["username"] == os.environ.get("USER", "user")
