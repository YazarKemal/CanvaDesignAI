// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";

const PAYLOAD = {
  analysis: { asset_analysis: {}, recommended_directions: [] },
  selected_direction: "moody_collector",
  answers: { framing: "Framed" },
  listing_role: "clean_product",
};

function jsonRequest(body: unknown) {
  return new Request("http://localhost/api/mockup/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/mockup/generate", () => {
  afterEach(() => vi.restoreAllMocks());

  it("forwards the JSON payload unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ final_prompt: "a prompt" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(jsonRequest(PAYLOAD));

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8002/api/mockup/workflow/generate");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(PAYLOAD);
  });

  it("preserves the upstream status and error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Unknown creative direction" }), { status: 502 }),
      ),
    );

    const res = await POST(jsonRequest(PAYLOAD));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ detail: "Unknown creative direction" });
  });

  it("returns 400 for invalid JSON", async () => {
    const req = new Request("http://localhost/api/mockup/generate", {
      method: "POST",
      body: "not-json",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 502 when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));

    const res = await POST(jsonRequest(PAYLOAD));
    expect(res.status).toBe(502);
    expect(await res.json()).toMatchObject({
      detail: expect.stringContaining("mockup director"),
    });
  });
});
