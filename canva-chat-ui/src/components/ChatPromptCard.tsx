"use client";

import { useState } from "react";
import type { PromptCardData } from "@/types";

const aspectColorMap: Record<string, string> = {
  "1:1": "bg-accent-purple/15 text-accent-purple border-accent-purple/30",
  "16:9": "bg-accent-cyan/15 text-accent-cyan border-accent-cyan/30",
  "9:16": "bg-accent-pink/15 text-accent-pink border-accent-pink/30",
  "4:3": "bg-accent-green/15 text-accent-green border-accent-green/30",
  "3:4": "bg-accent-orange/15 text-accent-orange border-accent-orange/30",
};

const toolColorMap: Record<string, string> = {
  "Magic Media": "bg-accent-purple/15 text-accent-purple border-accent-purple/30",
  "Text to Image": "bg-accent-cyan/15 text-accent-cyan border-accent-cyan/30",
  "AI Video": "bg-accent-pink/15 text-accent-pink border-accent-pink/30",
  "AI Presentation": "bg-accent-green/15 text-accent-green border-accent-green/30",
  "AI Photo": "bg-accent-orange/15 text-accent-orange border-accent-orange/30",
};

function Badge({
  label,
  colorClass,
}: {
  label: string;
  colorClass: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${colorClass}`}
    >
      {label}
    </span>
  );
}

export default function ChatPromptCard({ data }: { data: PromptCardData }) {
  const [copied, setCopied] = useState(false);

  const aspectClass =
    aspectColorMap[data.aspectRatio] ??
    "bg-dark-500/50 text-dark-300 border-dark-500";

  const toolClass =
    toolColorMap[data.targetTool] ??
    "bg-dark-500/50 text-dark-300 border-dark-500";

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(data.promptText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for insecure contexts
      const textarea = document.createElement("textarea");
      textarea.value = data.promptText;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div className="message-enter w-full max-w-2xl rounded-xl border border-dark-600 bg-dark-800 overflow-hidden">
      {/* Header with badges */}
      <div className="flex items-center gap-2 px-4 pt-4 pb-2">
        <Badge label={`📐 ${data.aspectRatio}`} colorClass={aspectClass} />
        <Badge label={`🛠 ${data.targetTool}`} colorClass={toolClass} />
      </div>

      {/* Prompt text area */}
      <div className="px-4 py-3">
        <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-dark-300">
          Prompt
        </label>
        <div className="relative rounded-lg border border-dark-600 bg-dark-900 p-4">
          <p className="font-mono text-sm leading-relaxed text-zinc-200 whitespace-pre-wrap break-words pr-16">
            {data.promptText}
          </p>
          <button
            onClick={handleCopy}
            className="absolute top-3 right-3 flex items-center gap-1.5 rounded-md bg-dark-600 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-all hover:bg-dark-500 hover:text-white active:scale-95"
          >
            {copied ? (
              <>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span>Copied</span>
              </>
            ) : (
              <>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                </svg>
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Canva Tip section */}
      <div className="mx-4 mb-4 rounded-lg border border-accent-purple/20 bg-accent-purple/5 p-3">
        <div className="mb-1 flex items-center gap-1.5">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-accent-purple"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <span className="text-xs font-semibold uppercase tracking-wider text-accent-purple">
            Canva Tip
          </span>
        </div>
        <p className="text-sm leading-relaxed text-zinc-400">
          {data.canvaTip}
        </p>
      </div>
    </div>
  );
}
