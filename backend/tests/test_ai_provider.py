import asyncio
import json
import subprocess
from pathlib import Path

import claude_agent_sdk as sdk
import pytest

from app.ai import provider, worker
from app.ai.errors import AICLINotFound, AIError, AINotLoggedIn, AITimeout


def test_provider_sends_text_via_stdin_and_filters_parent_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "parent-only")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "parent-only")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "parent-only")
    monkeypatch.setenv("GHS_TEST_SECRET", "parent-only")

    def run(args, **kwargs):
        assert args[1:] == ["-E", "-m", "app.ai.worker"]
        assert all("parent-only" not in value for value in kwargs["env"].values())
        assert kwargs["timeout"] == 15
        assert json.loads(kwargs["input"]) == {"prompt": "Texto", "system": "Sistema", "timeout": 10, "model": "haiku"}
        return subprocess.CompletedProcess(args, 0, stdout=b'{"text":"Sugerencia"}')

    monkeypatch.setattr(provider.subprocess, "run", run)
    assert provider.ClaudeAgentSDKProvider(10, "haiku").generate_text("Texto", "Sistema") == "Sugerencia"


@pytest.mark.parametrize("error", [AICLINotFound, AINotLoggedIn, AITimeout, AIError])
def test_worker_error_preserves_type(monkeypatch, error):
    stdout = json.dumps({"error": error.code, "message": "Diagnóstico seguro", "checks": {"session_active": False}}).encode()
    monkeypatch.setattr(provider.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 0, stdout=stdout))
    with pytest.raises(error, match="Diagnóstico seguro") as exc:
        provider.ClaudeAgentSDKProvider(10).generate_text("texto", "sistema")
    assert exc.value.details == {"session_active": False}


def test_outer_timeout_hides_command_and_stderr(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(["private-path"], 1, stderr=b"private-text")

    monkeypatch.setattr(provider.subprocess, "run", run)
    with pytest.raises(AITimeout, match="tiempo de espera"):
        provider.ClaudeAgentSDKProvider(1).generate_text("texto", "sistema")


def test_sdk_absent_session_never_queries(monkeypatch):
    fake_cli = "/fake/claude"
    monkeypatch.setattr(worker, "find_cli", lambda: fake_cli)
    outputs = {"--version": "2.1.319 (Claude Code)", "--help": "  --restricted  ",
               "auth": '{"loggedIn": false, "authMethod": "none"}'}

    def cli(path, cwd, deadline, *args):
        assert path == fake_cli and not list(Path(cwd).iterdir())
        return subprocess.CompletedProcess(args, int(args[0] == "auth"), stdout=outputs[args[0]])

    monkeypatch.setattr(worker, "_cli", cli)
    monkeypatch.setattr(worker, "query_text", lambda *args, **kw: pytest.fail("No consented authentication"))
    with pytest.raises(AINotLoggedIn):
        asyncio.run(worker.run({"timeout": 10}, {}))


@pytest.mark.parametrize("case", ["valid", "extra_tool", "mcp", "tool_use", "auth", "extra_turn", "no_init", "no_result"])
def test_sdk_single_turn_and_fail_closed(monkeypatch, tmp_path, case):
    finished = False

    async def query(*, prompt, options):
        nonlocal finished
        assert options.cli_path == "installed-cli" and options.cwd == str(tmp_path)
        assert options.tools == options.allowed_tools == options.setting_sources == []
        assert options.strict_mcp_config and options.mcp_servers == {}
        assert options.max_turns == 1 and options.permission_mode == "dontAsk"
        assert {"Bash", "Read", "Write", "Edit", "WebFetch", "WebSearch"} <= set(options.disallowed_tools)
        assert "no-session-persistence" in options.extra_args and "restricted" in options.extra_args
        assert options.model == "sonnet" and options.system_prompt == "Sistema"
        inputs = [entry async for entry in prompt]
        assert len(inputs) == 1 and inputs[0]["client_composed"] is True
        assert inputs[0]["message"]["content"] == "@texto"
        try:
            if case != "no_init":
                yield sdk.SystemMessage("init", {"tools": ["Read"] if case == "extra_tool" else [],
                    "mcp_servers": [{"name": "bad"}] if case == "mcp" else []})
            if case == "tool_use":
                yield sdk.AssistantMessage([sdk.ToolUseBlock("1", "Read", {})], "sonnet")
            if case == "auth":
                yield sdk.AssistantMessage([], "sonnet", error="authentication_failed")
            if case != "no_result":
                yield sdk.ResultMessage("success", 1, 1, False, 2 if case == "extra_turn" else 1, "test", result="respuesta")
        finally:
            finished = True

    monkeypatch.setattr(sdk, "query", query)

    def invoke():
        return asyncio.run(worker.query_text(sdk, cli="installed-cli", cwd=str(tmp_path),
                                              prompt="@texto", system="Sistema", model="sonnet"))

    if case == "valid":
        assert invoke() == "respuesta"
    else:
        with pytest.raises(AINotLoggedIn if case == "auth" else AIError):
            invoke()
    assert finished
