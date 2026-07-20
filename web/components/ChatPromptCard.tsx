"use client";

import { useState } from "react";
import type { LogEntry } from "@/lib/types";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable — no-op */
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="absolute right-2 top-2 select-none border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 transition-colors hover:bg-white hover:text-black"
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

export function ChatPromptCard({ entry }: { entry: LogEntry }) {
  // Terminal log entry: a left border, flowing top-to-bottom. No bubbles.
  if (entry.error) {
    return (
      <div className="border-l border-zinc-700 pl-4">
        <p className="text-sm text-zinc-300">$ {entry.concept}</p>
        <p className="mt-1 text-sm text-zinc-500">! {entry.error}</p>
      </div>
    );
  }

  const card = entry.card!;
  const status =
    entry.approved === false
      ? `best-effort · ${entry.score?.toFixed(1)}`
      : `approved · ${entry.score?.toFixed(1)}`;

  return (
    <div className="border-l border-zinc-700 pl-4">
      {/* Command line */}
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm text-white">$ {card.concept}</p>
        <span className="shrink-0 text-xs text-zinc-600">[{status}]</span>
      </div>

      {/* Parameters — plain grayscale text, no colored badges */}
      <p className="mt-1 text-xs text-zinc-500">
        # {card.aspect_ratio} · {card.target_tool}
        {card.art_direction?.magic_media_style
          ? ` · ${card.art_direction.magic_media_style}`
          : ""}
      </p>

      {/* The prompt — the copy-paste payload */}
      <div className="relative mt-2 border border-zinc-800 bg-zinc-950 p-3 pr-16">
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
          {card.prompt_text}
        </p>
        <CopyButton text={card.prompt_text} />
      </div>

      {/* Negative prompt + Canva tip */}
      <p className="mt-2 text-xs text-zinc-600">
        # neg: {card.negative_prompt}
      </p>
      {card.art_direction?.color_palette?.length ? (
        <p className="mt-1 text-xs text-zinc-600">
          # palette: {card.art_direction.color_palette.join(", ")}
        </p>
      ) : null}
      <p className="mt-1 text-xs text-zinc-500">// canva tip: {card.canva_tip}</p>
    </div>
  );
}
