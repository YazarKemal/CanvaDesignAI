import { NextResponse } from "next/server";

// Thin proxy: on-demand Omni-Channel adaptation of an already-approved card.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body." }, { status: 400 });
  }

  const { card, formats, brand } = body as { card?: unknown; formats?: unknown; brand?: unknown };
  if (!card || typeof card !== "object") {
    return NextResponse.json({ detail: "card is required." }, { status: 400 });
  }
  if (!Array.isArray(formats) || formats.length === 0) {
    return NextResponse.json({ detail: "formats must be a non-empty array." }, { status: 400 });
  }

  try {
    const upstream = await fetch(`${BACKEND_URL}/api/adapt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ card, formats, brand: typeof brand === "string" ? brand : null }),
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
