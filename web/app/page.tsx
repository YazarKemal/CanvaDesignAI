"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BrandSelect } from "@/components/BrandSelect";
import { ChatInput } from "@/components/ChatInput";
import { ChatPromptCard } from "@/components/ChatPromptCard";
import { MockupWorkflow, type MockupPhase } from "@/components/MockupWorkflow";
import { StyleSelect } from "@/components/StyleSelect";
import { MENTOR_LINES } from "@/lib/mentor-lines";
import { pickRandom, SUGGESTIONS } from "@/lib/suggestions";
import {
  type AttachedImage,
  type FinalPromptResponse,
  type ListingRole,
  type MockupAnalyzeResponse,
  type RefinedStrategy,
} from "@/lib/mockup-types";
import type { ChatResponse, LogEntry } from "@/lib/types";

const TOOLS = ["canva", "magic media", "dall-e 3", "midjourney"];

const BUSY_PHASES: readonly MockupPhase[] = ["analyzing", "refining", "generating"];

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

  // ── Mockup Director workflow state ──
  const [image, setImage] = useState<AttachedImage | null>(null);
  const [workflowPhase, setWorkflowPhase] = useState<MockupPhase | "idle">("idle");
  const [analysis, setAnalysis] = useState<MockupAnalyzeResponse | null>(null);
  const [selectedDirection, setSelectedDirection] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [listingRole, setListingRole] = useState<ListingRole>("hero");
  const [strategy, setStrategy] = useState<RefinedStrategy | null>(null);
  const [finalPrompt, setFinalPrompt] = useState<FinalPromptResponse | null>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);

  const cycleSuggestion = useCallback(() => {
    setSuggestion((prev) => {
      const idx = SUGGESTIONS.indexOf(prev);
      return SUGGESTIONS[(idx + 1) % SUGGESTIONS.length];
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, loading, workflowPhase]);

  // Defer random suggestion to client mount only — avoids SSR hydration mismatch.
  useEffect(() => {
    setSuggestion(pickRandom(SUGGESTIONS));
  }, []);

  // Pick a random mentor line on client mount — avoids SSR hydration mismatch.
  useEffect(() => {
    setMentorIdx(Math.floor(Math.random() * MENTOR_LINES.length));
  }, []);

  // Revoke the object URL backing the attached artwork preview when it changes
  // or is cleared, so we don't leak memory.
  useEffect(() => {
    return () => {
      if (image) URL.revokeObjectURL(image.url);
    };
  }, [image]);

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

  function handleImageChange(file: File | null) {
    if (!file) {
      setImage(null);
      setWorkflowError(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setImage({ file, name: file.name, url, mimeType: file.type });
    setWorkflowError(null);
  }

  async function submit() {
    if (loading) return;
    const concept = input.trim();
    if (!concept && !image) return;

    if (image) {
      await submitMockup(concept);
    } else {
      await submitChat(concept);
    }
  }

  // ── Legacy text-only chat flow (unchanged behaviour). ──
  async function submitChat(concept: string) {
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

  // ── Mockup Director workflow: analyze → refine → generate. ──
  async function submitMockup(text: string) {
    if (!image) return;
    setHistory((h) => [...h, text || `[mockup] ${image.name}`]);
    setHistoryIdx(null);
    setInput("");
    setWorkflowPhase("analyzing");
    setWorkflowError(null);
    setAnalysis(null);
    setStrategy(null);
    setFinalPrompt(null);
    setSelectedDirection(null);
    setAnswers({});
    setListingRole("hero");
    cycleSuggestion();

    const form = new FormData();
    form.append("file", image.file, image.name);
    form.append("marketplace", "Etsy");
    if (text) form.append("creative_direction", text);

    try {
      const res = await fetch("/api/mockup/analyze", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) {
        setWorkflowPhase("error");
        setWorkflowError(data?.detail ?? `analysis failed (${res.status})`);
        return;
      }
      const payload = data as MockupAnalyzeResponse;
      setAnalysis(payload);
      setWorkflowPhase("analysis");
      // Preselect the recommended direction (user can still change it).
      const recommended = payload.recommended_directions?.find((d) => d.recommended);
      if (recommended) setSelectedDirection(recommended.id);
    } catch {
      setWorkflowPhase("error");
      setWorkflowError("Could not reach the mockup director.");
    }
  }

  async function refine() {
    if (!analysis || !selectedDirection) return;
    setWorkflowPhase("refining");
    setWorkflowError(null);
    try {
      const res = await fetch("/api/mockup/refine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          analysis,
          selected_direction: selectedDirection,
          answers,
          listing_role: listingRole,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setWorkflowPhase("error");
        setWorkflowError(data?.detail ?? `refine failed (${res.status})`);
        return;
      }
      setStrategy(data as RefinedStrategy);
      setWorkflowPhase("strategy");
    } catch {
      setWorkflowPhase("error");
      setWorkflowError("Could not reach the mockup director.");
    }
  }

  async function generate() {
    if (!analysis || !selectedDirection) return;
    setWorkflowPhase("generating");
    setWorkflowError(null);
    try {
      const res = await fetch("/api/mockup/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          analysis,
          selected_direction: selectedDirection,
          answers,
          listing_role: listingRole,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setWorkflowPhase("error");
        setWorkflowError(data?.detail ?? `generate failed (${res.status})`);
        return;
      }
      setFinalPrompt(data as FinalPromptResponse);
      setWorkflowPhase("done");
    } catch {
      setWorkflowPhase("error");
      setWorkflowError("Could not reach the mockup director.");
    }
  }

  function resetWorkflow() {
    setImage(null);
    setWorkflowPhase("idle");
    setAnalysis(null);
    setStrategy(null);
    setFinalPrompt(null);
    setSelectedDirection(null);
    setAnswers({});
    setListingRole("hero");
    setWorkflowError(null);
  }

  function historyPrev() {
    if (history.length === 0) return;
    const idx = historyIdx === null ? history.length - 1 : Math.max(0, historyIdx - 1);
    setHistoryIdx(idx);
    setInput(history[idx]);
  }

  const busy = loading || BUSY_PHASES.includes(workflowPhase as MockupPhase);

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
            disabled={busy}
            suggestion={input ? undefined : suggestion}
            onSuggestionAccept={cycleSuggestion}
            image={image}
            onImageChange={handleImageChange}
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
          {/* Mockup Director workflow, in the same terminal log area */}
          {workflowPhase !== "idle" && (
            <div className="space-y-4">
              {image && (
                <div className="border-l border-zinc-700 pl-4">
                  <p className="text-xs uppercase tracking-widest text-zinc-500">
                    attached artwork
                  </p>
                  <img
                    src={image.url}
                    alt={image.name}
                    className="mt-2 max-h-48 w-auto border border-zinc-700"
                    data-testid="mockup-image-preview"
                  />
                </div>
              )}
              <MockupWorkflow
                phase={workflowPhase as MockupPhase}
                analysis={analysis}
                selectedDirectionId={selectedDirection}
                answers={answers}
                listingRole={listingRole}
                strategy={strategy}
                finalPrompt={finalPrompt}
                error={workflowError}
                onSelectDirection={setSelectedDirection}
                onAnswer={(key, value) =>
                  setAnswers((prev) => ({ ...prev, [key]: value }))
                }
                onListingRole={setListingRole}
                onRefine={refine}
                onGenerate={generate}
                onReset={resetWorkflow}
              />
            </div>
          )}
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
