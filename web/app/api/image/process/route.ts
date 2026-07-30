import { NextResponse } from "next/server";

const IMAGE_BACKEND_URL = process.env.IMAGE_BACKEND_URL ?? "http://127.0.0.1:8001";

export async function POST(request: Request) {
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json({ detail: "Invalid multipart form body." }, { status: 400 });
  }

  const file = formData.get("file");
  if (!file || !(file instanceof Blob)) {
    return NextResponse.json({ detail: "file is required." }, { status: 400 });
  }

  try {
    const upstream = await fetch(`${IMAGE_BACKEND_URL}/api/image/process`, {
      method: "POST",
      body: formData,
    });
    if (!upstream.ok) {
      const data = await upstream.json().catch(() => ({ detail: "Image processing failed." }));
      return NextResponse.json(data, { status: upstream.status });
    }

    const body = await upstream.arrayBuffer();
    const headers = new Headers();
    headers.set("Content-Type", upstream.headers.get("content-type") ?? "application/octet-stream");
    headers.set(
      "Content-Disposition",
      upstream.headers.get("content-disposition") ?? 'attachment; filename="canva-output.bin"',
    );
    const manifest = upstream.headers.get("x-cavdesign-manifest");
    if (manifest) headers.set("X-CaVDesign-Manifest", manifest);
    return new Response(body, { status: 200, headers });
  } catch {
    return NextResponse.json(
      { detail: `Could not reach the image engine at ${IMAGE_BACKEND_URL}.` },
      { status: 502 },
    );
  }
}
