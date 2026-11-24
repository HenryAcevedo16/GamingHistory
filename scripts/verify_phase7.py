"""Real browser smoke check. Requires Python Playwright, installed Edge and FFmpeg.

Run against the local studio with FFmpeg already installed/connected. The two
optional delivery flags require their plugins to be installed and verified.
"""
import argparse
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright, expect


def run(*command):
    result = subprocess.check_output(command, text=True).strip()
    print(f"{subprocess.list2cmdline(command)} -> {result or 'exit 0'}", flush=True)
    return result


def drag(page, locator, dx):
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y, steps=8)
    page.mouse.up()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", default="http://127.0.0.1:3000")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--send-resolve", action="store_true")
    parser.add_argument("--send-capcut", action="store_true")
    args = parser.parse_args()
    args.workspace.mkdir(exist_ok=True)
    args.evidence.mkdir(exist_ok=True)
    suffix = uuid4().hex[:8]
    names = [f"phase7-{suffix}-{letter}.mp4" for letter in "ab"]
    for name, pattern in zip(names, ("testsrc", "testsrc2")):
        run("ffmpeg", "-v", "error", "-n", "-f", "lavfi", "-i", f"{pattern}=size=320x180:rate=24",
            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(args.workspace / name))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1480, "height": 1030}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        print(f"Microsoft Edge {browser.version} / headless", flush=True)

        def capture(name):
            path = args.evidence / f"{name}.png"
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=path, full_page=True)
            print(f"captura -> {path}", flush=True)

        page.goto(args.web + "/extensions")
        page.get_by_role("link", name="Proyectos", exact=True).click()
        name = f"Fase 7 · Verificación {suffix}"
        page.get_by_label("Nombre del proyecto").fill(name)
        page.get_by_role("button", name="Crear proyecto").click()
        expect(page.get_by_role("heading", name=name)).to_be_visible()
        route = f"{args.api}/api/projects/{page.url.rsplit('/', 1)[-1]}"
        print(f"proyecto -> {page.url}", flush=True)
        page.get_by_text("Importar por ruta local", exact=True).click()
        path_field = page.get_by_label("Ruta local")
        path_field.fill("../AGENTS.md")
        with page.expect_response(lambda r: r.url == route + "/media") as bad_import:
            page.get_by_role("button", name="Importar recurso").click()
        assert bad_import.value.status == 422
        expect(page.get_by_role("alert").filter(has_text="no están permitidas")).to_be_visible()
        for filename in names:
            path_field.fill(filename)
            page.get_by_role("button", name="Importar recurso").click()
            page.get_by_role("button", name=f"Añadir {filename} a Vídeo", exact=True).click()
            expect(page.locator("[data-clip]").filter(has_text=filename)).to_be_visible()

        a, b = [page.locator("[data-clip]").filter(has_text=filename) for filename in names]
        a.press("Shift+ArrowRight")
        expect(a).to_have_attribute("aria-label", f"{names[0]}, 0.1 s, duración 1.9 s")
        expect(page.get_by_text("Entrada de fuente 0.1 s", exact=False)).to_be_visible()
        page.get_by_role("button", name="Deshacer").click()
        expect(a).to_have_attribute("aria-label", f"{names[0]}, 0 s, duración 2 s")
        drag(page, a.locator("..").locator('[data-trim="end"]'), -112)
        expect(a).to_have_attribute("aria-label", f"{names[0]}, 0 s, duración 1 s")
        drag(page, b, -112)
        expect(b).to_have_attribute("aria-label", f"{names[1]}, 1 s, duración 2 s")
        page.get_by_role("button", name="Deshacer").click()
        expect(b).to_have_attribute("aria-label", f"{names[1]}, 2 s, duración 2 s")
        page.get_by_role("button", name="Rehacer").click()
        expect(b).to_have_attribute("aria-label", f"{names[1]}, 1 s, duración 2 s")
        page.get_by_role("button", name="Añadir subtítulo").click()
        page.get_by_label("Texto del subtítulo").fill("GHS Phase 7 - local")
        page.get_by_role("button", name="Aplicar edición").press("Enter")
        expect(page.locator("[data-clip]").filter(has_text="GHS Phase 7 - local")).to_be_visible()
        page.get_by_role("button", name="Guardar timeline").click()
        expect(page.get_by_text("Guardado", exact=True)).to_be_visible()
        page.reload()
        expect(a).to_have_attribute("aria-label", f"{names[0]}, 0 s, duración 1 s")
        expect(b).to_have_attribute("aria-label", f"{names[1]}, 1 s, duración 2 s")
        persisted = page.request.get(route + "/timeline").json()
        clips = persisted["tracks"][0]["clips"]
        assert [(c["start_seconds"], c["duration_seconds"]) for c in clips] == [(0, 1), (1, 2)]
        print("PUT + reload -> A=[0,1], B=[1,3], subtítulo persistido", flush=True)
        capture("01-timeline-persistida")

        b.focus()
        with page.expect_response(lambda r: r.url == route + "/timeline/validate") as overlap:
            b.press("ArrowLeft")
        assert overlap.value.status == 422
        expect(page.get_by_role("alert").filter(has_text="Solapamiento en pista de vídeo")).to_be_visible()
        expect(b).to_have_attribute("aria-label", f"{names[1]}, 1 s, duración 2 s")
        assert page.request.get(route + "/timeline").json() == persisted
        print("ArrowLeft -> POST timeline/validate 422; mensaje visible y posición intacta", flush=True)
        capture("02-solapamiento-rechazado")

        page.get_by_role("button", name="Renderizar con FFmpeg").click()
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_text("Elementos no exportables (1)")).to_be_visible()
        expect(dialog.get_by_text("Los subtítulos no se exportan", exact=False)).to_be_visible()
        assert page.request.get(f"{args.api}/api/jobs?project_id={route.rsplit('/', 1)[-1]}").json()["items"] == []
        capture("03-preflight-ffmpeg")
        dialog.get_by_role("button", name="Confirmar envío").click()
        expect(page.get_by_text("Completado · 100% (done)")).to_be_visible(timeout=30000)
        link = page.get_by_role("link", name="Descargar resultado")
        with page.expect_download() as download:
            link.click()
        result = args.evidence / "render-ffmpeg.mp4"
        download.value.save_as(result)
        info = json.loads(run("ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name", "-of", "json", str(result)))
        assert abs(float(info["format"]["duration"]) - 3) < 0.045
        assert {s["codec_name"] for s in info["streams"]} == {"h264", "aac"}
        capture("04-render-completado")

        for target, action, do_send, success in (
            ("resolve", "Enviar a Resolve", args.send_resolve, "Proyecto guardado en Resolve:"),
            ("capcut", "Generar borrador CapCut", args.send_capcut, "Borrador CapCut generado en"),
        ):
            review = page.request.get(f"{route}/exports/{target}/preflight").json()
            expect(page.locator(f"#{target}-availability")).to_have_text(review["reason"])
            button = page.get_by_role("button", name=action)
            if review["available"]:
                expect(button).to_be_enabled()
            else:
                expect(button).to_be_disabled()
                assert review["reason"]
            print(f"{target} -> available={review['available']}; {review['reason']}; verificadas={review['verified_capabilities']}", flush=True)
            if do_send:
                button.click()
                expect(dialog.get_by_text("Elementos no exportables", exact=False)).to_be_visible()
                capture(f"05-preflight-{target}")
                with page.expect_response(lambda r: r.request.method == "POST" and r.url in (route + "/exports/resolve", route + "/drafts"), timeout=90000) as sent:
                    dialog.get_by_role("button", name="Confirmar envío").click()
                assert sent.value.status == 201, sent.value.text()
                print(f"{sent.value.url} -> {sent.value.status} {sent.value.text()}", flush=True)
                expect(page.get_by_text(success, exact=False)).to_be_visible()
                capture(f"06-resultado-{target}")
        expect(page.get_by_text("Comprobando disponibilidad…", exact=True)).to_have_count(0)
        capture("07-disponibilidad")
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.get_by_role("heading", name="Línea de tiempo")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        capture("08-timeline-movil")
        page.set_viewport_size({"width": 1480, "height": 1030})
        page.get_by_role("link", name="Proyectos", exact=True).last.click()
        project_link = page.get_by_role("link", name=name, exact=False)
        expect(project_link).to_be_visible()
        capture("09-listado-proyectos")
        project_link.click()
        expect(page.get_by_role("heading", name=name)).to_be_visible()
        expect(b).to_have_attribute("aria-label", f"{names[1]}, 1 s, duración 2 s")
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
