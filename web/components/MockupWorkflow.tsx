"use client";

import { useState } from "react";
import {
  LISTING_ROLE_LABELS,
  LISTING_ROLES,
  type ClarifyingQuestion,
  type CreativeDirection,
  type FinalPromptResponse,
  type ListingRole,
  type MockupAnalyzeResponse,
  type RefinedStrategy,
} from "@/lib/mockup-types";

export type MockupPhase =
  | "analyzing"
  | "analysis"
  | "refining"
  | "strategy"
  | "generating"
  | "done"
  | "error";

interface MockupWorkflowProps {
  phase: MockupPhase;
  analysis: MockupAnalyzeResponse | null;
  selectedDirectionId: string | null;
  answers: Record<string, string>;
  listingRole: ListingRole;
  strategy: RefinedStrategy | null;
  finalPrompt: FinalPromptResponse | null;
  error: string | null;
  onSelectDirection: (id: string) => void;
  onAnswer: (key: string, value: string) => void;
  onListingRole: (role: ListingRole) => void;
  onRefine: () => void;
  onGenerate: () => void;
  onReset: () => void;
}

function allAnswered(questions: ClarifyingQuestion[], answers: Record<string, string>): boolean {
  return questions.every((q) => (answers[q.key] ?? "").length > 0);
}

/** Compact terminal label + subrow for a mockup-type field. */
function Field({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <p className="text-sm">
      <span className="text-zinc-500">{label}: </span>
      <span className="text-zinc-300">{value}</span>
    </p>
  );
}

