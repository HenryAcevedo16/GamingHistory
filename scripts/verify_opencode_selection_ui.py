"""Exercise model selection in Edge against intercepted API responses; no inference."""

import argparse
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

MODEL = "fixture/chat"
FALLBACK = "fixture/other"
PROJECT = "opencode-ui-fixture"
REQUIRED = {"ready": False, "code": "AI_MODEL_REQUIRED", "message": "Pulsa Cargar modelos y elige uno."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    catalog = {"models": [MODEL, FALLBACK], "default_model": None}
    requests = []

    def intercept(route):
        request = route.request
        url = urlsplit(request.url)
        headers = {"access-control-allow-origin": args.web, "access-control-allow-headers": "*",
                   "access-control-allow-methods": "GET, POST, OPTIONS"}
        if request.method == "OPTIONS":
            route.fulfill(status=204, headers=headers)
            return
        if url.path == "/api/ai/models":
            requests.append(("models", None))
            result = catalog
        elif url.path == "/api/ai/status":
            model = parse_qs(url.query).get("model", [None])[0]
            requests.append(("status", model))
            status = {
                MODEL: {"ready": True, "tools_disabled": True},
                FALLBACK: {"ready": False, "code": "AI_PROVIDER_UNAVAILABLE", "message": f"{FALLBACK} (HTTP 503)"},
            }.get(model, REQUIRED)
            result = {"providers": {"opencode": status}}
        elif url.path == "/api/ai/script":
            requests.append(("script", request.post_data_json["model"]))
            result = {"text": "Plan de prueba"}
        elif url.path == "/api/ai/claude-model":
            assert not request.post_data
            requests.append(("claude-model", None))
            result = {"model": "sonnet"}
        else:
            route.abort()
            raise AssertionError(f"Solicitud de IA no esperada: {url.path}")
        route.fulfill(json=result, headers=headers)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        page.route("**/api/ai/**", intercept)
        page.route(f"**/api/projects/{PROJECT}", lambda route: route.fulfill(json={
            "id": PROJECT, "name": "Proyecto de prueba", "assets": [], "tracks": [], "transitions": [],
        }, headers={"access-control-allow-origin": args.web}))
        page.goto(args.web + "/extensions")
        verify = page.get_by_role("button", name="Verificar conexión con OpenCode")
        load = page.get_by_role("button", name="Cargar modelos", exact=True)
        select = page.get_by_label("Modelo de OpenCode")
        expect(verify).to_be_enabled()
        assert requests == []

        verify.click()
        expect(page.get_by_role("alert").filter(has_text="AI_MODEL_REQUIRED")).to_be_visible()
        load.click()
        expect(select).to_have_value("")
        assert requests == [("status", None), ("models", None)]
        select.select_option(FALLBACK)
        verify.click()
        expect(page.get_by_role("alert").filter(has_text=f"AI_PROVIDER_UNAVAILABLE: {FALLBACK}")).to_be_visible()
        select.select_option(MODEL)
        verify.click()
        expect(page.get_by_text("Disponible · sin herramientas", exact=True)).to_be_visible()
        assert requests[-1] == ("status", MODEL)

        page.reload()
        expect(verify).to_be_enabled()
        assert requests[-1] == ("status", MODEL)
        load.click()
        expect(select).to_have_value(MODEL)

        page.goto(args.web + f"/projects/{PROJECT}")
        page.get_by_label("Proveedor de IA").select_option("opencode")
        load.click()
        expect(select).to_have_value(MODEL)
        warning = page.locator("#ai-plan-notes")
        expect(warning).to_contain_text(f"{MODEL} (vía OpenCode)")
        expect(warning).to_contain_text("nota guardada")
        page.get_by_label("Texto de guion").fill("Guion sintético para la prueba local")
        send = page.get_by_role("button", name="Enviar guion y sugerir estructura")
        send.click()
        expect(page.get_by_text("Plan de prueba", exact=True)).to_be_visible()
        assert requests[-1] == ("script", MODEL)

        # Do not silently use the configured model if the saved selection disappears.
        catalog.update(models=[FALLBACK], default_model=FALLBACK)
        page.get_by_role("button", name="Actualizar modelos", exact=True).click()
        expect(select).to_have_value("")
        expect(send).to_be_disabled()
        expect(warning).to_contain_text("No se enviará texto hasta elegirlo")
        page.get_by_label("Proveedor de IA").select_option("claude")
        expect(warning).to_contain_text("Anthropic · sonnet (vía Claude Code)")
        assert requests[-1] == ("claude-model", None)

        blocked_storage = browser.new_page()
        blocked_storage.add_init_script("""
            const original = { getItem: Storage.prototype.getItem, setItem: Storage.prototype.setItem };
            for (const method of ["getItem", "setItem"]) {
                Storage.prototype[method] = function (key) {
                    if (key === "ghs.ai.opencode.model") throw new Error("Storage blocked for this key");
                    return Reflect.apply(original[method], this, arguments);
                };
            }
        """)
        blocked_storage.route("**/api/ai/**", intercept)
        catalog.update(models=[MODEL], default_model=None)
        blocked_storage.goto(args.web + "/extensions")
        blocked_storage.get_by_role("button", name="Cargar modelos", exact=True).click()
        blocked_storage.get_by_label("Modelo de OpenCode").select_option(MODEL)
        blocked_storage.get_by_role("button", name="Verificar conexión con OpenCode").click()
        expect(blocked_storage.get_by_text("Disponible · sin herramientas", exact=True)).to_be_visible()
        browser.close()

    print("Edge: selección explícita, modelo recordado y validado, aviso del plan y envío interceptado. Sin inferencia.")


if __name__ == "__main__":
    main()
