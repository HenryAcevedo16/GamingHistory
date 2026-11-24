export type Kind = "video" | "audio" | "subtitle";
export const kinds: Kind[] = ["video", "audio", "subtitle"];
export const labels = { video: "Vídeo", audio: "Audio", subtitle: "Subtítulos" };

export type Item = { id: string; start_seconds: number; duration_seconds: number; source_in_seconds?: number;
  asset_id?: string; name?: string | null; text?: string };
export type Track = { id: string; name: string; enabled?: boolean; locked?: boolean } &
  ({ kind: "subtitle"; cues: Item[] } | { kind: "video" | "audio"; clips: Item[] });
export type Timeline = { tracks: Track[]; transitions: { from_clip_id: string; to_clip_id: string }[] };
export type Asset = { id: string; name: string; kind: string; duration_seconds: number };
export type ProjectSummary = { id: string; name: string; updated_at: string; assets: number; tracks: number };
export type Project = Timeline & { id: string; name: string; assets: Asset[] };

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

export type History = { past: Timeline[]; current: Timeline; future: Timeline[] };
export const initialHistory = (current: Timeline): History => ({ current, past: [], future: [] });
export function historyStep(history: History, action: Timeline | "undo" | "redo"): History {
  const { past, current, future } = history;
  if (action === "undo") return past.length ? { past: past.slice(0, -1), current: past.at(-1)!, future: [current, ...future] } : history;
  if (action === "redo") return future.length ? { past: [...past, current], current: future[0], future: future.slice(1) } : history;
  return { past: [...past, current].slice(-50), current: action, future: [] };
}
