"""Short-lived SDK worker. Only the local CLI receives the clean OS environment."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import aclosing
from pathlib import Path
from tempfile import TemporaryDirectory

from app.ai.errors import AICLINotFound, AIError, AINotLoggedIn, AITimeout

_LOGIN_MESSAGE = "Claude Code no tiene una sesión de Claude activa. Ejecuta claude auth login."
_DENIED = ["Bash", "PowerShell", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep",
           "WebFetch", "WebSearch", "Agent", "Task", "Skill", "ToolSearch"]


def find_cli() -> str:
    command = shutil.which("claude")
    if os.name != "nt":
        if command:
            return command
    else:
        # Resolve the official npm shim to its native executable; never run .cmd
        # via a shell, and never silently fall back to the SDK's bundled binary.
        if command:
            path = Path(command)
            if path.suffix.lower() == ".exe":
                return str(path)
            npm_exe = path.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
            if npm_exe.is_file():
                return str(npm_exe)
        native = Path.home() / ".local" / "bin" / "claude.exe"
        if native.is_file():
            return str(native)
    raise AICLINotFound("No se encontró Claude Code instalado. Instálalo o agrégalo al PATH.")


def _cli(cli: str, cwd: str, deadline: float, *args: str) -> subprocess.CompletedProcess:
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError
    return subprocess.run([cli, *args], cwd=cwd, capture_output=True, encoding="utf-8",
                          timeout=remaining)


async def query_text(sdk, *, cli: str, cwd: str, prompt: str, system: str, model: str | None) -> str:
    options = sdk.ClaudeAgentOptions(
        cli_path=cli, cwd=cwd, model=model, system_prompt=system,
        tools=[], allowed_tools=[], disallowed_tools=_DENIED, max_turns=1,
        permission_mode="dontAsk", setting_sources=[], strict_mcp_config=True,
        mcp_servers={}, skills=[],
        env={"DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
             "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"},
        extra_args={"restricted": None, "disable-slash-commands": None,
                    "no-session-persistence": None},
        settings=json.dumps({"disableAllHooks": True, "disableClaudeAiConnectors": True}),
        stderr=lambda _: None,
    )

    async def input_messages():
        # Pass the text via stdin, not a CLI argument or a file. client_composed
        # prevents slash commands and @ references from being expanded.
        yield {"type": "user", "message": {"role": "user", "content": prompt},
               "client_composed": True, "session_id": "", "parent_tool_use_id": None}

    initialized = False
    result = None
    async with aclosing(sdk.query(prompt=input_messages(), options=options)) as messages:
        async for message in messages:
            if isinstance(message, sdk.SystemMessage) and message.subtype == "init":
                if message.data.get("tools") != [] or message.data.get("mcp_servers") != []:
                    raise AIError("Claude Code anunció herramientas o servidores MCP. Se rechazó la respuesta.")
                initialized = True
            if isinstance(message, sdk.AssistantMessage):
                if message.error == "authentication_failed":
                    raise AINotLoggedIn(_LOGIN_MESSAGE)
                if any(isinstance(block, (sdk.ToolUseBlock, sdk.ToolResultBlock,
                                          sdk.ServerToolUseBlock, sdk.ServerToolResultBlock))
                       for block in message.content):
                    raise AIError("Claude Code intentó usar una herramienta. Se rechazó la respuesta.")
            if isinstance(message, sdk.ResultMessage):
                if message.api_error_status == 401:
                    raise AINotLoggedIn(_LOGIN_MESSAGE)
                if message.permission_denials or message.deferred_tool_use:
                    raise AIError("Claude Code intentó usar una herramienta. Se rechazó la respuesta.")
                result = message
    if (not initialized or result is None or result.is_error or result.subtype != "success"
            or result.num_turns != 1 or not result.result or not result.result.strip()):
        raise AIError("El Claude Agent SDK no completó un turno de texto sin herramientas.")
    return result.result.strip()


async def run(payload: dict, checks: dict) -> str:
    timeout = payload["timeout"]
    deadline = asyncio.get_running_loop().time() + timeout
    checks.update(cli_version=None, sdk_importable=False, session_active=False, tools_disabled=False)
    try:
        import claude_agent_sdk as sdk
    except Exception:
        sdk = None
    checks["sdk_importable"] = sdk is not None

    cli = find_cli()
    with TemporaryDirectory(prefix="ghs-ai-") as cwd:
        version = _cli(cli, cwd, deadline, "--version")
        if version.returncode or not (match := re.fullmatch(r"(\d+\.\d+\.\d+) \(Claude Code\)", version.stdout.strip())):
            raise AIError("Claude Code está instalado, pero no se pudo obtener su versión.")
        checks["cli_version"] = match[1]
        if sdk is None:
            raise AIError("No se pudo importar claude-agent-sdk en el entorno del backend.")
        if tuple(map(int, match[1].split("."))) < (2, 1, 248):
            raise AIError("Actualiza Claude Code: esta versión no admite el aislamiento requerido.")
        help_result = _cli(cli, cwd, deadline, "--help")
        if help_result.returncode or "--restricted " not in help_result.stdout:
            raise AIError("Actualiza Claude Code: esta versión no admite el modo restringido requerido.")
        auth = _cli(cli, cwd, deadline, "auth", "status")
        try:
            state = json.loads(auth.stdout)
        except ValueError:
            raise AIError("Claude Code no pudo comprobar el estado de su sesión.") from None
        if state.get("loggedIn") is not True or state.get("authMethod") != "claude.ai":
            raise AINotLoggedIn(_LOGIN_MESSAGE)
        if auth.returncode or state.get("apiProvider") != "firstParty":
            raise AIError("Claude Code no confirmó una sesión directa de Claude.")
        checks["session_active"] = True
        async with asyncio.timeout_at(deadline):
            text = await query_text(sdk, cli=cli, cwd=cwd, prompt=payload["prompt"],
                                    system=payload["system"], model=payload["model"])
        checks["tools_disabled"] = True
        return text


def main() -> None:
    checks: dict = {}
    try:
        text = asyncio.run(run(json.load(sys.stdin.buffer), checks))
        output = {"text": text}
    except (TimeoutError, subprocess.TimeoutExpired):
        output = {"error": AITimeout.code, "message": "Claude superó el tiempo de espera configurado."}
    except AIError as exc:
        output = {"error": exc.code, "message": exc.message}
    except Exception:
        # SDK exceptions may include the prompt, subprocess arguments or local
        # paths. Never print them or pass them back to the API.
        output = {"error": AIError.code, "message": "Falló la llamada local de Claude Agent SDK."}
    print(json.dumps({**output, "checks": checks}))


if __name__ == "__main__":
    main()
