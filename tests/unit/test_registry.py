from wc_registry.types import CommandParam, CommandSpec, CommandResult, ParsedArgs


def test_command_result_ok():
    r = CommandResult.ok("Created agent", workspace="/tmp/x")
    assert r.success is True
    assert r.message == "Created agent"
    assert r.details == {"workspace": "/tmp/x"}


def test_command_result_error():
    r = CommandResult.error("not found")
    assert r.success is False
    assert r.message == "not found"
    assert r.details is None


def test_command_result_ok_no_details():
    r = CommandResult.ok("done")
    assert r.details is None


def test_parsed_args_get_positional():
    args = ParsedArgs(positional={"name": "helper"}, flags={}, raw="helper")
    assert args.get("name") == "helper"
    assert args.get("missing") is None
    assert args.get("missing", "default") == "default"


def test_parsed_args_get_flag():
    args = ParsedArgs(positional={}, flags={"--workspace": "/tmp"}, raw="--workspace /tmp")
    assert args.get("--workspace") == "/tmp"


def test_parsed_args_positional_over_flag():
    args = ParsedArgs(positional={"name": "pos"}, flags={"name": "flag"}, raw="")
    assert args.get("name") == "pos"


from wc_registry import CommandRegistry
from wc_registry.types import CommandParam, CommandResult, ParsedArgs


def test_registry_register_and_dispatch():
    reg = CommandRegistry(prefix="test")

    @reg.command(
        name="greet",
        args="<name>",
        description="Say hello",
        params=[CommandParam("name", required=True, help="Who to greet")],
    )
    def cmd_greet(buffer, args: ParsedArgs) -> CommandResult:
        return CommandResult.ok(f"Hello {args.get('name')}")

    result = reg.dispatch(None, "greet alice")
    assert result.success
    assert result.message == "Hello alice"


def test_registry_missing_required_param():
    reg = CommandRegistry(prefix="test")

    @reg.command(
        name="greet",
        args="<name>",
        description="Say hello",
        params=[CommandParam("name", required=True, help="Who to greet")],
    )
    def cmd_greet(buffer, args: ParsedArgs) -> CommandResult:
        return CommandResult.ok("should not reach")

    result = reg.dispatch(None, "greet")
    assert not result.success
    assert "name" in result.message.lower()


def test_registry_flag_parsing():
    reg = CommandRegistry(prefix="test")

    @reg.command(
        name="create",
        args="<name> [--workspace <path>]",
        description="Create something",
        params=[
            CommandParam("name", required=True, help="Name"),
            CommandParam("--workspace", required=False, help="Path"),
        ],
    )
    def cmd_create(buffer, args: ParsedArgs) -> CommandResult:
        return CommandResult.ok(f"{args.get('name')} at {args.get('--workspace', 'default')}")

    result = reg.dispatch(None, "create myapp --workspace /tmp/x")
    assert result.success
    assert result.message == "myapp at /tmp/x"


def test_registry_unknown_subcommand():
    reg = CommandRegistry(prefix="test")
    result = reg.dispatch(None, "nonexistent")
    assert not result.success
    assert "unknown" in result.message.lower()


def test_registry_help_generation():
    reg = CommandRegistry(prefix="test")

    @reg.command(name="foo", args="<x>", description="Do foo", params=[])
    def cmd_foo(buffer, args):
        return CommandResult.ok("ok")

    @reg.command(name="bar", args="", description="Do bar", params=[])
    def cmd_bar(buffer, args):
        return CommandResult.ok("ok")

    result = reg.dispatch(None, "help")
    assert result.success
    assert "foo" in result.message
    assert "bar" in result.message
    assert "Do foo" in result.message


def test_registry_empty_args_shows_help():
    reg = CommandRegistry(prefix="test")

    @reg.command(name="foo", args="", description="Do foo", params=[])
    def cmd_foo(buffer, args):
        return CommandResult.ok("ok")

    result = reg.dispatch(None, "")
    assert result.success
    assert "foo" in result.message


def test_registry_boolean_flag():
    reg = CommandRegistry(prefix="test")

    @reg.command(
        name="run",
        args="[--verbose]",
        description="Run it",
        params=[CommandParam("--verbose", required=False, help="Verbose output")],
    )
    def cmd_run(buffer, args: ParsedArgs) -> CommandResult:
        return CommandResult.ok(f"verbose={args.get('--verbose', False)}")

    result = reg.dispatch(None, "run --verbose")
    assert result.success
    assert "verbose=True" in result.message
