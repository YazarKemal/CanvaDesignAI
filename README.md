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

## Usage

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY and DEEPSEEK_API_KEY

python main.py "Grand Opening Cafe"
```

## Development

```bash
pip install -r requirements.txt pytest
pytest
```

All API calls are wrapped behind injectable clients, so the test suite runs
fully offline against mocked Anthropic/DeepSeek responses.
