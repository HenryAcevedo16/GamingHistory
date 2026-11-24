import assert from "node:assert/strict";
import test from "node:test";
import { geometry, historyStep, initialHistory, transform } from "../src/lib/timeline.ts";

const clip = { id: "clip", start_seconds: 2, source_in_seconds: 0.25, duration_seconds: 3 };
test("position and width use actual seconds at both zoom levels", () => {
  assert.deepEqual(geometry(clip, 80), { left: 160, width: 240 });
  assert.deepEqual(geometry(clip, 160), { left: 320, width: 480 });
  assert.deepEqual(geometry(transform(clip, "move", 1.25), 80), { left: 260, width: 240 });
});
test("start trim moves the source and preserves the end; end trim preserves the source", () => {
  assert.deepEqual(transform(clip, "start", 0.5), { ...clip, start_seconds: 2.5, duration_seconds: 2.5, source_in_seconds: 0.75 });
  assert.deepEqual(transform(clip, "end", -1), { ...clip, duration_seconds: 2 });
  assert.equal(transform(clip, "end", -4).duration_seconds, -1, "invalid edits must reach backend validation");
  const subtitle = { id: "cue", start_seconds: 0, duration_seconds: 1, text: "hola" };
  assert.equal(Object.hasOwn(transform(subtitle, "start", 0.25), "source_in_seconds"), false);
});
test("undo and redo preserve at least 20 edits, and a new branch clears redo", () => {
  const state = (n) => ({ tracks: [{ id: "v", kind: "video", name: "Video", clips: [{ ...clip, start_seconds: n }] }], transitions: [] });
  let history = initialHistory(state(0));
  for (let n = 1; n <= 30; n++) history = historyStep(history, state(n));
  for (let n = 0; n < 25; n++) history = historyStep(history, "undo");
  assert.deepEqual(history.current, state(5));
  for (let n = 0; n < 25; n++) history = historyStep(history, "redo");
  assert.deepEqual(history.current, state(30));
  history = historyStep(historyStep(history, "undo"), state(99));
  assert.deepEqual(historyStep(history, "redo").current, state(99));
});
