from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.ai import opencode
from app.ai.errors import AIAuthFailed, AIError, AIServerUnavailable, AITimeout
from app.ai.opencode import OpenCodeServerProvider

MODEL = {"providerID": "fixture", "id": "fixture-chat", "enabled": True, "type": "chat"}
KEY = "fixture/fixture-chat"
SESSION = "/api/session/ses_fixture"
AUTH = "Basic " + base64.b64encode(b"opencode:test-password").decode()
DENIED = [{"action": "*", "resource": "*", "effect": "deny"}]


@pytest.fixture
def server():
    calls = []
    responses = {
        ("GET", "/api/info"): (401, {}),
        ("GET", "/api/model"): (200, {"data": [MODEL, {**MODEL, "id": "disabled", "enabled": False},
                                               {**MODEL, "id": "image", "type": "image"}]}),
        ("GET", "/api/model/default"): (200, {"data": MODEL}),
        ("POST", "/api/session"): (200, {"data": {"id": "ses_fixture", "permissions": DENIED,
                                                 "model": {"providerID": "fixture", "id": "fixture-chat"}}}),
        ("POST", SESSION + "/generate"): (200, {"data": {"text": "respuesta real del fixture"}}),
        ("DELETE", SESSION): (204, None),
    }

    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            auth = self.headers.get("Authorization")
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append((self.command, self.path, auth, json.loads(body) if body else None))
            status, data = responses.get((self.command, self.path), (404, {}))
            if self.path != "/api/info" and auth != AUTH:
                status, data = 401, {"error": "raw response must not be relayed"}
            if status == 599:  # Test-only slow response.
                time.sleep(0.15)
            self.send_response(status)
            self.end_headers()
            if data is not None:
                try:
                    self.wfile.write(json.dumps(data).encode())
                except OSError:
                    pass

        do_GET = do_POST = do_DELETE = handle_request

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02})
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", responses, calls
    httpd.shutdown()
    thread.join()
    httpd.server_close()


def test_catalog_and_transient_generation(server):
    url, _, calls = server
    provider = OpenCodeServerProvider(url, "test-password", 2)
    assert provider.list_models() == {"models": [KEY], "default_model": KEY}
    assert all(method == "GET" for method, *_ in calls)
    calls.clear()
    assert provider.generate_text("entrada", "sistema") == "respuesta real del fixture"
    assert calls == [
        ("GET", "/api/info", None, None),
        ("GET", "/api/model", AUTH, None),
        ("GET", "/api/model/default", AUTH, None),
        ("POST", "/api/session", AUTH, {"title": "Gaming History Studio", "model": {
            "providerID": "fixture", "id": "fixture-chat"}, "permissions": DENIED}),
        ("POST", SESSION + "/generate", AUTH, {"prompt": "sistema\n\nTexto del usuario:\nentrada"}),
        ("DELETE", SESSION, AUTH, None),
    ]


def test_explicit_model_overrides_default_and_unknown_never_sends(server):
    url, _, calls = server
    assert OpenCodeServerProvider(url, "test-password", 2, KEY, default_model="invalid").generate_text("a", "b")
    calls.clear()
    with pytest.raises(AIError, match="no está disponible"):
        OpenCodeServerProvider(url, "test-password", 2, "invalid").generate_text("a", "b")
    assert not any(method == "POST" for method, *_ in calls)


@pytest.mark.parametrize("value", ["http://localhost:4096", "http://127.0.0.1.evil.test", "http://[::1]",
                                   "http://127.0.0.1@evil.test", "http://127.0.0.1:4096/api",
                                   "http://127.0.0.1:0", "http://127.0.0.1:65536"])
def test_nonlocal_or_invalid_url_fails_closed(value):
    with pytest.raises(AIError, match="URL|puerto"):
        OpenCodeServerProvider(value, "test-password", 2).list_models()


def test_auth_and_unauthenticated_server(server):
    url, responses, calls = server
    with pytest.raises(AIAuthFailed, match="Falta"):
        OpenCodeServerProvider(url, "", 2).list_models()
    assert not calls
    with pytest.raises(AIAuthFailed, match="rechazó"):
        OpenCodeServerProvider(url, "wrong", 2).list_models()
    calls.clear()
    responses["GET", "/api/info"] = (200, {"version": "2.4.1"})
    with pytest.raises(AIAuthFailed, match="no exige"):
        OpenCodeServerProvider(url, "test-password", 2).list_models()
    assert calls == [("GET", "/api/info", None, None)]


@pytest.mark.parametrize(("providers", "error", "message"), [
    ([], AIAuthFailed, "login"),
    ([{"id": "fixture"}], AIError, "no tiene modelos"),
])
def test_missing_login_or_models(server, monkeypatch, providers, error, message):
    url, responses, _ = server
    monkeypatch.setattr(opencode.time, "sleep", lambda _: None)
    responses["GET", "/api/model"] = (200, {"data": []})
    responses["GET", "/api/provider"] = (200, {"data": providers})
    with pytest.raises(error, match=message):
        OpenCodeServerProvider(url, "test-password", 2).list_models()


def test_down_and_timeout(server, monkeypatch):
    url, responses, _ = server
    responses["GET", "/api/info"] = (599, None)
    with pytest.raises(AITimeout):
        OpenCodeServerProvider(url, "test-password", 0.05).list_models()

    def unavailable(*args, **kwargs):
        raise opencode.httpx.ConnectError("not listening")

    monkeypatch.setattr(opencode.httpx.Client, "request", unavailable)
    with pytest.raises(AIServerUnavailable):
        OpenCodeServerProvider(url, "test-password", 2).list_models()


def test_generation_error_sanitized_and_session_deleted(server):
    url, responses, calls = server
    responses["POST", SESSION + "/generate"] = (500, {"data": {"status": 401, "secret": "not for clients"}})
    with pytest.raises(AIAuthFailed, match="modelo.*autenticación") as error:
        OpenCodeServerProvider(url, "test-password", 2, KEY).generate_text("a", "b")
    assert "not for clients" not in str(error.value)
    assert calls[-1][:2] == ("DELETE", SESSION)


def test_no_generation_without_confirmed_deny_all(server):
    url, responses, calls = server
    responses["POST", "/api/session"] = (200, {"data": {"id": "ses_fixture", "permissions": []}})
    with pytest.raises(AIError, match="bloqueo"):
        OpenCodeServerProvider(url, "test-password", 2, KEY).generate_text("a", "b")
    assert not any(path.endswith("/generate") for _, path, *_ in calls)
    assert calls[-1][:2] == ("DELETE", SESSION)


def test_connection_check_requires_marker_empty_history_and_no_permission_requests(server):
    url, responses, calls = server
    responses["POST", SESSION + "/generate"] = (200, {"data": {"text": "GHS_AI_READY"}})
    responses["GET", SESSION + "/message"] = (200, {"data": []})
    responses["GET", SESSION + "/permission"] = (200, {"data": []})
    provider = OpenCodeServerProvider(url, "test-password", 2, KEY)
    assert provider.check_status() == {"ready": True, "tools_disabled": True}
    assert calls[-1][:2] == ("DELETE", SESSION)
    responses["GET", SESSION + "/permission"] = (200, {"data": [{"id": "unexpected"}]})
    with pytest.raises(AIError, match="permisos pendientes"):
        provider.check_status()
    assert calls[-1][:2] == ("DELETE", SESSION)
