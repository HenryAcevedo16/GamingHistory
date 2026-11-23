from __future__ import annotations

import os

from app.core.exec import run_command


def test_run_command_does_not_pass_sensitive_environment_to_child(
    monkeypatch,
) -> None:
    secret_name = "GHS_TEST_SECRET"
    monkeypatch.setenv(secret_name, "must-not-reach-child")
    result = run_command(
        "cmd.exe",
        ["/d", "/c", f"if defined {secret_name} (echo leaked) else (echo absent)"],
        allowed_binaries={"cmd.exe"},
    )

    assert result.ok, result.error or result.stderr
    assert result.stdout.strip() == "absent"
    assert os.environ[secret_name] == "must-not-reach-child"
