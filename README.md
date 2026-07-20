# CanvaDesignAI

An AI pipeline that turns a short concept (e.g. "Grand Opening Cafe") into a
ready-to-use, structured design recipe — enforced by a **Design
Constitution** and checked by a **dual-agent validation loop** before it
ever reaches you.

## 1. The Design Constitution

[`design_rules.json`](design_rules.json) is the single source of truth for
every design produced by this project. It fixes:

- **Color theory** — WCAG contrast minimums, a list of forbidden color
  combinations (e.g. warm red on vivid green), and 60-30-10 harmony rules.
- **Typography** — a curated set of headline/body font pairings (e.g.
  Montserrat + Playfair Display) and hierarchy rules.
- **White space** — minimum gap ratios between text and imagery, margins,
  and text density limits.
- **Layout** — safe zones, rule-of-thirds composition, text/visual split.
- **Review rubric** — the weighted scoring criteria and pass threshold used
  by the Reviewer agent below.

Both agents load this same file, so the rules they operate under never
drift out of sync.

## 2. Dual-Agent Validation

```
concept ──▶ Generator (Claude) ──▶ draft ──▶ Reviewer (DeepSeek) ──▶ score
                 ▲                                   │
                 └──────────── feedback (if score < threshold) ─────┘
```

- **Generator** (`src/generator.py`, Claude / Anthropic API): takes your
  concept and drafts a design recipe honoring the constitution.
- **Reviewer** (`src/reviewer.py`, DeepSeek API — fast & cheap): scores the
  draft against the constitution's rubric (contrast, readability,
  whitespace, template usability, brand coherence) and returns actionable
  feedback if it falls below the pass threshold.
- **Orchestrator** (`src/orchestrator.py`): loops Generator → Reviewer,
  feeding rejection feedback back into the Generator, up to `max_attempts`,
  and returns the best-scoring draft.

## 3. Structured Output

The Generator's output — and therefore the pipeline's final result — is
always the same JSON shape (validated by [`src/schema.py`](src/schema.py)),
ready to copy, apply by hand, or wire up to the Canva API later:

```json
{
  "theme": "Modern Cafe",
  "color_palette": ["#4A2E1B", "#F5EFE6", "#D4A373"],
  "typography": {
    "headline": "Placeholder: [Cafe Name]",
    "body_text": "Join us for warm vibes!"
  },
  "image_prompts": {
    "main_visual": "Cinematic shot of a latte with perfect micro-foam art, resting on a wooden table, soft window light, subtle drop shadow."
  },
  "layout_instructions": "Place text at the top 40% of the canvas. Keep the bottom 60% for the main visual inside a draggable frame."
}
```

See [`examples/grand_opening_cafe.json`](examples/grand_opening_cafe.json)
for a full example.

## 4. Publishing to Canva

Canva's public Connect API does not expose "Magic Media" (its AI
text-to-image feature) to third-party developers — it only offers asset
upload and design creation. So turning a design draft into a real Canva
design takes two steps:

```
draft ──▶ OpenAIImageProvider (generates image_prompts.main_visual) ──▶ image bytes
              │
              ▼
        CanvaClient.upload_asset ──▶ asset_id ──▶ CanvaClient.create_design ──▶ edit_url
```

- **`src/image_provider.py`** (OpenAI Images API): renders
  `image_prompts.main_visual` into an actual image, since Canva's API can't.
- **`src/canva_client.py`** (Canva Connect API): uploads that image as an
  asset and creates a design from it (plus `export_design` to download a
  finished file). Auth is a bearer access token — obtaining one requires
  Canva's OAuth2 (authorization code + PKCE) flow, which is not implemented
  here; generate a token via Canva's own quickstart/Postman collection and
  set `CANVA_ACCESS_TOKEN`.
- **`src/canva_pipeline.py`**: wires the two together —
  `publish_design_to_canva(design, canva_client=..., image_provider=...)`.

> Endpoint paths/fields in `canva_client.py` are written from documentation
> knowledge (Canva's docs site blocked automated fetches while this was
> built) — spot-check against the current [Canva Connect API
> reference](https://www.canva.dev/docs/connect/) before relying on it in
> production.

## Usage

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY and DEEPSEEK_API_KEY

python main.py "Grand Opening Cafe"

# Also generate the main visual and push it into a real Canva design:
python main.py "Grand Opening Cafe" --publish-to-canva --canva-design-type poster
```

## Development

```bash
pip install -r requirements.txt pytest
pytest
```

All API calls are wrapped behind injectable clients, so the test suite runs
fully offline against mocked Anthropic/DeepSeek/OpenAI/Canva responses.
