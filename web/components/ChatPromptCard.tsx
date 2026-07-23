"use client";

import { useState } from "react";
import {
  formatForAspectRatio,
  TARGET_FORMAT_LABELS,
  type LogEntry,
  type PromptCard,
  type TargetFormat,
  type TextZone,
} from "@/lib/types";

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

const WIREFRAME_WIDTH = 24;
const WIREFRAME_HEIGHT = 5;

/** Monochrome ASCII wireframe of the canvas with the reserved text_zone
 * marked — visualizes composition/hierarchy without touching color. */
function buildWireframe(zone: TextZone): string[] {
  const top = "┌" + "─".repeat(WIREFRAME_WIDTH) + "┐";
  const bottom = "└" + "─".repeat(WIREFRAME_WIDTH) + "┘";
  const blank = "│" + " ".repeat(WIREFRAME_WIDTH) + "│";

  const centerLabel = "[ headline / subtext ]";
  const pad = WIREFRAME_WIDTH - centerLabel.length;
  const left = Math.floor(pad / 2);
  const right = pad - left;
  const fullLabelRow = "│" + " ".repeat(Math.max(left, 0)) + centerLabel + " ".repeat(Math.max(right, 0)) + "│";

  const halfLabel = "[ headline ]";
  const halfWidth = Math.floor(WIREFRAME_WIDTH / 2);
  const leftRow =
    "│" + halfLabel.padEnd(halfWidth, " ") + " ".repeat(WIREFRAME_WIDTH - halfWidth) + "│";
  const rightRow =
    "│" + " ".repeat(WIREFRAME_WIDTH - halfWidth) + halfLabel.padStart(halfWidth, " ") + "│";

  const rows: string[] = [top];
  const mid = Math.floor(WIREFRAME_HEIGHT / 2);

  for (let i = 0; i < WIREFRAME_HEIGHT; i++) {
    if (zone === "top" && i === 0) rows.push(fullLabelRow);
    else if (zone === "bottom" && i === WIREFRAME_HEIGHT - 1) rows.push(fullLabelRow);
    else if (zone === "center" && i === mid) rows.push(fullLabelRow);
    else if (zone === "left" && i === mid) rows.push(leftRow);
    else if (zone === "right" && i === mid) rows.push(rightRow);
    else rows.push(blank);
  }

  rows.push(bottom);
  return rows;
}

function ContrastLine({ ratio }: { ratio?: number }) {
  if (ratio === undefined) return null;
  const passes = ratio >= 4.5;
  return (
    <p className="mt-1 text-xs text-zinc-500">
      contrast: {ratio.toFixed(1)}:1 {passes ? "(AA ok)" : "(LOW - below 4.5:1)"}
    </p>
  );
}

function AdaptButtons({
  card,
  onAdapt,
  adapting,
}: {
  card: PromptCard;
  onAdapt?: (format: TargetFormat) => void;
  adapting?: boolean;
}) {
  if (!onAdapt) return null;

  const activeFormat = formatForAspectRatio(card.aspect_ratio);

  const otherFormats = (Object.keys(TARGET_FORMAT_LABELS) as TargetFormat[]).filter(
    (fmt) => fmt !== activeFormat,
  );
  if (otherFormats.length === 0) return null;

  return (
    <p className="mt-3 text-xs text-zinc-600">
      adapt to:{" "}
      {otherFormats.map((fmt) => (
        <button
          key={fmt}
          type="button"
          disabled={adapting}
          onClick={() => onAdapt(fmt)}
          className="ml-1 border border-zinc-700 px-2 py-0.5 text-zinc-400 transition-colors hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-50"
        >
          {adapting ? "…" : TARGET_FORMAT_LABELS[fmt]}
        </button>
      ))}
    </p>
  );
}

/** Resolve a value from the new hybrid format with a legacy fallback.
 *  After _ensure_hybrid_format runs, legacy flat keys (magic_media_prompt,
 *  layer_typography_architecture, etc.) are popped — so the canonical
 *  source is raster_background / native_typography. */
