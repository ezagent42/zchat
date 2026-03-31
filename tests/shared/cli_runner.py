# tests/shared/cli_runner.py
"""CLI runner factory for test suites."""
import os
import subprocess
from typing import Callable


def make_cli_runner(
    cmd: list[str], project: str, env: dict
) -> Callable[..., subprocess.CompletedProcess]:
    """Create a CLI runner closure.

    Args:
        cmd: command prefix, e.g. ["zchat"] or ["uv", "run", "python", "-m", "zchat.cli"]
        project: project name (passed via --project)
        env: environment variables to inject (ZCHAT_HOME, etc.)
    """
    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        full_cmd = [*cmd, "--project", project, *args]
        merged_env = {**os.environ, **env}
        result = subprocess.run(
            full_cmd, env=merged_env, capture_output=True, text=True,
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, full_cmd,
                output=result.stdout, stderr=result.stderr,
            )
        return result
    return run
