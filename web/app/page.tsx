"use client";

import { useEffect, useRef, useState } from "react";
import { ChatInput } from "@/components/ChatInput";
import { ChatPromptCard } from "@/components/ChatPromptCard";
import type { ChatResponse, LogEntry } from "@/lib/types";

const TOOLS = ["canva", "magic media", "dall-e 3", "midjourney"];

export default function Home() {
  const [input, setInput] = useState("");
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState<number | null>(null);
  const nextId = useRef(1);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, loading]);

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

  async function submit() {
    const concept = input.trim();
    if (!concept || loading) return;

    setHistory((h) => [...h, concept]);
    setHistoryIdx(null);
    setInput("");
    setLoading(true);

    const id = nextId.current++;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: concept }),
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
          <p className="mt-2 text-xs text-zinc-600">{TOOLS.join(" · ")}</p>
        </header>

        {/* Input, centered */}
        <div className="mx-auto mt-12 w-full max-w-2xl">
          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={submit}
            onHistoryPrev={historyPrev}
            disabled={loading}
          />
        </div>

        {/* Terminal log — flows top to bottom, left-bordered entries */}
        <section className="mx-auto mt-10 w-full max-w-2xl space-y-6 pb-10">
          {entries.map((entry) => (
            <ChatPromptCard key={entry.id} entry={entry} />
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
