import { NextResponse } from "next/server";

// Thin proxy: lists available brand profiles for the brand picker.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  try {
    const upstream = await fetch(`${BACKEND_URL}/api/brands`);
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch {
    return NextResponse.json(
      { detail: `Could not reach the CaVDesign engine at ${BACKEND_URL}.` },
      { status: 502 },
    );
  }
}
