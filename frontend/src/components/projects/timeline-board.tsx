"use client";

import { Film, Music2, Subtitles } from "lucide-react";
import { useRef, useState, type PointerEvent } from "react";
import { emptyTrack, end, geometry, items, kinds, labels, transform, type Gesture, type Item, type Timeline, type Track } from "@/lib/timeline";
import { cn } from "@/lib/utils";

const icons = { video: Film, audio: Music2, subtitle: Subtitles };
const colors = { video: "border-violet-400/60 bg-violet-700/45", audio: "border-cyan-400/60 bg-cyan-800/50", subtitle: "border-amber-400/60 bg-amber-800/45" };
type Drag = { id: number; x: number; item: Item; track: Track; mode: Gesture };

export function TimelineBoard({ timeline, title, selected, select, change, busy }: {
  timeline: Timeline; title: (item: Item) => string; selected: string | null; select: (id: string) => void;
  change: (track: Track, item: Item) => void; busy: boolean;
}) {
  const [scale, setScale] = useState(112);
  const [preview, setPreview] = useState<Item | null>(null);
  const drag = useRef<Drag | null>(null);
  const tracks = kinds.flatMap((kind) => {
    const existing = timeline.tracks.filter((track) => track.kind === kind);
    return existing.length ? existing : [emptyTrack(kind, `empty-${kind}`)];
  });
  const extent = tracks.reduce((max, track) => items(track).reduce((value, item) => Math.max(value, end(item)), max), 0);
  const step = Math.max(scale >= 180 ? 0.5 : 1, 10 ** Math.ceil(Math.log10(Math.max(1, extent / 120))));
  const ticks = Math.ceil(Math.max(6, extent + step) / step);
  const width = Math.min(8_000_000, ticks * step * scale);

  function start(event: PointerEvent<HTMLElement>, track: Track, item: Item, mode: Gesture) {
    if (event.button !== 0 || !event.isPrimary || busy || track.locked || event.pointerType === "touch") return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { id: event.pointerId, x: event.clientX, track, item, mode };
    select(item.id);
  }
  function move(event: PointerEvent<HTMLElement>, done: boolean) {
    const active = drag.current;
    if (!active || active.id !== event.pointerId) return;
    const dx = event.clientX - active.x;
    const next = transform(active.item, active.mode, Math.round(dx / scale * 100) / 100);
    if (!done) { if (Math.abs(dx) >= 3) setPreview(next); return; }
    drag.current = null;
    setPreview(null);
    if (Math.abs(dx) >= 3) change(active.track, next);
  }
  function handlers(track: Track, item: Item, mode: Gesture) {
    return { onPointerDown: (event: PointerEvent<HTMLElement>) => start(event, track, item, mode),
      onPointerMove: (event: PointerEvent<HTMLElement>) => move(event, false),
      onPointerUp: (event: PointerEvent<HTMLElement>) => move(event, true),
      onLostPointerCapture: (event: PointerEvent<HTMLElement>) => {
        if (drag.current?.id === event.pointerId) { drag.current = null; setPreview(null); }
      } };
  }

  return <>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="timeline-heading" className="font-display text-lg font-semibold">Línea de tiempo</h2>
      <label className="flex items-center gap-2 font-mono text-xs text-muted-foreground">Zoom horizontal
        <input type="range" min="28" max="252" step="14" value={scale} onChange={(event) => setScale(Number(event.target.value))} className="w-24 accent-primary focus-visible:outline-2 focus-visible:outline-ring" />
        <span aria-hidden>{Math.round(scale / 112 * 100)}%</span>
      </label>
    </div>
    <p className="text-xs text-muted-foreground">Arrastra el cuerpo para mover o los bordes para recortar. Con teclado: ←/→ mueve, Mayús recorta el inicio, Alt recorta el fin.</p>
    <div tabIndex={0} role="region" aria-labelledby="timeline-heading" className="overflow-x-auto rounded-xl border border-white/10 bg-background/75 focus-visible:outline-2 focus-visible:outline-ring">
      <div style={{ width: width + 128, minWidth: "100%" }}>
        <div className="relative ml-32 h-8 overflow-hidden border-b border-white/10 font-mono text-[0.65rem] text-muted-foreground" aria-hidden>
          {Array.from({ length: ticks + 1 }, (_, index) => <span key={index} style={{ left: index * step * scale }} className="absolute top-0 border-l border-white/20 py-1.5 pl-1">{index * step} s</span>)}
        </div>
        {tracks.map((track) => {
          const Icon = icons[track.kind];
          return <div key={track.id} role="group" aria-label={`${labels[track.kind]}: ${track.name}`} className="flex h-14 border-b border-white/8 last:border-b-0">
            <div className="sticky left-0 z-20 flex w-32 shrink-0 items-center gap-2 border-r border-white/15 bg-card px-3 text-xs text-muted-foreground">
              <Icon aria-hidden className="size-4 shrink-0 text-primary" /><span className="truncate" title={track.name}>{track.name}{track.locked ? " · bloqueada" : ""}</span>
            </div>
            <div className="relative min-w-0 flex-1 overflow-hidden" style={{ backgroundImage: "linear-gradient(to right, rgb(255 255 255 / 0.075) 1px, transparent 1px)", backgroundSize: `${step * scale}px 100%` }}>
              {items(track).map((item) => {
                const displayed = preview?.id === item.id ? preview : item;
                const position = geometry(displayed, scale);
                const focused = selected === item.id;
                return <div key={item.id} className={cn("absolute top-2 flex h-10 select-none overflow-hidden rounded-md border", colors[track.kind], focused && "z-10 ring-2 ring-white/80", track.enabled === false && "opacity-50")}
                  style={{ left: position.left, width: Math.max(0.5, position.width) }}>
                  <button type="button" aria-pressed={focused} aria-label={`${title(item)}, ${item.start_seconds} s, duración ${item.duration_seconds} s`} data-clip={item.id}
                    className="absolute inset-0 cursor-grab truncate px-2 text-left text-xs font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-white active:cursor-grabbing"
                    onClick={() => select(item.id)} {...handlers(track, item, "move")}
                    onKeyDown={(event) => {
                      if (busy || track.locked || event.ctrlKey || event.metaKey || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
                      event.preventDefault();
                      change(track, transform(item, event.shiftKey ? "start" : event.altKey ? "end" : "move", event.key === "ArrowLeft" ? -0.1 : 0.1));
                    }}>{title(item)}</button>
                  {!track.locked && <>
                    <span aria-hidden data-trim="start" className="absolute inset-y-0 left-0 w-[min(7px,22%)] cursor-ew-resize border-r border-white/25 bg-white/10" {...handlers(track, item, "start")} />
                    <span aria-hidden data-trim="end" className="absolute inset-y-0 right-0 w-[min(7px,22%)] cursor-ew-resize border-l border-white/25 bg-white/10" {...handlers(track, item, "end")} />
                  </>}
                </div>;
              })}
            </div>
          </div>;
        })}
      </div>
    </div>
  </>;
}