function resolveCardData(card: PromptCard) {
  const raster = card.raster_background;
  const native = card.native_typography;
  const legacyLayer = card.layer_typography_architecture;

  const magic_media_prompt =
    raster?.magic_media_prompt ?? card.magic_media_prompt ?? "";
  const negative_prompt =
    raster?.negative_prompt ?? card.negative_prompt ?? "";
  const magic_media_style =
    raster?.magic_media_style ?? legacyLayer?.magic_media_style;

  const headline = native?.headline ?? legacyLayer?.headline ?? "";
  const subtext = native?.subtext ?? legacyLayer?.subtext ?? "";
  const color_palette: string[] =
    native?.color_palette ?? legacyLayer?.color_palette ?? [];
  const fonts = native?.fonts ?? legacyLayer?.fonts ?? {
    headline_font: "—",
    body_font: "—",
  };
  const background_layers =
    native?.alignment_zone ?? legacyLayer?.background_layers ?? "";

  return {
    magic_media_prompt,
    negative_prompt,
    magic_media_style,
    headline,
    subtext,
    color_palette,
    fonts,
    background_layers,
  };
}

function CardBody({
  card,
  pasteText,
  contrastRatio,
  onAdapt,
  adapting,
}: {
  card: PromptCard;
  pasteText?: string;
  contrastRatio?: number;
  onAdapt?: (format: TargetFormat) => void;
  adapting?: boolean;
}) {
  const d = resolveCardData(card);
  const tip = card.direct_action_tip ?? [];

  return (
    <>
      {/* Parameters — plain grayscale text, no colored badges */}
      <p className="mt-1 text-xs text-zinc-500">
        # {card.aspect_ratio} · {card.target_tool} · zone: {card.text_zone}
        {d.magic_media_style ? ` · ${d.magic_media_style}` : ""}
      </p>

      {/* Composition wireframe — monochrome, shows where text_zone sits */}
      <pre className="mt-2 whitespace-pre border border-zinc-800 bg-zinc-950 p-2 text-xs leading-tight text-zinc-500">
        {buildWireframe(card.text_zone).join("\n")}
      </pre>

      {/* 1. Magic Media prompt — the copy-paste payload */}
      <p className="mt-3 text-xs text-zinc-600">01 // magic media prompt</p>
      <div className="relative mt-1 border border-zinc-800 bg-zinc-950 p-3 pr-16">
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
          {d.magic_media_prompt}
        </p>
        <CopyButton text={d.magic_media_prompt} />
      </div>
      <p className="mt-1 text-xs text-zinc-600">neg: {d.negative_prompt}</p>

      {/* 2. Layer & typography architecture */}
      <p className="mt-3 text-xs text-zinc-600">02 // layer &amp; typography architecture</p>
      <div className="mt-1 space-y-1 border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400">
        <p>
          headline: <span className="text-zinc-200">{d.headline}</span>
        </p>
        <p>
          subtext: <span className="text-zinc-200">{d.subtext}</span>
        </p>
        <p>palette: {d.color_palette.join(" · ")}</p>
        <ContrastLine ratio={contrastRatio} />
        <p>
          fonts: {d.fonts.headline_font} / {d.fonts.body_font}
        </p>
        <p>layers: {d.background_layers}</p>
      </div>

      {/* 3. Direct action tip — step by step */}
      <p className="mt-3 text-xs text-zinc-600">03 // direct action tip</p>
      <ol className="mt-1 space-y-1 border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400">
        {tip.map((step, i) => (
          <li key={i}>
            {i + 1}. {step}
          </li>
        ))}
      </ol>

      {/* Paste the whole card + directive into a Canva-connected AI chat */}
      {pasteText ? (
        <div className="mt-3">
          <CopyButton
            text={pasteText}
            label="copy for Claude / ChatGPT chat"
            className="relative w-full py-1.5 text-center"
          />
        </div>
      ) : null}

      {/* Omni-Channel: on-demand adaptation to other formats */}
      <AdaptButtons card={card} onAdapt={onAdapt} adapting={adapting} />
    </>
  );
}

export function ChatPromptCard({
  entry,
  onAdapt,
  adapting,
}: {
  entry: LogEntry;
  onAdapt?: (format: TargetFormat) => void;
  adapting?: boolean;
}) {
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

      {entry.selectedStyleName && (
        <p className="mt-1 text-xs text-zinc-500">
          Style: {entry.selectedStyleName}
        </p>
      )}

      <CardBody
        card={card}
        pasteText={entry.pasteText}
        contrastRatio={entry.contrastRatio}
        onAdapt={onAdapt}
        adapting={adapting}
      />
    </div>
  );
}
