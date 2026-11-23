from __future__ import annotations

import os
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.core.exec import resolve_binary, run_command
from app.plugins.manifest import DiagnosticCheck

CheckStatus = Literal["pass", "fail", "warn", "skip"]

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:\|([^}]*))?\}")
_VERSION_PATTERN = re.compile(r"\b(\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?)")


class CheckResult(BaseModel):
    id: str
    label: str
    kind: str
    status: CheckStatus
    optional: bool = False
    evidence: str = ""
    hint: str | None = None
    version: str | None = None
    duration_ms: int = 0


class DiagnosticReport(BaseModel):
    plugin_id: str
    ran_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ok: bool
    checks: list[CheckResult]
    summary: dict[str, int]
    duration_ms: int


def expand_target(value: str) -> str:
    """Expand ${VAR|default} then OS variables (%VAR% / $VAR)."""
    expanded = _ENV_PATTERN.sub(
        lambda m: os.environ.get(m.group(1), m.group(2) if m.group(2) is not None else ""),
        value,
    )
    return os.path.expandvars(expanded).strip()


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _clip(text: str, limit: int = 600) -> str:
    single = " ".join(text.split())
    return single if len(single) <= limit else f"{single[:limit]}..."


def _extract_version(text: str) -> str | None:
    match = _VERSION_PATTERN.search(text)
    return match.group(1) if match else None


def _status_for(optional: bool, ok: bool) -> CheckStatus:
    if ok:
        return "pass"
    return "warn" if optional else "fail"


