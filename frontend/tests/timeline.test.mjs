import assert from "node:assert/strict";
import test from "node:test";
import { appendMedia, geometry, historyStep, initialHistory, items, moveIndex, newLane, reorderClip, transform } from "../src/lib/timeline.ts";

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

const media = (id, kind, duration_seconds) => ({ id, name: id, kind, duration_seconds });
const next = (asset) => ({ asset, start: "next" });
const zero = (asset, options = {}) => ({ asset, start: "zero", ...options });
const timeline = (...tracks) => ({ tracks, transitions: [] });
const track = (id, kind, clips, locked = false) => ({ id, kind, name: id, clips, locked });
const makeId = () => { let number = 0; return () => `new-${++number}`; };
const positions = (t) => items(t).map((item) => [item.asset_id, item.start_seconds, item.duration_seconds]);

test("queue move swaps adjacent entries without mutation and respects bounds", () => {
  const queue = ["a", "b", "c"];
  assert.deepEqual(moveIndex(queue, 1, -1), ["b", "a", "c"]);
  assert.deepEqual(moveIndex(queue, 1, 1), ["a", "c", "b"]);
  assert.equal(moveIndex(queue, 0, -1), queue);
  assert.equal(moveIndex(queue, 2, 1), queue);
  assert.deepEqual(queue, ["a", "b", "c"]);
});

test("append follows queue order after the last clip on the chosen track", () => {
  const tracks = timeline(track("v", "video", [{ ...clip, asset_id: "old" }]), track("other", "video", []));
  const result = appendMedia(tracks, [next(media("b", "video", 2)), next(media("a", "video", 3))], { video: "v" }, makeId());
  assert.deepEqual(positions(result.timeline.tracks[0]), [["old", 2, 3], ["b", 5, 2], ["a", 7, 3]]);
  assert.equal(result.first, result.timeline.tracks[0].clips[1].id);
  assert.equal(result.timeline.tracks[1], tracks.tracks[1]);
});

test("mixed sequential clips share a cursor, while zero-start music overlays separately", () => {
  const result = appendMedia(timeline(), [
    next(media("opening", "video", 2)), zero(media("music", "audio", 20), { music: true }),
    next(media("voice", "audio", 3)), next(media("still", "image", 0)),
  ], { audio: newLane, video: newLane }, makeId());
  assert.deepEqual(result.timeline.tracks.map(positions), [
    [["opening", 0, 2], ["still", 5, 1]], [["voice", 2, 3]], [["music", 0, 20]],
  ]);
  assert.equal(result.timeline.tracks[2].name, "Música de fondo");
});

test("zero start accepts a free interval but never overlaps even another newly placed clip", () => {
  const original = timeline(track("a", "audio", [{ ...clip, asset_id: "old" }]));
  const sound = media("music", "audio", 2);
  const entry = zero(sound, { zeroTrack: "a" });
  const result = appendMedia(original, [entry], {}, makeId());
  assert.deepEqual(positions(result.timeline.tracks[0]), [["old", 2, 3], ["music", 0, 2]]);
  assert.throws(() => appendMedia(original, [entry, entry], {}, makeId()), /se solapa/);
  assert.throws(() => appendMedia(timeline(track("a", "audio", [])), [entry, next(sound)], { audio: "a" }, makeId()), /se solapa/);
  assert.equal(original.tracks[0].clips.length, 1);
});

test("both sequential and zero placements reject locked or incompatible tracks", () => {
  const original = timeline(track("locked", "audio", [], true), track("v", "video", []));
  const asset = media("voice", "audio", 1);
  for (const id of ["locked", "v", "unknown"]) {
    assert.throws(() => appendMedia(original, [next(asset)], { audio: id }, makeId()), /pista de audio/);
    assert.throws(() => appendMedia(original, [zero(asset, { zeroTrack: id })], {}, makeId()), /pista de audio/);
  }
});

test("reorder uses chronological rather than storage order and compacts from zero", () => {
  const a = { ...clip, id: "a", start_seconds: 1, asset_id: "a" };
  const b = { ...clip, id: "b", start_seconds: 8, duration_seconds: 0.35, asset_id: "b" };
  const c = { ...clip, id: "c", start_seconds: 12, duration_seconds: 1, asset_id: "c" };
  const original = track("v", "video", [c, a, b]);
  const moved = reorderClip(original, "b", -1);
  assert.deepEqual(positions(moved), [["b", 0, 0.35], ["a", 0.35, 3], ["c", 3.35, 1]]);
  assert.equal(moved.clips[0].source_in_seconds, b.source_in_seconds);
  assert.equal(reorderClip(original, "a", -1), original);
  assert.equal(reorderClip(original, "missing", 1), original);
  assert.equal(reorderClip(original, "c", 1), original);
  const locked = { ...original, locked: true };
  assert.equal(reorderClip(locked, "b", -1), locked);
  const initial = timeline(original);
  const ordered = timeline(moved);
  const undone = historyStep(historyStep(initialHistory(initial), ordered), "undo");
  assert.equal(undone.current, initial);
  assert.equal(historyStep(undone, "redo").current, ordered);
});
