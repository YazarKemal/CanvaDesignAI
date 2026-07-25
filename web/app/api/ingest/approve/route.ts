import { NextResponse } from "next/server";

// Thin proxy: browser → Next.js → Python FastAPI /ingest/approve.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "Invalid JSON body." },
      { status: 400 },
    );
  }

  const { card, reviewer_note } = body as {
    card?: unknown;
    reviewer_note?: unknown;
  };

  if (!card || typeof card !== "object") {
    return NextResponse.json(
      { detail: "card is required and must be an object." },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(`${BACKEND_URL}/ingest/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        card,
        reviewer_note:
          typeof reviewer_note === "string" ? reviewer_note : null,
      }),
    });

    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch {
    return NextResponse.json(
      { detail: `Could not reach the CaVDesign engine at ${BACKEND_URL}.` },
      { status: 502 },
    );
  }
}