def _run_binary_check(check: DiagnosticCheck, allowed: set[str], default_timeout: float) -> CheckResult:
    target = expand_target(check.target)
    started = time.perf_counter()
    resolved = resolve_binary(target)
    if resolved is None:
        return CheckResult(
            id=check.id,
            label=check.label,
            kind=check.kind,
            optional=check.optional,
            status=_status_for(check.optional, False),
            evidence=f"'{target}' no está en PATH.",
            hint=check.hint,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    args = check.args or ["-version"]
    result = run_command(
        target,
        args,
        timeout=min(check.timeout_seconds, default_timeout),
        allowed_binaries=allowed,
    )
    duration = int((time.perf_counter() - started) * 1000)
    if result.error:
        return CheckResult(
            id=check.id,
            label=check.label,
            kind=check.kind,
            optional=check.optional,
            status=_status_for(check.optional, False),
            evidence=f"{resolved} — {result.error}",
            hint=check.hint,
            duration_ms=duration,
        )

    output = result.output.strip()
    evidence = f"{resolved} — {_clip(_first_line(output))}"
    if result.returncode != 0:
        evidence = f"{resolved} — salida {result.returncode}: {_clip(_first_line(output))}"

    return CheckResult(
        id=check.id,
        label=check.label,
        kind=check.kind,
        optional=check.optional,
        status=_status_for(check.optional, result.returncode == 0),
        evidence=evidence,
        hint=check.hint,
        version=_extract_version(output),
        duration_ms=duration,
    )


def _run_file_check(check: DiagnosticCheck) -> CheckResult:
    started = time.perf_counter()
    candidates = [expand_target(part) for part in check.target.split(";") if part.strip()]
    candidates = list(dict.fromkeys(candidates))
    found = [candidate for candidate in candidates if Path(candidate).exists()]
    unresolved = [candidate for candidate in candidates if "${" in candidate or "%" in candidate]
    if found:
        evidence = "Encontrado: " + " | ".join(found)
        status: CheckStatus = "pass"
    else:
        evidence = f"No se encontró ninguna ruta: {' | '.join(candidates)}"
        if unresolved:
            evidence += " (variable de entorno sin definir)"
        status = _status_for(check.optional, False)
    return CheckResult(
        id=check.id,
        label=check.label,
        kind=check.kind,
        optional=check.optional,
        status=status,
        evidence=evidence,
        hint=check.hint,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _run_env_check(check: DiagnosticCheck) -> CheckResult:
    started = time.perf_counter()
    variable = expand_target(check.target)
    value = os.environ.get(variable, "")
    if value:
        result = CheckResult(
            id=check.id,
            label=check.label,
            kind=check.kind,
            optional=check.optional,
            status="pass",
            evidence=f"Variable {variable} definida (valor no expuesto).",
            hint=check.hint,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    elif check.optional:
        result = CheckResult(
            id=check.id,
            label=check.label,
            kind=check.kind,
            optional=True,
            status="skip",
            evidence=f"Variable {variable} no definida.",
            hint=check.hint,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    else:
        result = CheckResult(
            id=check.id,
            label=check.label,
            kind=check.kind,
            optional=False,
            status="fail",
            evidence=f"Variable {variable} no definida.",
            hint=check.hint,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    return result


def _run_tcp_check(check: DiagnosticCheck) -> CheckResult:
    started = time.perf_counter()
    target = expand_target(check.target)
    try:
        host, port_text = target.rsplit(":", 1)
        port = int(port_text)
    except ValueError:
        return CheckResult(
            id=check.id,
            label=check.label,
            kind=check.kind,
            optional=check.optional,
            status=_status_for(check.optional, False),
            evidence=f"Destino TCP inválido: '{target}'.",
            hint=check.hint,
        )

    try:
        with socket.create_connection((host, port), timeout=check.timeout_seconds):
            status: CheckStatus = "pass"
            evidence = f"Conexión TCP establecida con {host}:{port}."
    except OSError as exc:
        status = _status_for(check.optional, False)
        evidence = f"No se pudo conectar a {host}:{port} — {exc}"

    return CheckResult(
        id=check.id,
        label=check.label,
        kind=check.kind,
        optional=check.optional,
        status=status,
        evidence=evidence,
        hint=check.hint,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _run_http_check(check: DiagnosticCheck) -> CheckResult:
    started = time.perf_counter()
    url = expand_target(check.target)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return CheckResult(
            id=check.id,
            label=check.label,
            kind=check.kind,
            optional=check.optional,
            status=_status_for(check.optional, False),
            evidence=f"URL inválida: '{url}'.",
            hint=check.hint,
        )

    try:
        response = httpx.get(url, timeout=check.timeout_seconds, follow_redirects=True)
        reachable = response.status_code < 500
        status: CheckStatus = "pass" if reachable else "warn"
        evidence = f"{url} respondió HTTP {response.status_code} ({response.elapsed.total_seconds():.2f}s)."
    except httpx.HTTPError as exc:
        status = _status_for(check.optional, False)
        evidence = f"Sin respuesta de {url} — {type(exc).__name__}: {exc}"

    return CheckResult(
        id=check.id,
        label=check.label,
        kind=check.kind,
        optional=check.optional,
        status=status,
        evidence=evidence,
        hint=check.hint,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def run_checks(
    plugin_id: str,
    checks: list[DiagnosticCheck],
    *,
    default_timeout: float = 15.0,
) -> DiagnosticReport:
    started = time.perf_counter()
    allowed = {check.target for check in checks if check.kind in ("binary", "command")}
    results: list[CheckResult] = []

    for check in checks:
        if check.kind in ("binary", "command"):
            results.append(_run_binary_check(check, allowed, default_timeout))
        elif check.kind == "file":
            results.append(_run_file_check(check))
        elif check.kind == "env":
            results.append(_run_env_check(check))
        elif check.kind == "tcp":
            results.append(_run_tcp_check(check))
        elif check.kind == "http":
            results.append(_run_http_check(check))
        else:  # pragma: no cover - schema already restricts kinds
            results.append(
                CheckResult(
                    id=check.id,
                    label=check.label,
                    kind=check.kind,
                    optional=check.optional,
                    status="skip",
                    evidence=f"Tipo de comprobación no soportado: {check.kind}",
                    hint=check.hint,
                )
            )

    summary = {
        "passed": sum(1 for r in results if r.status == "pass"),
        "failed": sum(1 for r in results if r.status == "fail"),
        "warnings": sum(1 for r in results if r.status == "warn"),
        "skipped": sum(1 for r in results if r.status == "skip"),
    }
    ok = all(r.status == "pass" for r in results if not r.optional)
    return DiagnosticReport(
        plugin_id=plugin_id,
        ok=ok,
        checks=results,
        summary=summary,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
