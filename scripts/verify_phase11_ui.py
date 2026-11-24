"""Test vision confirmation and note persistence in Edge with intercepted APIs."""
import argparse
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

PROJECT = "vision-ui-fixture"
MODEL = "fixture/vision"
WARNING = "La descripción es una propuesta de la IA: revísala antes de aceptarla"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    assets = [
        {"id": "img1", "name": "naranja.png", "kind": "image", "duration_seconds": 0},
        {"id": "img2", "name": "verde.webp", "kind": "image", "duration_seconds": 0},
        {"id": "audio", "name": "audio.mp3", "kind": "audio", "duration_seconds": 1},
    ]
    project_path = f"/api/projects/{PROJECT}"
    sends, writes = [], []

    def intercept(route):
        request = route.request
        path = urlsplit(request.url).path
        headers = {"access-control-allow-origin": args.web,
                   "access-control-allow-headers": "*",
                   "access-control-allow-methods": "GET, POST, PUT, OPTIONS"}
        if request.method == "OPTIONS":
            return route.fulfill(status=204, headers=headers)
        if path == project_path:
            result = {"id": PROJECT, "name": "Visión de prueba",
                      "assets": assets, "tracks": [], "transitions": []}
        elif path == "/api/ai/claude-model":
            result = {"model": "sonnet"}
        elif path == "/api/ai/models":
            result = {"models": ["fixture/text", MODEL], "default_model": "fixture/text",
                      "vision_models": [MODEL]}
        elif path == "/api/ai/vision/preview":
            ids = request.post_data_json["asset_ids"]
            result = {"images": [{"asset_id": id_, "bytes": 800} for id_ in ids],
                      "errors": [], "total_bytes": 800 * len(ids), "batches": 1}
        elif path == "/api/ai/vision":
            body = request.post_data_json
            assert request.headers["x-ghs-ai-action"] == "confirm"
            assert body["confirmed"] is True and body["model"] == MODEL
            ids = body["asset_ids"]
            sends.append(ids)
            result = {"provider": "opencode", "model": MODEL, "images": len(ids),
                      "batches": 1, "total_bytes": 800 * len(ids), "results": [
                          {"asset_id": id_, "status": "ok", "description": "Fondo [enlace omitido].",
                           "trimmed": True, "urls_removed": 1} for id_ in ids]}
        elif path == project_path + "/assets/img2/note" and request.method == "PUT":
            note = request.post_data_json["note"]
            writes.append(note)
            assets[1]["note"] = note
            result = assets[1]
        else:
            return route.fulfill(status=404, json={"error": {"message": "Ruta no simulada"}}, headers=headers)
        return route.fulfill(json=result, headers=headers)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        page.route("**/api/**", intercept)
        page.goto(args.web + f"/projects/{PROJECT}")
        panel = page.get_by_role("region", name="Análisis de imágenes con IA")
        first = panel.get_by_role("button", name="Analizar naranja.png")
        expect(panel.get_by_role("button", name="Analizar audio.mp3")).to_have_count(0)
        assert not sends and not writes
        panel.get_by_label("Proveedor de IA").select_option("opencode")
        expect(first).to_be_disabled()
        panel.get_by_role("button", name="Cargar modelos").click()
        model = panel.get_by_label("Modelo con imágenes")
        expect(model.locator("option[value='fixture/text']")).to_have_count(0)
        expect(first).to_be_disabled()
        model.select_option(MODEL)
        first.click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_contain_text(MODEL)
        expect(dialog).to_contain_text("800 B")
        expect(dialog).to_contain_text("Estas imágenes saldrán de este equipo hacia el proveedor elegido")
        dialog.get_by_role("button", name="Cancelar", exact=True).click()
        expect(dialog).not_to_be_visible()
        assert not sends and not writes

        panel.get_by_role("button", name="Seleccionar todas").click()
        panel.get_by_role("button", name="Analizar seleccionadas").click()
        expect(dialog).to_contain_text("Imágenes: 2")
        expect(dialog).to_contain_text("Lotes: 1")
        dialog.get_by_role("button", name="Enviar", exact=True).click()
        expect(panel.get_by_text(WARNING, exact=True)).to_have_count(2)
        expect(panel.get_by_text("Se ocultó un enlace", exact=False)).to_have_count(2)
        assert sends == [["img1", "img2"]] and not writes
        panel.get_by_role("listitem").filter(has_text="naranja.png").get_by_role(
            "button", name="Descartar", exact=True).click()
        expect(panel.get_by_text("Propuesta descartada.")).to_be_visible()
        assert not writes
        panel.get_by_label("Descripción propuesta para verde.webp").fill("Nota revisada en Edge.")
        panel.get_by_role("button", name="Aceptar y guardar nota").click()
        expect(panel.get_by_text("Nota guardada.")).to_be_visible()
        assert writes == ["Nota revisada en Edge."]
        page.reload()
        expect(panel.get_by_text(WARNING, exact=True)).to_have_count(0)
        page.get_by_text("Editar nota para IA", exact=True).click()
        expect(page.get_by_role("textbox", name="Nota de verde.webp", exact=True)).to_have_value("Nota revisada en Edge.")
        browser.close()

    print("Edge: confirmación individual y múltiple, cancelar, descartar y aceptar nota; sin inferencia.")


if __name__ == "__main__":
    main()
