"""Start Studio's optional Windows OpenCode server without printing its password."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    password = dotenv_values(ROOT / "backend" / ".env", encoding="utf-8").get("GHS_OPENCODE_SERVER_PASSWORD")
    if not password or not password.strip():
        print("OpenCode no iniciado: falta GHS_OPENCODE_SERVER_PASSWORD en backend/.env.")
        return 1
    executable = shutil.which("opencode")
    if not executable:
        print("OpenCode no iniciado: opencode no está en el PATH.")
        return 1
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GHS_")}
    env.pop("OPENCODE_PASSWORD", None)  # V2 prefers this variable over the legacy alias.
    env["OPENCODE_SERVER_PASSWORD"] = password
    try:
        location = Path(tempfile.gettempdir()) / "ghs-opencode"
        location.mkdir(exist_ok=True)
        # `serve` can print its password at startup. Discard both streams.
        subprocess.Popen([executable, "serve", "--hostname", "127.0.0.1", "--port", "4096"],
                         cwd=location, env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    except (OSError, ValueError):
        print("OpenCode no iniciado: no se pudo lanzar opencode serve.")
        return 1
    print("OpenCode: arranque solicitado en 127.0.0.1:4096. Verifica la conexión en Extensiones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
