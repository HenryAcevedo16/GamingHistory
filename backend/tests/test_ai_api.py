import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.routes import ai
from app.core.db import get_session
from app.editing.subtitles import parse_srt
from app.main import app
from app.models.audit import AuditLog

CONFIRM = {"X-GHS-AI-Action": "confirm"}
SRT = "1\n00:00:00,100 --> 00:00:01,321\nHola\nSegunda línea\n"


@pytest.fixture
def studio(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    SQLModel.metadata.create_all(engine)

    def session():
        with Session(engine) as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_session, session)
    client = TestClient(app, base_url="http://localhost")
    yield client, engine
    client.close()
    engine.dispose()


def test_no_implicit_or_nonlocal_calls(studio, monkeypatch):
    client, _ = studio
    monkeypatch.setattr(ai, "_provider", lambda: pytest.fail("Claude must not be called"))
    assert client.get("/api/ai/status").status_code == 403
    assert client.get("/api/ai/status", headers={**CONFIRM, "Origin": "https://external.example"}).status_code == 403
    assert client.get("/api/ai/status", headers={**CONFIRM, "Host": "external.example"}).status_code == 403
    assert client.post("/api/ai/script", headers=CONFIRM, json={"text": "texto"}).status_code == 403


@pytest.mark.parametrize("text", [r'C:\Users\Someone\secret.txt', "/home/someone/secret.txt",
                                  r"\\host\share", r"C:/local/hidden", "INTERNAL_KEY=private",
                                  "Bearer abcdefghijk", "sk-ant-testing-000"])
def test_sensitive_inputs_never_reach_provider(studio, monkeypatch, text):
    client, engine = studio
    # The provider factory may be built while evaluating the expression, but
    # generate_text must never run.
    class Provider:
        def generate_text(self, *args):
            pytest.fail("Sensitive contents reached Claude")

    monkeypatch.setattr(ai, "_provider", Provider)
    response = client.post("/api/ai/script", headers=CONFIRM, json={"confirmed": True, "text": text})
    assert response.status_code == 422 and response.json()["error"]["code"] == "AI_SENSITIVE_INPUT"
    with Session(engine) as session:
        assert [(r.status, r.detail) for r in session.exec(select(AuditLog)).all()] == [
            ("started", ""), ("error", "AI_SENSITIVE_INPUT")]


@pytest.mark.parametrize("text", ["", "texto sin tiempo", f"```srt\n{SRT}```",
                                  SRT.replace("01,321", "00,100"),
                                  SRT + "\n2\n00:00:01,300 --> 00:00:02,000\nSolapado"])
def test_parser_rejects_invalid_srt(text):
    with pytest.raises(ValueError):
        parse_srt(text)


def test_srt_input_output_and_explicit_application(studio, monkeypatch):
    client, _ = studio
    calls = []
    output = "salida no válida"

    class Provider:
        def generate_text(self, prompt, system):
            calls.append((prompt, system))
            return output

    monkeypatch.setattr(ai, "_provider", Provider)
    project = client.post("/api/projects", json={"name": "Prueba IA", "metadata": {"keep": True}}).json()
    path = f"/api/projects/{project['id']}"

    def subtitles(text):
        return client.post("/api/ai/subtitles", headers=CONFIRM,
                           json={"text": text, "mode": "correct", "confirmed": True})

    assert subtitles("inválido").json()["error"]["code"] == "AI_INVALID_SRT_INPUT"
    assert not calls
    assert subtitles(SRT).json()["error"]["code"] == "AI_INVALID_SRT_OUTPUT"
    output = SRT.replace("01,321", "01,322")
    assert subtitles(SRT).json()["error"]["code"] == "AI_INVALID_SRT_OUTPUT"
    output = "\ufeff" + SRT.replace("\n", "\r\n")
    cue = subtitles(SRT).json()["cues"][0]
    assert cue["text"] == "Hola\nSegunda línea" and cue["duration_seconds"] == 1.221
    assert all(prompt == SRT and "sin cambiar los tiempos" in system for prompt, system in calls)
    assert client.get(path).json() == project

    assert client.put(f"{path}/script-plan", json={"text": "Plan aceptado"}).status_code == 200
    assert client.get(path).json()["metadata"] == {"script_plan": "Plan aceptado", "keep": True}
    timeline = {"tracks": [{"kind": "subtitle", "name": "Subtítulos · Claude", "cues": [cue]}], "transitions": []}
    assert client.post(f"{path}/timeline/validate", json=timeline).status_code == 200
    assert client.get(f"{path}/timeline").json()["tracks"] == []
    assert client.put(f"{path}/timeline", json=timeline).status_code == 200
    assert client.get(f"{path}/timeline").json()["tracks"][0]["cues"][0]["id"] == cue["id"]


def test_generated_cues_may_split_but_not_leave_source_interval():
    original = parse_srt(SRT)
    split = parse_srt("1\n00:00:00,100 --> 00:00:00,900\nHola\n\n"
                      "2\n00:00:00,900 --> 00:00:01,321\nSegunda línea\n")
    assert ai._keeps_timing(original, split, "generate")
    assert not ai._keeps_timing(original, split, "correct")
    assert not ai._keeps_timing(original, parse_srt(SRT.replace("01,321", "02,000")), "generate")
