import { NextResponse } from "next/server";

// Thin proxy: the browser sends a multipart upload to this Next.js route, which
// forwards it to the Python FastAPI mockup director. Keeps any keys server-side.
const MOCKUP_BACKEND_URL = process.env.MOCKUP_BACKEND_URL ?? "http://127.0.0.1:8002";

export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ detail: "Expected multipart/form-data." }, { status: 400 });
  }

  if (!(form.get("file") instanceof File)) {
    return NextResponse.json({ detail: "Field 'file' must be an uploaded image." }, { status: 400 });
  }

  try {
    // Forward the FormData unchanged. Do NOT set a multipart Content-Type header
    // manually — fetch derives the correct boundary from the FormData body.
    const upstream = await fetch(`${MOCKUP_BACKEND_URL}/api/mockup/workflow/analyze`, {
      method: "POST",
      body: form,
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
