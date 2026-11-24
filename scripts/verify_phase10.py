"""Verify the real upload/editor workflow in Edge; use an isolated Studio instance."""

import argparse
import hashlib
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-n", *map(str, args)], check=True)


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_cancel(page, workspace, folder, route):
    source = folder / "cancel.wav"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440", "-t", "90", source)
    # Supply a real disk file to a browser drop event rather than selecting it in Studio.
    page.evaluate("""() => {
      const input = document.createElement("input");
      input.type = "file";
      input.id = "phase10-drop-fixture";
      input.hidden = true;
      document.body.append(input);
    }""")
    page.locator("#phase10-drop-fixture").set_input_files(source)
    transfer = page.evaluate_handle("""() => {
      const drop = new DataTransfer();
      drop.items.add(document.querySelector("#phase10-drop-fixture").files[0]);
      document.querySelector("#phase10-drop-fixture").remove();
      return drop;
    }""")
    page.get_by_text("O suelta archivos aquí.", exact=False).locator("..").dispatch_event("drop", {"dataTransfer": transfer})
    expect(page.get_by_label("Nota opcional para cancel.wav")).to_be_visible()
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.enable")

    def throttle(rate):
        cdp.send("Network.emulateNetworkConditions", {
            "offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": rate,
        })

    def wait_until(condition):
        deadline = time.monotonic() + 8
        while not condition():
            assert time.monotonic() < deadline, "No se observó el estado esperado del archivo en disco"
            time.sleep(0.05)

    throttle(350_000)
    try:
        page.get_by_role("button", name="Subir archivos", exact=True).click()
        expect(page.get_by_role("progressbar", name="Subida de cancel.wav")).to_be_visible()
        def partial():
            return any(0 < path.stat().st_size < source.stat().st_size for path in workspace.rglob(source.name))
        wait_until(partial)
        page.get_by_role("button", name="Cancelar subida", exact=True).press("Enter")
    finally:
        throttle(-1)
        cdp.detach()
    wait_until(lambda: not list(workspace.rglob(source.name)))
    expect(page.get_by_role("status").filter(has_text="Subida detenida. 0 de 1 confirmados")).to_be_visible()
    assert len(page.request.get(route).json()["assets"]) == 5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", default="http://127.0.0.1:3000")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--exercise-cancel", action="store_true")
    args = parser.parse_args()
    folder = (args.evidence / f"phase10-{uuid4().hex[:8]}").resolve()
    assert not folder.is_relative_to(args.workspace.resolve())
    folder.mkdir(parents=True)
    a, b, voice, music, still, invalid = [folder / name for name in (
        "video-a.mp4", "video-b.mp4", "narracion.wav", "musica.wav", "foto.png", "no-es-audio.wav"
    )]
    for path, pattern in ((a, "testsrc"), (b, "testsrc2")):
        ffmpeg("-f", "lavfi", "-i", f"{pattern}=size=160x90:rate=24", "-t", "1",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", path)
    for path, frequency, duration in ((voice, 440, 1), (music, 220, 4)):
        ffmpeg("-f", "lavfi", "-i", f"sine=frequency={frequency}", "-t", duration, path)
    ffmpeg("-f", "lavfi", "-i", "color=blue:s=160x90", "-frames:v", "1", "-update", "1", still)
    invalid.write_bytes(b"this is not WAV")
    originals = {file.name: hash_file(file) for file in (a, b, voice, music, still, invalid)}

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1480, "height": 1000}, reduced_motion="reduce")
        page.set_default_timeout(15_000)
        errors, ai_calls = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: ai_calls.append(request.url) if "/api/ai" in request.url else None)
        api = args.api + "/api"
        installed = page.request.post(api + "/plugins/ffmpeg/install", data={"confirm_permissions": True})
        assert installed.ok, installed.text()
        connected = page.request.post(api + "/plugins/ffmpeg/connect")
        assert connected.ok, connected.text()

        project_name = f"Fase 10 · {folder.name}"
        page.goto(args.web + "/projects")
        page.get_by_label("Nombre del proyecto").fill(project_name)
        page.get_by_role("button", name="Crear proyecto").click()
        expect(page.get_by_role("heading", name=project_name)).to_be_visible()
        route = f"{api}/projects/{page.url.rsplit('/', 1)[-1]}"
        assert page.request.get(route).json()["assets"] == []

        with page.expect_file_chooser() as chooser:
            page.get_by_role("button", name="Elegir archivos").press("Enter")
        assert chooser.value.is_multiple()
        chooser.value.set_files([a, b, invalid, voice, music, still])
        queue = page.get_by_role("region", name="Cola de importación")
        note = "Entrevista: usar solo el primer minuto."
        queue.get_by_label("Nota opcional para video-a.mp4", exact=True).fill(note)
        queue.get_by_role("button", name="Subir video-b.mp4 en la cola").press("Enter")
        expect(queue.get_by_text("1. video-b.mp4", exact=True)).to_be_visible()
        expect(queue.get_by_role("button", name="Subir video-b.mp4 en la cola")).to_be_focused()
        assert page.request.get(route).json()["assets"] == []
        queue.get_by_role("button", name="Subir archivos", exact=True).press("Enter")
        expect(page.get_by_role("status").filter(has_text="5 de 6 importados. 1 con error.")).to_be_visible()
        expect(queue.get_by_text("ffprobe falló:", exact=False)).to_be_visible()
        queue.get_by_label("Uso de musica.wav").select_option(label="Música de fondo")
        expect(queue.get_by_label("Inicio de musica.wav")).to_have_value("zero")
        expect(queue.get_by_label("Inicio de narracion.wav")).to_have_value("next")
        expect(queue.get_by_label("Inicio de video-a.mp4")).to_have_value("next")
        queue.get_by_label("Inicio de foto.png").select_option(label="Empezar en 0")
        page.screenshot(path=folder / "01-cola.png", full_page=True)
        queue.get_by_role("button", name="Añadir todos en este orden").press("Enter")

        def appearance(path, start, duration):
            locator = page.locator("[data-clip]").filter(has_text=path.name)
            expect(locator).to_have_attribute("aria-label", f"{path.name}, {start} s, duración {duration} s")
            return locator

        appearance(b, 0, 1)
        a_clip = appearance(a, 1, 1)
        appearance(voice, 2, 1)
        appearance(music, 0, 4)
        appearance(still, 0, 1)
        a_clip.press("Enter")
        page.get_by_label("Posición (s)", exact=True).fill("5")
        page.get_by_role("button", name="Aplicar edición").press("Enter")
        appearance(a, 5, 1)
        page.get_by_role("button", name="Mover antes").press("Enter")
        appearance(a, 0, 1)
        appearance(b, 1, 1)
        page.get_by_role("button", name="Deshacer").press("Enter")
        appearance(a, 5, 1)
        page.get_by_role("button", name="Rehacer").press("Enter")
        appearance(a, 0, 1)
        page.get_by_role("button", name="Guardar timeline").press("Enter")
        expect(page.get_by_role("status").filter(has_text="Guardado")).to_be_visible()

        resources = page.get_by_role("region", name="Recursos")
        entry = resources.get_by_role("listitem").filter(has=page.get_by_text(a.name, exact=True))
        entry.get_by_text("Editar nota para IA", exact=True).click()
        expect(entry.get_by_label("Nota de video-a.mp4")).to_have_value(note)
        new_note = "Usar la apertura (nota editada)."
        entry.get_by_label("Nota de video-a.mp4").fill(new_note)
        entry.get_by_role("button", name="Guardar nota").press("Enter")
        expect(entry.get_by_role("status").filter(has_text="Nota guardada")).to_be_visible()
        page.reload()
        appearance(a, 0, 1)
        appearance(b, 1, 1)
        appearance(voice, 2, 1)
        appearance(music, 0, 4)
        appearance(still, 0, 1)
        expect(page.get_by_text("Al pedir un plan de guion y cortes", exact=False)).to_be_visible()
        page.screenshot(path=folder / "02-reabierto.png", full_page=True)
        saved = page.request.get(route).json()
        names = {asset["id"]: asset["name"] for asset in saved["assets"]}
        clips = [[(names[clip["asset_id"]], clip["start_seconds"]) for clip in track["clips"]]
                 for track in saved["tracks"]]
        assert clips == [[(a.name, 0), (b.name, 1)], [(voice.name, 2)], [(music.name, 0)], [(still.name, 0)]], clips
        assert len(saved["assets"]) == 5
        assert next(asset for asset in saved["assets"] if asset["name"] == a.name)["note"] == new_note
        for asset in saved["assets"]:
            path = Path(asset["path"]).resolve(strict=True)
            assert path.is_relative_to(args.workspace.resolve()) and hash_file(path) == originals[asset["name"]]
            assert hash_file(folder / asset["name"]) == originals[asset["name"]]
        assert not list(args.workspace.rglob(invalid.name))
        if args.exercise_cancel:
            check_cancel(page, args.workspace, folder, route)
            print("Arrastre en Edge y cancelación tras escritura parcial: copia eliminada y ningún recurso nuevo.")
        assert not ai_calls and not errors, (ai_calls, errors)
        print(f"Edge {browser.version}: {clips}; 5 copias verificadas por SHA-256; 1 fallo; nota editada; sin llamadas de IA.")
        print(f"Proyecto: {page.url}\nEvidencia: {folder}")
        browser.close()


if __name__ == "__main__":
    main()
