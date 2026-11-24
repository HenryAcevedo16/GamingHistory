"""Exercise the real local backup UI against an existing Phase 7 test project."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", required=True)
    parser.add_argument("--api", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    destination = args.evidence / f"backups-{uuid4().hex[:8]}"

    def get(path):
        with urlopen(f"{args.api}/api{path}", timeout=10) as response:
            return response.read()

    original = get(f"/projects/{args.project}")
    timeline = get(f"/projects/{args.project}/timeline")
    tracks = json.loads(timeline)["tracks"]
    assert any(track.get("clips") for track in tracks) and any(track.get("cues") for track in tracks)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        print(f"Edge {browser.version}; real project {args.project}")
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.goto(f"{args.web}/projects")
        page.get_by_role("link", name="Respaldo", exact=True).click()
        expect(page.get_by_role("heading", name="Respaldo", exact=True)).to_be_visible()
        folder_input = page.get_by_role("textbox", name="Ruta absoluta")
        folder_input.fill(str(destination))
        page.get_by_role("button", name="Validar y guardar carpeta").click()
        expect(page.get_by_text("Carpeta de respaldo configurada.")).to_be_visible()
        page.get_by_role("combobox", name="Proyecto").select_option(args.project)

        def create(assets=False):
            page.get_by_role("checkbox", name="Incluir archivos de los recursos del proyecto").set_checked(assets)
            page.get_by_role("button", name="Generar vista previa").click()
            expect(page.get_by_role("heading", name="Contenido del respaldo")).to_be_visible()
            button = page.get_by_role("button", name="Crear respaldo")
            expect(button).to_be_disabled()
            expect(page.get_by_text("Opción de recursos activada" if assets else "Sin archivos de recursos", exact=False)).to_be_visible()
            page.screenshot(path=args.evidence / ("04-preview-assets.png" if assets else "01-preview.png"), full_page=True)
            page.get_by_role("checkbox", name="Confirmo guardar estos archivos en esta carpeta").check()
            with page.expect_response(lambda response: response.url.endswith("/api/backups")
                                      and response.request.method == "POST") as event:
                button.click()
            assert event.value.status == 201, event.value.text()
            item = event.value.json()
            expect(page.get_by_text("Respaldo creado y hashes comprobados.")).to_be_visible()
            return item["id"]

        created = create()
        backup = destination / created
        print(f"Default backup: {backup}")
        print(f"Files: {', '.join(sorted(path.name for path in backup.iterdir()))}")
        assert {child.name for child in backup.iterdir()} == {"manifest.json", "timeline.json", "metadata.json"}
        page.get_by_role("button", name="Actualizar lista").click()
        expect(page.get_by_text("Hashes sin verificar", exact=False)).to_be_visible()
        page.get_by_role("button", name="Verificar hashes").click()
        expect(page.get_by_text("Hashes verificados", exact=False)).to_be_visible()
        page.screenshot(path=args.evidence / "02-verified.png", full_page=True)

        def restore(backup_id, expected):
            with page.expect_response(lambda response: response.url.endswith(f"/api/backups/{backup_id}/restore")) as event:
                page.get_by_role("button", name="Restaurar como copia").first.click()
            assert event.value.status == expected, event.value.text()
            return event.value.json()

        copy = restore(created, 201)["id"]
        expect(page.get_by_text("Copia restaurada. El proyecto original no se modificó.")).to_be_visible()
        page.screenshot(path=args.evidence / "03-restored.png", full_page=True)
        restored = get(f"/projects/{copy}/timeline")
        (args.evidence / "original-timeline.json").write_bytes(timeline)
        (args.evidence / "restored-timeline.json").write_bytes(restored)
        assert restored == timeline and original == get(f"/projects/{args.project}")
        print(f"Copy {copy}: exact timeline JSON, {len(timeline)} bytes, SHA-256 {hashlib.sha256(timeline).hexdigest()}")

        with_assets = create(assets=True)
        asset_copy = restore(with_assets, 201)["id"]
        asset_project = json.loads(get(f"/projects/{asset_copy}"))
        all_original_assets = json.loads(original)["assets"]
        assert [asset["id"] for asset in asset_project["assets"]] == [asset["id"] for asset in all_original_assets]
        for old, new in zip(all_original_assets, asset_project["assets"], strict=True):
            assert new["path"] != old["path"]
            assert Path(new["path"]).read_bytes() == Path(old["path"]).read_bytes()
        assert get(f"/projects/{asset_copy}/timeline") == timeline
        print(f"Assets backup {with_assets}: {len(all_original_assets)} restored with same IDs and bytes, copy {asset_copy}")

        corrupted_id = create()
        corrupted = destination / corrupted_id / "timeline.json"
        with corrupted.open("r+b") as stream:
            first_byte = stream.read(1)
            stream.seek(0)
            stream.write(bytes([first_byte[0] ^ 1]))
        count = json.loads(get("/projects"))["total"]
        failure = restore(corrupted_id, 422)["error"]
        assert failure["code"] == "BACKUP_HASH_MISMATCH" and json.loads(get("/projects"))["total"] == count
        expect(page.get_by_role("alert").filter(has_text="timeline.json")).to_be_visible()
        expect(page.get_by_text("BACKUP_HASH_MISMATCH", exact=True)).to_be_visible()
        page.screenshot(path=args.evidence / "05-corruption-rejected.png", full_page=True)
        print(f"Corrupted manually in place (1 byte): {corrupted}; restore -> 422 {failure['code']}, no project inserted")
        browser.close()


if __name__ == "__main__":
    main()
