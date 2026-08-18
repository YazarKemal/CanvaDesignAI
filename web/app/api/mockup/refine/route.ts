import { NextResponse } from "next/server";

// Thin proxy: forwards the refine payload (analysis + direction + answers) to
// the Python FastAPI mockup director and returns its response unchanged.
const MOCKUP_BACKEND_URL = process.env.MOCKUP_BACKEND_URL ?? "http://127.0.0.1:8002";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body." }, { status: 400 });
  }

  try {
    const upstream = await fetch(`${MOCKUP_BACKEND_URL}/api/mockup/workflow/refine`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch {
    return NextResponse.json(
      { detail: `Could not reach the mockup director at ${MOCKUP_BACKEND_URL}.` },
      { status: 502 },
    );
  }
}
