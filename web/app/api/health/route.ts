import { NextResponse } from "next/server";

// Thin proxy: pings the backend health endpoint so the frontend can
// verify the CaVDesign engine is reachable without making a full
// /api/chat call.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  try {
    const upstream = await fetch(`${BACKEND_URL}/health`);
    if (!upstream.ok) {
      return NextResponse.json(
        { status: "error", detail: `Backend returned ${upstream.status}` },
        { status: 502 },
      );
    }
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch {
    return NextResponse.json(
      { status: "error", detail: `Could not reach the CaVDesign engine at ${BACKEND_URL}.` },
      { status: 502 },
    );
  }
}