export function MockupWorkflow({
  phase,
  analysis,
  selectedDirectionId,
  answers,
  listingRole,
  strategy,
  finalPrompt,
  error,
  onSelectDirection,
  onAnswer,
  onListingRole,
  onRefine,
  onGenerate,
  onReset,
}: MockupWorkflowProps) {
  // Copy feedback state is local to the "done" view.
  const [copied, setCopied] = useState(false);

  async function copyPrompt() {
    if (!finalPrompt) return;
    try {
      await navigator.clipboard.writeText(finalPrompt.final_prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable — no-op */
    }
  }

  if (phase === "analyzing") {
    return (
      <div className="border-l border-zinc-700 pl-4 text-sm text-zinc-500">
        &gt; analyzing artwork<span className="caret-blink">_</span>
      </div>
    );
  }

  if (phase === "error" && (!analysis || error)) {
    return (
      <div className="border-l border-zinc-700 pl-4 text-sm text-red-400" data-testid="mockup-error">
        &gt; {error ?? "Something went wrong."}
      </div>
    );
  }

  if (!analysis) return null;

  const asset = analysis.asset_analysis;
  const directions = analysis.recommended_directions ?? [];
  const best = analysis.best_recommendation;
  const questions = strategy ? strategy.remaining_questions : analysis.clarifying_questions ?? [];
  const canRefine = allAnswered(questions, answers) && phase !== "refining";
  const showRefineButton =
    phase === "analysis" || (phase === "strategy" && questions.length > 0);
  const canGenerate =
    phase === "strategy" && strategy && strategy.remaining_questions.length === 0;

  return (
    <div className="space-y-4 border-l border-zinc-700 pl-4">
      {/* Asset summary */}
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-widest text-zinc-500">artwork analysis</p>
        <p className="text-sm">
          <span className="text-zinc-500">product: </span>
          <span className="text-zinc-300">{asset.product_type}</span>
          {asset.product_category && (
            <>
              {" "}
              <span className="text-zinc-600">/ {asset.product_category}</span>
            </>
          )}
        </p>
        <Field label="style" value={asset.visual_style} />
        {asset.mood?.length > 0 && (
          <p className="text-sm">
            <span className="text-zinc-500">mood: </span>
            <span className="text-zinc-300">{asset.mood.join(", ")}</span>
          </p>
        )}
        {asset.orientation && (
          <Field label="orientation" value={`${asset.orientation} · ${asset.aspect_ratio}`} />
        )}
        {asset.dominant_colors?.length > 0 && (
          <p className="text-sm">
            <span className="text-zinc-500">palette: </span>
            <span className="text-zinc-300">{asset.dominant_colors.join(" ")}</span>
          </p>
        )}
      </div>

      {/* Creative directions */}
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-widest text-zinc-500">directions</p>
        {best?.message && <p className="text-sm text-zinc-400">{best.message}</p>}
        <div className="space-y-1">
          {directions.map((d: CreativeDirection) => {
            const selected = selectedDirectionId === d.id;
            return (
              <button
                key={d.id}
                type="button"
                data-testid={`direction-${d.id}`}
                onClick={() => onSelectDirection(d.id)}
                className={`block w-full border px-3 py-2 text-left text-sm transition-colors ${
                  selected
                    ? "border-white bg-white text-black"
                    : "border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                }`}
              >
                <span className="font-semibold">{d.title}</span>
                {d.recommended && (
                  <span className="ml-2 text-xs font-normal text-zinc-500">
                    [recommended]
                  </span>
                )}
                <span className="mt-0.5 block text-xs text-zinc-500">{d.rationale}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Clarifying questions */}
      {questions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-widest text-zinc-500">
            {strategy ? "remaining questions" : "clarify"}
          </p>
          {questions.map((q) => (
            <div key={q.key} className="space-y-1">
              <p className="text-sm text-zinc-300">{q.question}</p>
              <div className="flex flex-wrap gap-1">
                {q.options.map((opt) => {
                  const active = answers[q.key] === opt;
                  return (
                    <button
                      key={opt}
                      type="button"
                      data-testid={`answer-${q.key}-${opt}`}
                      onClick={() => onAnswer(q.key, opt)}
                      className={`select-none border px-2 py-1 text-xs transition-colors ${
                        active
                          ? "border-white bg-white text-black"
                          : "border-zinc-700 text-zinc-400 hover:bg-zinc-800"
                      }`}
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Listing role selector */}
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-widest text-zinc-500">listing role</p>
        <div className="flex flex-wrap gap-1">
          {LISTING_ROLES.map((role) => {
            const active = listingRole === role;
            return (
              <button
                key={role}
                type="button"
                data-testid={`role-${role}`}
                onClick={() => onListingRole(role)}
                className={`select-none border px-2 py-1 text-xs transition-colors ${
                  active
                    ? "border-white bg-white text-black"
                    : "border-zinc-700 text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                {LISTING_ROLE_LABELS[role]}
              </button>
            );
          })}
        </div>
      </div>

      {/* Refined strategy */}
      {strategy && (
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-widest text-zinc-500">refined direction</p>
          <Field label="environment" value={strategy.environment} />
          <Field label="surface / frame" value={strategy.surface_or_frame} />
          <Field label="lighting" value={strategy.lighting} />
          <Field label="camera" value={strategy.camera} />
          <Field label="composition" value={strategy.composition} />
          <Field label="styling" value={strategy.styling_notes} />
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2">
        {phase === "refining" && (
          <span className="text-sm text-zinc-500">
            &gt; refining<span className="caret-blink">_</span>
          </span>
        )}
        {showRefineButton && (
          <button
            type="button"
            data-testid="mockup-refine"
            onClick={onRefine}
            disabled={!canRefine}
            className="select-none border border-zinc-700 px-3 py-1 text-sm text-zinc-300 transition-colors hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:opacity-40"
          >
            {phase === "strategy" ? "refine again" : "refine direction"}
          </button>
        )}
        {phase === "generating" && (
          <span className="text-sm text-zinc-500">
            &gt; generating<span className="caret-blink">_</span>
          </span>
        )}
        {canGenerate && (
          <button
            type="button"
            data-testid="mockup-generate"
            onClick={onGenerate}
            className="select-none bg-white px-3 py-1 text-sm font-bold text-black transition-colors hover:bg-zinc-300"
          >
            generate prompt
          </button>
        )}
        <button
          type="button"
          data-testid="mockup-reset"
          onClick={onReset}
          className="select-none border border-zinc-700 px-3 py-1 text-sm text-zinc-500 transition-colors hover:bg-white hover:text-black"
        >
          start over
        </button>
      </div>

      {/* Final prompt */}
      {finalPrompt && phase === "done" && (
        <div className="space-y-2 border border-zinc-700 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-widest text-zinc-500">final prompt</p>
            <button
              type="button"
              data-testid="mockup-copy"
              onClick={copyPrompt}
              className="select-none border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 transition-colors hover:bg-white hover:text-black"
            >
              {copied ? "copied" : "copy prompt"}
            </button>
          </div>
          <p className="whitespace-pre-wrap text-sm text-zinc-200">{finalPrompt.final_prompt}</p>
          <p className="text-xs text-zinc-500">
            <span className="text-zinc-400">negative: </span>
            {finalPrompt.negative_prompt}
          </p>
          {finalPrompt.recommended_usage && (
            <p className="text-xs text-zinc-400">use as: {finalPrompt.recommended_usage}</p>
          )}
          {finalPrompt.preservation_notes?.length > 0 && (
            <ul className="list-inside list-disc text-xs text-zinc-500">
              {finalPrompt.preservation_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
