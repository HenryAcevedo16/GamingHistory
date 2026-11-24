import assert from "node:assert/strict";
import test from "node:test";
import { combinedNote, fitsNote, formatBytes, VISION_NOTE_LIMIT } from "../src/lib/vision.ts";

test("appending keeps the existing note and never overwrites it", () => {
  assert.equal(combinedNote("", "Escena naranja"), "Escena naranja");
  assert.equal(combinedNote(null, "  Escena naranja  "), "Escena naranja");
  assert.equal(combinedNote("Nota previa", "Escena naranja"), "Nota previa\nEscena naranja");
});

test("a combined note is accepted only up to the backend limit", () => {
  const note = "n".repeat(VISION_NOTE_LIMIT - 10);
  assert.equal(fitsNote(note, "123456789"), true);
  assert.equal(fitsNote(note, "1234567890"), false);
  assert.equal(fitsNote(undefined, "x".repeat(VISION_NOTE_LIMIT)), true);
});

test("sizes use Spanish units and never render unknown values as negative", () => {
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(-3), "0 B");
  assert.equal(formatBytes(800), "800 B");
  assert.equal(formatBytes(1536), "1,5 KB");
  assert.equal(formatBytes(8 * 1024 * 1024), "8 MB");
});
