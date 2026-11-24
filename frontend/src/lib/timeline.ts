export type Kind = "video" | "audio" | "subtitle";
export const kinds: Kind[] = ["video", "audio", "subtitle"];
export const labels = { video: "Vídeo", audio: "Audio", subtitle: "Subtítulos" };

export type Item = { id: string; start_seconds: number; duration_seconds: number; source_in_seconds?: number;
  asset_id?: string; name?: string | null; text?: string };
export type Track = { id: string; name: string; enabled?: boolean; locked?: boolean } &
  ({ kind: "subtitle"; cues: Item[] } | { kind: "video" | "audio"; clips: Item[] });
export type Timeline = { tracks: Track[]; transitions: { from_clip_id: string; to_clip_id: string }[] };
export type Asset = { id: string; name: string; kind: string; duration_seconds: number; note?: string | null };
export type ProjectSummary = { id: string; name: string; updated_at: string; assets: number; tracks: number };
export type Project = Timeline & { id: string; name: string; assets: Asset[]; metadata?: Record<string, unknown> };

export const items = (track: Track) => track.kind === "subtitle" ? track.cues : track.clips;
export const end = (item: Item) => item.start_seconds + item.duration_seconds;
export const seconds = (value: number) => Number(value.toFixed(6));
export function emptyTrack(kind: Kind, id: string): Track {
  const base = { id, name: labels[kind] };
  return kind === "subtitle" ? { ...base, kind, cues: [] } : { ...base, kind, clips: [] };
}
export const geometry = (item: Item, scale: number) => ({ left: item.start_seconds * scale, width: item.duration_seconds * scale });
export type Gesture = "move" | "start" | "end";
export function transform(item: Item, mode: Gesture, delta: number): Item {
  if (mode === "move") return { ...item, start_seconds: seconds(item.start_seconds + delta) };
  if (mode === "end") return { ...item, duration_seconds: seconds(item.duration_seconds + delta) };
  return { ...item, start_seconds: seconds(item.start_seconds + delta), duration_seconds: seconds(item.duration_seconds - delta),
    ...(item.source_in_seconds === undefined ? {} : { source_in_seconds: seconds(item.source_in_seconds + delta) }) };
}

export function withItems(track: Track, next: Item[]): Track {
  return track.kind === "subtitle" ? { ...track, cues: next } : { ...track, clips: next };
}

export function moveIndex<T>(list: T[], index: number, direction: -1 | 1): T[] {
  const other = index + direction;
  if (index < 0 || index >= list.length || other < 0 || other >= list.length) return list;
  const next = [...list];
  [next[index], next[other]] = [next[other], next[index]];
  return next;
}

export const mediaLane = (asset: Asset) => asset.kind === "image" ? "video" :
  asset.kind === "video" || asset.kind === "audio" ? asset.kind : null;
export type MediaLane = NonNullable<ReturnType<typeof mediaLane>>;
export const newLane = "new-track";
export type Placement = { asset: Asset; start: "next" | "zero"; zeroTrack?: string; music?: boolean };

export function appendMedia(timeline: Timeline, entries: Placement[], targets: Partial<Record<MediaLane, string>>,
  makeId: () => string): { timeline: Timeline; first: string } {
  const tracks = new Map(timeline.tracks.map((track) => [track.id, track]));
  const lanes = new Map<MediaLane, string>();
  function destination(kind: MediaLane, choice?: string, music?: boolean) {
    const track = choice === newLane ? { ...emptyTrack(kind, makeId()), ...(music ? { name: "Música de fondo" } : {}) } :
      choice ? tracks.get(choice) : undefined;
    if (!track || track.kind !== kind || track.locked) throw new Error(`Elige una pista de ${labels[kind].toLowerCase()} que no esté bloqueada.`);
    tracks.set(track.id, track);
    return track;
  }
  for (const { asset, start } of entries) {
    const kind = mediaLane(asset);
    if (!kind || (asset.kind !== "image" && !(asset.duration_seconds > 0))) throw new Error("Hay un recurso sin tipo o duración utilizable.");
    if (start === "next" && !lanes.has(kind)) lanes.set(kind, destination(kind, targets[kind]).id);
  }
  // For mixed media use one cursor, preserving the global selection order across lanes.
  let cursor = [...lanes.values()].flatMap((id) => items(tracks.get(id)!))
    .reduce((latest, item) => Math.max(latest, end(item)), 0);
  let first = "";
  for (const { asset, start, zeroTrack, music } of entries) {
    const kind = mediaLane(asset)!;
    const track = start === "zero" ? destination(kind, zeroTrack ?? newLane, music) : tracks.get(lanes.get(kind)!)!;
    const id = makeId();
    const item = { id, asset_id: asset.id, start_seconds: start === "zero" ? 0 : cursor, source_in_seconds: 0,
      duration_seconds: asset.kind === "image" ? 1 : asset.duration_seconds };
    if (items(track).some((other) => item.start_seconds < end(other) && other.start_seconds < end(item))) {
      throw new Error(`${asset.name} se solapa con otro clip en ${track.name}. Cambia su pista o su modo de inicio.`);
    }
    if (start === "next") cursor = end(item);
    if (!first) first = id;
    tracks.set(track.id, withItems(track, [...items(track), item]));
  }
  return { timeline: { ...timeline, tracks: [...tracks.values()] }, first };
}

export const chronological = (track: Track) => [...items(track)].sort((a, b) => a.start_seconds - b.start_seconds);

export function reorderClip(track: Track, id: string, direction: -1 | 1): Track {
  if (track.locked || track.kind === "subtitle") return track;
  const ordered = chronological(track);
  const next = moveIndex(ordered, ordered.findIndex((item) => item.id === id), direction);
  if (next === ordered) return track;
  let cursor = 0;
  return withItems(track, next.map((item) => {
    const moved = { ...item, start_seconds: cursor };
    cursor = end(moved);
    return moved;
  }));
}

export type History = { past: Timeline[]; current: Timeline; future: Timeline[] };
export const initialHistory = (current: Timeline): History => ({ current, past: [], future: [] });
export function historyStep(history: History, action: Timeline | "undo" | "redo"): History {
  const { past, current, future } = history;
  if (action === "undo") return past.length ? { past: past.slice(0, -1), current: past.at(-1)!, future: [current, ...future] } : history;
  if (action === "redo") return future.length ? { past: [...past, current], current: future[0], future: future.slice(1) } : history;
  return { past: [...past, current].slice(-50), current: action, future: [] };
}
