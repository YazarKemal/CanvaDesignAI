"use client";

import { useState } from "react";
import type { LogEntry } from "@/lib/types";

function CopyButton({
  text,
  label = "copy",
  className = "absolute right-2 top-2",
}: {
  text: string;
  label?: string;
  className?: string;
}) {
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
      className={`select-none border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 transition-colors hover:bg-white hover:text-black ${className}`}
    >
      {copied ? "copied" : label}
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
  const layer = card.layer_typography_architecture;
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
        {layer?.magic_media_style ? ` · ${layer.magic_media_style}` : ""}
      </p>

      {/* 1. Magic Media prompt — the copy-paste payload */}
      <p className="mt-3 text-xs text-zinc-600">01 // magic media prompt</p>
      <div className="relative mt-1 border border-zinc-800 bg-zinc-950 p-3 pr-16">
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
          {card.magic_media_prompt}
        </p>
        <CopyButton text={card.magic_media_prompt} />
      </div>
      <p className="mt-1 text-xs text-zinc-600">neg: {card.negative_prompt}</p>

      {/* 2. Layer & typography architecture */}
      <p className="mt-3 text-xs text-zinc-600">02 // layer &amp; typography architecture</p>
      <div className="mt-1 space-y-1 border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400">
        <p>
          headline: <span className="text-zinc-200">{layer.headline}</span>
        </p>
        <p>
          subtext: <span className="text-zinc-200">{layer.subtext}</span>
        </p>
        <p>palette: {layer.color_palette.join(" · ")}</p>
        <p>
          fonts: {layer.fonts.headline_font} / {layer.fonts.body_font}
        </p>
        <p>layers: {layer.background_layers}</p>
      </div>

      {/* 3. Direct action tip — step by step */}
      <p className="mt-3 text-xs text-zinc-600">03 // direct action tip</p>
      <ol className="mt-1 space-y-1 border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400">
        {card.direct_action_tip.map((step, i) => (
          <li key={i}>
            {i + 1}. {step}
          </li>
        ))}
      </ol>

      {/* Paste the whole card + directive into a Canva-connected AI chat */}
      {entry.pasteText ? (
        <div className="mt-3">
          <CopyButton
            text={entry.pasteText}
            label="copy for Claude / ChatGPT chat"
            className="relative w-full py-1.5 text-center"
          />
        </div>
      ) : null}
    </div>
  );
}
