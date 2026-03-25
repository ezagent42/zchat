# wc_registry/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CommandParam:
    name: str
    required: bool
    help: str
    default: Any = None


@dataclass
class CommandSpec:
    name: str
    args: str
    description: str
    params: list[CommandParam]
    handler: Callable


@dataclass
class CommandResult:
    success: bool
    message: str
    details: dict | None = None

    @classmethod
    def ok(cls, msg: str, **details) -> CommandResult:
        return cls(success=True, message=msg, details=details or None)

    @classmethod
    def error(cls, msg: str, **details) -> CommandResult:
        return cls(success=False, message=msg, details=details or None)


@dataclass
class ParsedArgs:
    """Result of argument parsing."""
    positional: dict[str, str] = field(default_factory=dict)
    flags: dict[str, str | bool] = field(default_factory=dict)
    raw: str = ""

    def get(self, name: str, default=None):
        return self.positional.get(name, self.flags.get(name, default))
