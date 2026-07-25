"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BrandSelect } from "@/components/BrandSelect";
import { ChatInput } from "@/components/ChatInput";
import { ChatPromptCard } from "@/components/ChatPromptCard";
import { StyleSelect } from "@/components/StyleSelect";
import { MENTOR_LINES } from "@/lib/mentor-lines";
import { pickRandom, SUGGESTIONS } from "@/lib/suggestions";
import type { ChatResponse, LogEntry } from "@/lib/types";

const TOOLS = ["canva", "magic media", "dall-e 3", "midjourney"];

export default function Home() {
  const [input, setInput] = useState("");
  const [brand, setBrand] = useState<string | null>(null);
  const [style, setStyle] = useState<string | null>(null);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState<number | null>(null);
  // Start with a deterministic value to avoid SSR hydration mismatch.
  // The real random pick is deferred to a useEffect below (client-only).
  const [suggestion, setSuggestion] = useState(SUGGESTIONS[0]);
  const [mentorIdx, setMentorIdx] = useState(0);
  const [mentorVisible, setMentorVisible] = useState(true);
  const mentorTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const prefersReducedMotion = useRef(false);
  const nextId = useRef(1);
  const bottomRef = useRef<HTMLDivElement>(null);

  const cycleSuggestion = useCallback(() => {
    setSuggestion((prev) => {
      const idx = SUGGESTIONS.indexOf(prev);
      return SUGGESTIONS[(idx + 1) % SUGGESTIONS.length];
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, loading]);

  // Defer random suggestion to client mount only — avoids SSR hydration mismatch.
  useEffect(() => {
    setSuggestion(pickRandom(SUGGESTIONS));
  }, []);

  // Pick a random mentor line on client mount — avoids SSR hydration mismatch.
  useEffect(() => {
    setMentorIdx(Math.floor(Math.random() * MENTOR_LINES.length));
  }, []);

  // ^c clears the log, terminal-style (only when nothing is selected).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey && e.key.toLowerCase() === "c") {
        const selection = window.getSelection()?.toString() ?? "";
        if (selection.length === 0) {
          setEntries([]);
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Mentor-line rotation — 12 s fade, respect prefers-reduced-motion.
  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    prefersReducedMotion.current = mql.matches;
    const onPrefChange = (e: MediaQueryListEvent) => {
      prefersReducedMotion.current = e.matches;
    };
    mql.addEventListener("change", onPrefChange);

    if (!prefersReducedMotion.current) {
      mentorTimer.current = setInterval(() => {
        setMentorVisible(false);
        setTimeout(() => {
          setMentorIdx((i) => (i + 1) % MENTOR_LINES.length);
          setMentorVisible(true);
        }, 700);
      }, 12000);
    }

    return () => {
      mql.removeEventListener("change", onPrefChange);
      if (mentorTimer.current) clearInterval(mentorTimer.current);
    };
  }, []);

  async function submit() {
    const concept = input.trim();
    if (!concept || loading) return;

    setHistory((h) => [...h, concept]);
    setHistoryIdx(null);
    setInput("");
    setLoading(true);
    cycleSuggestion();

    const id = nextId.current++;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: concept, brand, style }),
      });
      const data = await res.json();

      if (!res.ok) {
        setEntries((e) => [
          ...e,
          { id, concept, error: data?.detail ?? `request failed (${res.status})` },
        ]);
      } else {
        const payload = data as ChatResponse;
        setEntries((e) => [
          ...e,
          {
            id,
            concept,
            card: payload.card,
            approved: payload.approved,
            score: payload.score,
            pasteText: payload.paste_text,
            contrastRatio: payload.contrast_ratio,
            selectedStyleName: payload.selected_style_name ?? null,
            variants: payload.variants,
            kitAssets: payload.kit_assets,
          },
        ]);
      }
    } catch {
      setEntries((e) => [...e, { id, concept, error: "network error" }]);
    } finally {
      setLoading(false);
    }
  }

  function historyPrev() {
    if (history.length === 0) return;
    const idx = historyIdx === null ? history.length - 1 : Math.max(0, historyIdx - 1);
    setHistoryIdx(idx);
    setInput(history[idx]);
  }

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4">
        {/* Header */}
        <header className="pt-16 text-center sm:pt-24">
          <h1 className="text-5xl font-bold tracking-[0.3em] text-white sm:text-6xl">
            CAVDESIGN
          </h1>
          <p className="mt-4 text-sm text-zinc-400">
            design anything. prompt. generate. done.
          </p>
          <p
            className="mt-3 text-xs text-zinc-600 transition-opacity duration-700"
            style={{ minHeight: "1.5em", opacity: mentorVisible ? 1 : 0 }}
          >
            {MENTOR_LINES[mentorIdx]}
          </p>
        </header>

        {/* Input, centered */}
        <div className="mx-auto mt-12 w-full max-w-2xl">
          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={submit}
            onHistoryPrev={historyPrev}
            disabled={loading}
            suggestion={input ? undefined : suggestion}
            onSuggestionAccept={cycleSuggestion}
          />
          <p className="mt-3 text-[10px] text-zinc-700">{TOOLS.join(" · ")}</p>
          <BrandSelect selected={brand} onChange={setBrand} />
          <details className="mt-2 text-xs text-zinc-600">
            <summary className="cursor-pointer select-none hover:text-zinc-400 transition-colors">
              Gelişmiş: stili elle seç
            </summary>
            <StyleSelect selected={style} onChange={setStyle} />
          </details>
          <div className="mt-2 text-xs text-zinc-600">
            <Link
              href="/ingest"
              className="hover:text-zinc-400 transition-colors"
            >
              ▶ Şablon yükle: kendi referanslarını ekle
            </Link>
          </div>
        </div>

        {/* Terminal log — flows top to bottom, left-bordered entries */}
        <section className="mx-auto mt-10 w-full max-w-2xl space-y-6 pb-10">
          {entries.map((entry) => (
            <ChatPromptCard
              key={entry.id}
              entry={entry}
            />
          ))}
          {loading && (
            <div className="border-l border-zinc-700 pl-4 text-sm text-zinc-500">
              &gt; generating<span className="caret-blink">_</span>
            </div>
          )}
          <div ref={bottomRef} />
        </section>
      </main>

      {/* Shortcuts */}
      <footer className="py-6 text-center text-xs text-zinc-600">
        ↵ generate&nbsp;&nbsp;·&nbsp;&nbsp;↑ history&nbsp;&nbsp;·&nbsp;&nbsp;^c clear
      </footer>
    </div>
  );
}
