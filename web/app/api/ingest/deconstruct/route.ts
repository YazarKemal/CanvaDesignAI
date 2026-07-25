import { NextResponse } from "next/server";

// Thin proxy for multipart form upload → Python FastAPI /ingest/deconstruct.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export async function POST(request: Request) {
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json(
      { detail: "Invalid multipart form body." },
      { status: 400 },
    );
  }

  const file = formData.get("file");
  if (!file || !(file instanceof Blob)) {
    return NextResponse.json(
      { detail: "file is required and must be an image." },
      { status: 400 },
    );
  }

  // Forward the FormData as-is to the Python backend.
  const upstream = new FormData();
  upstream.append("file", file, (file as any).name ?? "upload");
  for (const key of [
    "source_type",
    "source_ref",
    "archetype",
    "category",
    "canvas_format",
  ]) {
    const val = formData.get(key);
    if (typeof val === "string") upstream.append(key, val);
  }

  try {
    const res = await fetch(`${BACKEND_URL}/ingest/deconstruct`, {
      method: "POST",
      body: upstream,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: `Could not reach the CaVDesign engine at ${BACKEND_URL}.` },
      { status: 502 },
    );
  }
}
