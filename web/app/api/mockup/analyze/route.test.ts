// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";

function formDataWithFile() {
  const form = new FormData();
  form.append("file", new File(["poster"], "poster.png", { type: "image/png" }), "poster.png");
  form.append("marketplace", "Etsy");
  return form;
}

describe("POST /api/mockup/analyze", () => {
  afterEach(() => vi.restoreAllMocks());

  it("forwards the multipart upload to the mockup director", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const req = new Request("http://localhost/api/mockup/analyze", {
      method: "POST",
      body: formDataWithFile(),
    });
    const res = await POST(req);

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8002/api/mockup/workflow/analyze");
    expect(init.method).toBe("POST");
    // No manual multipart Content-Type header — the boundary must come from FormData.
    expect(init.headers).toBeUndefined();
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("preserves the upstream status and error body", async () => {
    const upstream = new Response(JSON.stringify({ detail: "Unsupported file type." }), {
      status: 400,
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(upstream));

    const req = new Request("http://localhost/api/mockup/analyze", {
      method: "POST",
      body: formDataWithFile(),
    });
    const res = await POST(req);

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ detail: "Unsupported file type." });
  });

  it("returns 400 when no file is attached", async () => {
    const form = new FormData();
    form.append("marketplace", "Etsy");
    const req = new Request("http://localhost/api/mockup/analyze", {
      method: "POST",
      body: form,
    });

    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 502 when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));

    const req = new Request("http://localhost/api/mockup/analyze", {
      method: "POST",
      body: formDataWithFile(),
    });
    const res = await POST(req);

    expect(res.status).toBe(502);
    expect(await res.json()).toMatchObject({
      detail: expect.stringContaining("mockup director"),
    });
  });
});
