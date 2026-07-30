"use client";

import { useMemo, useState } from "react";

type Operation = "optimize" | "upscale" | "tiles";

function filenameFromDisposition(value: string | null) {
  const match = value?.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? "canva-output";
}

export default function ImageToolkitPage() {
  const [file, setFile] = useState<File | null>(null);
  const [operation, setOperation] = useState<Operation>("optimize");
  const [targetMb, setTargetMb] = useState(49);
  const [factor, setFactor] = useState(2);
  const [columns, setColumns] = useState(2);
  const [rows, setRows] = useState(2);
  const [overlap, setOverlap] = useState(32);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [manifest, setManifest] = useState<Record<string, unknown> | null>(null);

  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);

  async function processImage() {
    if (!file) return;
    setBusy(true);
    setError("");
    setManifest(null);

    const body = new FormData();
    body.append("file", file);
    body.append("operation", operation);
    body.append("target_mb", String(targetMb));
    body.append("preferred_format", "auto");
    body.append("factor", String(factor));
    body.append("sharpen", "true");
    body.append("columns", String(columns));
    body.append("rows", String(rows));
    body.append("overlap_px", String(overlap));
    body.append("tile_format", "png");

    try {
      const res = await fetch("/api/image/process", { method: "POST", body });
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Processing failed." }));
        throw new Error(data.detail ?? "Processing failed.");
      }
      const header = res.headers.get("x-cavdesign-manifest");
      if (header) setManifest(JSON.parse(header));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filenameFromDisposition(res.headers.get("content-disposition"));
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Processing failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-5 py-12 text-zinc-100">
      <header className="border-b border-zinc-800 pb-8">
        <p className="text-xs tracking-[0.35em] text-zinc-500">CAVDESIGN TOOL</p>
        <h1 className="mt-3 text-4xl font-semibold">Canva Image Toolkit</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-400">
          Preserve resolution, prepare files below Canva limits, create clean 2×/4× exports,
          or split oversized artwork into overlap-safe tiles.
        </p>
      </header>

      <section className="mt-8 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="border border-zinc-800 bg-zinc-950 p-5">
          <label className="block text-xs tracking-widest text-zinc-500">01 / SOURCE IMAGE</label>
          <input
            className="mt-4 block w-full text-sm text-zinc-400 file:mr-4 file:border file:border-zinc-700 file:bg-black file:px-4 file:py-2 file:text-zinc-200"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {preview && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="Preview" className="mt-5 max-h-[520px] w-full object-contain" />
          )}
        </div>

        <div className="border border-zinc-800 bg-zinc-950 p-5">
          <p className="text-xs tracking-widest text-zinc-500">02 / OPERATION</p>
          <div className="mt-4 grid grid-cols-3 gap-2">
            {(["optimize", "upscale", "tiles"] as Operation[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setOperation(item)}
                className={`border px-3 py-2 text-xs uppercase ${
                  operation === item ? "border-white bg-white text-black" : "border-zinc-700 text-zinc-400"
                }`}
              >
                {item}
              </button>
            ))}
          </div>

          {operation === "optimize" && (
            <label className="mt-6 block text-sm text-zinc-300">
              Canva target size: <strong>{targetMb} MB</strong>
              <input
                className="mt-3 w-full"
                type="range"
                min="5"
                max="49"
                value={targetMb}
                onChange={(e) => setTargetMb(Number(e.target.value))}
              />
              <span className="mt-2 block text-xs text-zinc-500">
                Pixel dimensions remain unchanged. PNG is attempted first, then high-quality WebP/JPEG.
              </span>
            </label>
          )}

          {operation === "upscale" && (
            <div className="mt-6">
              <p className="text-sm text-zinc-300">Upscale factor</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {[2, 4].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setFactor(value)}
                    className={`border py-2 ${factor === value ? "border-white" : "border-zinc-700 text-zinc-500"}`}
                  >
                    {value}×
                  </button>
                ))}
              </div>
              <p className="mt-3 text-xs leading-5 text-zinc-500">
                Uses Lanczos reconstruction plus restrained sharpening. It preserves line art without inventing AI detail.
              </p>
            </div>
          )}

          {operation === "tiles" && (
            <div className="mt-6 grid grid-cols-3 gap-3 text-sm">
              <label>Columns<input className="mt-2 w-full bg-black p-2" type="number" min="1" max="8" value={columns} onChange={(e) => setColumns(Number(e.target.value))} /></label>
              <label>Rows<input className="mt-2 w-full bg-black p-2" type="number" min="1" max="8" value={rows} onChange={(e) => setRows(Number(e.target.value))} /></label>
              <label>Overlap<input className="mt-2 w-full bg-black p-2" type="number" min="0" max="512" value={overlap} onChange={(e) => setOverlap(Number(e.target.value))} /></label>
              <p className="col-span-3 text-xs leading-5 text-zinc-500">
                Exports a ZIP with placement_manifest.json. Tiles are transport pieces, not semantic object layers.
              </p>
            </div>
          )}

          <button
            type="button"
            disabled={!file || busy}
            onClick={processImage}
            className="mt-8 w-full border border-white py-3 text-sm font-medium disabled:border-zinc-700 disabled:text-zinc-600"
          >
            {busy ? "PROCESSING…" : "PREPARE FOR CANVA"}
          </button>

          {error && <p className="mt-4 border-l border-red-700 pl-3 text-sm text-red-300">{error}</p>}
          {manifest && (
            <pre className="mt-4 max-h-56 overflow-auto border border-zinc-800 bg-black p-3 text-xs text-zinc-500">
              {JSON.stringify(manifest, null, 2)}
            </pre>
          )}
        </div>
      </section>

      <section className="mt-8 border border-amber-900/60 bg-amber-950/20 p-5 text-sm leading-6 text-amber-100/80">
        <strong>Semantic Layer Extractor:</strong> the next module will use promptable segmentation
        (SAM-family provider) to create transparent object layers from the full-resolution master.
        This first release deliberately distinguishes true object layers from rectangular splitting.
      </section>
    </main>
  );
}
