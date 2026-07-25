"use client";

import { useCallback, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SourceType = "canva" | "behance" | "upload";

interface DeconstructResult {
  concept: string;
  aspect_ratio: string;
  target_tool: string;
  text_zone: string;
  canva_keywords?: string[];
  raster_background?: {
    magic_media_prompt: string;
    negative_prompt: string;
    layout_style?: string;
  };
  vector_elements?: Record<string, unknown>;
  native_typography?: {
    headline: string;
    subtext: string;
    headline_pt?: number;
    subtext_pt?: number;
    color_palette?: string[];
    fonts?: {
      headline_font: string;
      body_font: string;
    };
    alignment_zone?: string;
    micro_tags?: Record<string, unknown>;
  };
  direct_action_tip?: string[];
  source_type: string;
  source_ref: string;
  ingested_at: string;
  archetype: string;
  category: string;
  format: string;
  approved: boolean;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Inline helpers
// ---------------------------------------------------------------------------

function ColorSwatch({ hex }: { hex: string }) {
  return (
    <span
      className="inline-block h-5 w-5 border border-zinc-600 align-middle"
      style={{ backgroundColor: hex }}
      title={hex}
    />
  );
}

function FontBadge({ label, value }: { label: string; value: string }) {
  return (
    <span className="mr-3 inline-flex items-center gap-1.5 text-xs text-zinc-400">
      <span className="text-zinc-600">{label}</span>
      <span className="text-zinc-200">{value}</span>
    </span>
  );
}

function PtBadge({ label, value }: { label: string; value?: number }) {
  if (value === undefined || value === 0) return null;
  return (
    <span className="mr-3 inline-flex items-center gap-1 text-xs">
      <span className="text-zinc-600">{label}</span>
      <span className="rounded border border-zinc-700 px-1.5 py-0.5 text-zinc-200">
        {value}pt
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function IngestPage() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<SourceType>("upload");
  const [sourceRef, setSourceRef] = useState("");
  const [archetype, setArchetype] = useState("");
  const [category, setCategory] = useState("");
  const [canvasFormat, setCanvasFormat] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DeconstructResult | null>(null);
  const [jsonText, setJsonText] = useState("");
  const [reviewerNote, setReviewerNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ------------------------------------------------------------------
  // File selection
  // ------------------------------------------------------------------

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0] ?? null;
      setFile(f);
      setResult(null);
      setJsonText("");
      setError(null);
      setSaved(false);
      setSaveError(null);

      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
      }
      if (f) {
        setPreviewUrl(URL.createObjectURL(f));
      }
    },
    [previewUrl],
  );

  // ------------------------------------------------------------------
  // Deconstruct
  // ------------------------------------------------------------------

  const handleDeconstruct = useCallback(async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setJsonText("");
    setSaved(false);
    setSaveError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("source_type", sourceType);
      formData.append("source_ref", sourceRef);
      formData.append("archetype", archetype);
      formData.append("category", category);
      formData.append("canvas_format", canvasFormat);

      const res = await fetch("/api/ingest/deconstruct", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (!res.ok) {
        setError(data?.detail ?? `Deconstruction failed (${res.status})`);
      } else {
        setResult(data as DeconstructResult);
        setJsonText(JSON.stringify(data, null, 2));
      }
    } catch {
      setError("Network error — could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }, [file, sourceType, sourceRef, archetype, category, canvasFormat]);

  // ------------------------------------------------------------------
  // Approve & save
  // ------------------------------------------------------------------

  const handleApprove = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    setSaved(false);

    let card: DeconstructResult;
    try {
      card = JSON.parse(jsonText) as DeconstructResult;
    } catch {
      setSaveError("JSON parse error — fix the syntax before approving.");
      setSaving(false);
      return;
    }

    try {
      const res = await fetch("/api/ingest/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          card,
          reviewer_note: reviewerNote || null,
        }),
      });
      const data = await res.json();

      if (!res.ok) {
        setSaveError(data?.detail ?? `Approval failed (${res.status})`);
      } else {
        setSaved(true);
        setSaveError(null);
      }
    } catch {
      setSaveError("Network error — could not reach the backend.");
    } finally {
      setSaving(false);
    }
  }, [jsonText, reviewerNote]);

  // ------------------------------------------------------------------
  // Discard
  // ------------------------------------------------------------------

  const handleDiscard = useCallback(() => {
    setResult(null);
    setJsonText("");
    setError(null);
    setSaved(false);
    setSaveError(null);
    setReviewerNote("");
  }, []);

  // ------------------------------------------------------------------
  // Resolved card data (live from textarea so edits reflect instantly)
  // ------------------------------------------------------------------

  let liveCard: DeconstructResult | null = null;
  try {
    liveCard = JSON.parse(jsonText) as DeconstructResult;
  } catch {
    liveCard = result; // fall back to the last valid result on parse error
  }

  const native = liveCard?.native_typography;
  const palette = native?.color_palette ?? [];
  const fonts = native?.fonts;

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4">
        {/* Header */}
        <header className="pt-12 text-center sm:pt-16">
          <h1 className="text-3xl font-bold tracking-[0.2em] text-white sm:text-4xl">
            INGEST
          </h1>
          <p className="mt-2 text-xs text-zinc-500">
            template image → vision deconstruction → human review → corpus
          </p>
          <p className="mt-8 text-xs text-zinc-600">
            <a href="/" className="hover:text-zinc-400 transition-colors">
              &larr; back to generator
            </a>
          </p>
        </header>

        {/* ── Upload & metadata ─────────────────────────────────────── */}

        <section className="mx-auto mt-10 w-full max-w-2xl">
          {/* File picker */}
          <div className="border border-zinc-800 bg-zinc-950 p-4">
            <p className="text-xs text-zinc-600">01 // select template image</p>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={handleFileChange}
              className="mt-2 w-full text-sm text-zinc-400 file:mr-3 file:cursor-pointer file:border file:border-zinc-700 file:bg-black file:px-3 file:py-1.5 file:text-xs file:text-zinc-300 file:transition-colors hover:file:bg-zinc-900"
            />
            <p className="mt-1 text-xs text-zinc-600">
              PNG, JPEG, WebP — max 10 MB
            </p>
          </div>

          {/* Metadata fields */}
          <div className="mt-3 border border-zinc-800 bg-zinc-950 p-4">
            <p className="text-xs text-zinc-600">02 // metadata</p>
            <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {/* source_type */}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-zinc-500">source_type</span>
                <select
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as SourceType)}
                  className="border border-zinc-700 bg-black px-2 py-1.5 text-xs text-zinc-300"
                >
                  <option value="canva">canva</option>
                  <option value="behance">behance</option>
                  <option value="upload">upload</option>
                </select>
              </label>

              {/* source_ref */}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-zinc-500">source_ref</span>
                <input
                  type="text"
                  value={sourceRef}
                  onChange={(e) => setSourceRef(e.target.value)}
                  placeholder="URL or filename"
                  className="border border-zinc-700 bg-black px-2 py-1.5 text-xs text-zinc-300 placeholder:text-zinc-700"
                />
              </label>

              {/* archetype */}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-zinc-500">archetype</span>
                <input
                  type="text"
                  value={archetype}
                  onChange={(e) => setArchetype(e.target.value)}
                  placeholder="e.g. instagram_story"
                  className="border border-zinc-700 bg-black px-2 py-1.5 text-xs text-zinc-300 placeholder:text-zinc-700"
                />
              </label>

              {/* category */}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-zinc-500">category</span>
                <input
                  type="text"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="e.g. lansman"
                  className="border border-zinc-700 bg-black px-2 py-1.5 text-xs text-zinc-300 placeholder:text-zinc-700"
                />
              </label>

              {/* canvas_format */}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-zinc-500">canvas_format</span>
                <input
                  type="text"
                  value={canvasFormat}
                  onChange={(e) => setCanvasFormat(e.target.value)}
                  placeholder="e.g. 9:16"
                  className="border border-zinc-700 bg-black px-2 py-1.5 text-xs text-zinc-300 placeholder:text-zinc-700"
                />
              </label>
            </div>
          </div>

          {/* Deconstruct button */}
          <button
            type="button"
            onClick={handleDeconstruct}
            disabled={!file || loading}
            className="mt-4 w-full border border-white py-3 text-sm text-white transition-colors hover:bg-white hover:text-black disabled:border-zinc-700 disabled:text-zinc-600 disabled:hover:bg-transparent disabled:hover:text-zinc-600"
          >
            {loading ? "deconstructing…" : "deconstruct"}
          </button>
        </section>

        {/* ── Loading / error ───────────────────────────────────────── */}

        {loading && (
          <section className="mx-auto mt-8 w-full max-w-2xl">
            <div className="border-l border-zinc-700 pl-4 text-sm text-zinc-500">
              &gt; vision model analyzing image<span className="caret-blink">_</span>
            </div>
          </section>
        )}

        {error && !loading && (
          <section className="mx-auto mt-8 w-full max-w-2xl">
            <div className="border-l border-red-800 pl-4">
              <p className="text-sm text-zinc-300">$ deconstruct</p>
              <p className="mt-1 text-sm text-red-400">! {error}</p>
            </div>
          </section>
        )}

        {/* ── Results — side-by-side comparison ─────────────────────── */}

        {result && !loading && (
          <section className="mx-auto mt-10 w-full max-w-5xl">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {/* LEFT: image preview */}
              <div>
                <p className="text-xs text-zinc-600">03 // uploaded image</p>
                <div className="mt-2 border border-zinc-800 bg-zinc-950 p-2">
                  {previewUrl ? (
                    <img
                      src={previewUrl}
                      alt="Template preview"
                      className="w-full object-contain"
                      style={{ maxHeight: "60vh" }}
                    />
                  ) : (
                    <p className="py-12 text-center text-xs text-zinc-700">
                      no preview
                    </p>
                  )}
                </div>

                {/* Card-level metadata summary */}
                {liveCard && (
                  <div className="mt-3 border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-500">
                    <p>
                      concept:{" "}
                      <span className="text-zinc-200">
                        {liveCard.concept}
                      </span>
                    </p>
                    <p>
                      aspect: {liveCard.aspect_ratio} · zone:{" "}
                      {liveCard.text_zone} · tool: {liveCard.target_tool}
                    </p>
                    <p>
                      source: {liveCard.source_type} · ref: {liveCard.source_ref}
                    </p>
                    <p>
                      archetype: {liveCard.archetype} · category:{" "}
                      {liveCard.category} · format: {liveCard.format}
                    </p>
                  </div>
                )}
              </div>

              {/* RIGHT: rendered card fields + editable JSON */}
              <div>
                <p className="text-xs text-zinc-600">04 // deconstructed card</p>

                {/* ── Key fields rendered visually ──────────────────── */}
                {liveCard && (
                  <div className="mt-2 space-y-3 border border-zinc-800 bg-zinc-950 p-3">
                    {/* Color palette — swatches the reviewer can verify */}
                    {palette.length > 0 && (
                      <div>
                        <p className="text-xs text-zinc-500">color_palette</p>
                        <div className="mt-1 flex flex-wrap gap-2">
                          {palette.map((hex) => (
                            <span
                              key={hex}
                              className="inline-flex items-center gap-1.5 rounded border border-zinc-700 px-2 py-1 text-xs"
                            >
                              <ColorSwatch hex={hex} />
                              <span className="text-zinc-400">{hex}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Fonts — most likely to drift, so make them prominent */}
                    {fonts && (
                      <div>
                        <p className="text-xs text-zinc-500">fonts</p>
                        <div className="mt-1 flex flex-wrap gap-1">
                          <FontBadge
                            label="headline:"
                            value={fonts.headline_font}
                          />
                          <FontBadge
                            label="body:"
                            value={fonts.body_font}
                          />
                        </div>
                      </div>
                    )}

                    {/* Point sizes — high-drift fields */}
                    {(native?.headline_pt !== undefined ||
                      native?.subtext_pt !== undefined) && (
                      <div>
                        <p className="text-xs text-zinc-500">point sizes</p>
                        <div className="mt-1">
                          <PtBadge
                            label="headline:"
                            value={native?.headline_pt}
                          />
                          <PtBadge
                            label="subtext:"
                            value={native?.subtext_pt}
                          />
                        </div>
                      </div>
                    )}

                    {/* Headline / subtext text content */}
                    {native && (
                      <div>
                        <p className="text-xs text-zinc-500">
                          headline &amp; subtext
                        </p>
                        <p className="mt-1 text-sm text-zinc-200">
                          {native.headline || (
                            <span className="text-zinc-700">—</span>
                          )}
                        </p>
                        <p className="text-xs text-zinc-400">
                          {native.subtext || (
                            <span className="text-zinc-700">—</span>
                          )}
                        </p>
                        {native.alignment_zone && (
                          <p className="mt-1 text-xs text-zinc-500">
                            alignment: {native.alignment_zone}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* ── Editable JSON textarea ────────────────────────── */}
                <div className="mt-3">
                  <p className="text-xs text-zinc-600">
                    05 // raw JSON (editable — fix vision mistakes here)
                  </p>
                  <textarea
                    value={jsonText}
                    onChange={(e) => {
                      setJsonText(e.target.value);
                      setSaved(false);
                      setSaveError(null);
                    }}
                    rows={24}
                    spellCheck={false}
                    className="mt-2 w-full resize-y border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed text-zinc-300 outline-none focus:border-zinc-600"
                  />
                </div>
              </div>
            </div>

            {/* ── Approval bar ──────────────────────────────────────── */}
            <div className="mt-6 border border-zinc-800 bg-zinc-950 p-4">
              <p className="text-xs text-zinc-600">06 // review &amp; approve</p>

              <label className="mt-3 flex flex-col gap-1">
                <span className="text-xs text-zinc-500">
                  reviewer_note (optional)
                </span>
                <input
                  type="text"
                  value={reviewerNote}
                  onChange={(e) => setReviewerNote(e.target.value)}
                  placeholder="e.g. palette matches brand, fonts look correct"
                  className="border border-zinc-700 bg-black px-2 py-1.5 text-xs text-zinc-300 placeholder:text-zinc-700"
                />
              </label>

              {saveError && (
                <p className="mt-3 text-sm text-red-400">! {saveError}</p>
              )}

              {saved && (
                <p className="mt-3 text-sm text-green-400">
                  &gt; saved to corpus ✓
                </p>
              )}

              <div className="mt-4 flex gap-3">
                <button
                  type="button"
                  onClick={handleApprove}
                  disabled={!jsonText.trim() || saving}
                  className="flex-1 border border-green-700 py-2.5 text-sm text-green-400 transition-colors hover:bg-green-950 disabled:border-zinc-700 disabled:text-zinc-600 disabled:hover:bg-transparent"
                >
                  {saving ? "saving…" : "approve & save"}
                </button>
                <button
                  type="button"
                  onClick={handleDiscard}
                  disabled={saving}
                  className="flex-1 border border-zinc-700 py-2.5 text-sm text-zinc-500 transition-colors hover:border-red-800 hover:text-red-400 disabled:border-zinc-800 disabled:text-zinc-700"
                >
                  discard
                </button>
              </div>
              <p className="mt-2 text-xs text-zinc-600">
                No record is saved until you press &ldquo;approve &amp;
                save&rdquo;. Review the card carefully first.
              </p>
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="py-8 text-center text-xs text-zinc-600">
        CAVDESIGN · template ingestion
      </footer>
    </div>
  );
}
