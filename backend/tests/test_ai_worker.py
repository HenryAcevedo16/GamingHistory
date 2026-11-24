from __future__ import annotations

import io
import json
import sys

import pytest

from app.ai import worker
from app.ai.errors import AIError


def test_content_places_image_blocks_before_text():
    blocks = worker._content("prompt", [{"media_type": "image/jpeg", "data": "abc"}])
    assert blocks == [
        {"type": "text", "text": "Imagen 1:"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "abc"}},
        {"type": "text", "text": "prompt"},
    ]
    assert worker._content("prompt", None) == "prompt"
    assert worker._content("prompt", []) == "prompt"


@pytest.mark.parametrize("image", [
    {"media_type": "image/png", "data": "abc"},
    {"media_type": "image/jpeg", "data": ""},
    {"media_type": "image/jpeg"},
    "no es un objeto",
])
def test_content_rejects_anything_but_reduced_jpeg(image):
    with pytest.raises(AIError):
        worker._content("prompt", [image])


def test_worker_never_prints_image_data_or_exception_text(monkeypatch, capsys):
    secret = "c2VjcmV0by1kZS1pbWFnZW4tYmFzZTY0"
    payload = {"prompt": "p", "system": "s", "timeout": 1, "model": None,
               "images": [{"media_type": "image/jpeg", "data": secret}]}
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))

    async def boom(_payload, _checks):
        raise RuntimeError(f"el SDK falló con {_payload['images'][0]['data']}")

    monkeypatch.setattr(worker, "run", boom)
    worker.main()
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert "AI_FAILED" in output.out
