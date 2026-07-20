# CanvaDesignAI

A **Visual Design Prompt Engine** (an "Art Director" in code). You give it a
plain concept — `"Grand Opening Cafe"` — and its dual-agent system engineers
a graphic-designer-quality **image-generation prompt** you can paste straight
into DALL·E 3 or Canva Magic Media.

It's for people who already have ChatGPT Pro or Canva Pro but can't reliably
get *consistent, designer-grade* results out of them. This tool automates the
prompt-engineering craft — color theory, photography language, composition,
lighting, and mood — so every prompt lands.

> **Scope:** this project outputs **prompts only**. It does not generate
> images and does not connect to Canva, DALL·E, or any external service —
> you run the prompt in the tool you already pay for.

## 1. The Art Director Constitution

[`design_rules.json`](design_rules.json) is the single source of truth both
agents obey. It codifies the craft of a great image prompt:

- **Prompt structure** — token ordering (subject → medium → composition →
  lighting → color → camera → quality), length, and a specificity mandate.
- **Medium & photography** — explicit mediums plus camera/lens, film-stock,
  and depth-of-field vocabulary.
- **Composition** — rule of thirds, camera angles, deliberate negative space
  (so you can add real text in Canva afterward).
- **Lighting** — a vocabulary of setups; lighting is never left implicit.
- **Color theory** — harmony schemes, 60-30-10 weighting, forbidden clashes.
- **Style & mood, negative prompts, aspect ratio, target tools**.
- **Review rubric** — the weighted criteria and pass threshold the Reviewer
  scores against.

## 2. Dual-Agent Validation

```
concept ──▶ Generator (Claude) ──▶ prompt ──▶ Reviewer (DeepSeek) ──▶ score
                 ▲                                    │
                 └──────────── feedback (if score < threshold) ─────┘
```

- **Generator** (`src/generator.py`, Claude): the art director. Turns your
  concept into a structured visual prompt honoring the constitution.
- **Reviewer** (`src/reviewer.py`, DeepSeek — fast & cheap): scores the prompt
  on concept fidelity, visual specificity, composition/lighting, color
  coherence, and tool-readiness, returning actionable feedback when it falls
  short.
- **Orchestrator** (`src/orchestrator.py`): loops Generator → Reviewer,
  feeding feedback back for revision up to `max_attempts`, and returns the
  best-scoring prompt.

## 3. Structured Output

The result is always this shape (validated by [`src/schema.py`](src/schema.py)):

```json
{
  "concept": "Grand Opening Cafe",
  "image_prompt": "A flat-white with delicate rosetta latte art in a matte-black ceramic cup, resting on a reclaimed-oak counter, photography shot on 85mm f/1.4 with shallow depth of field, rule-of-thirds with the cup on the lower-left third and clean empty upper space reserved for a headline, soft golden-hour window light raking in from the right, warm amber and deep espresso tones against a cream background, cozy and artisanal mood, high detail.",
  "negative_prompt": "text, watermark, signature, logo, extra fingers, deformed hands, cluttered background, low resolution, jpeg artifacts, harsh oversaturation",
  "art_direction": {
    "medium": "photography",
    "composition": "rule of thirds, subject lower-left, empty upper third for headline, eye-level",
    "lighting": "soft golden-hour window light from the right",
    "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
    "mood": "cozy, artisanal, inviting",
    "camera": "85mm f/1.4, shallow depth of field"
  },
  "aspect_ratio": "4:5",
  "target_tools": ["DALL-E 3", "Canva Magic Media"]
}
```

`image_prompt` is the star; `negative_prompt` excludes the usual diffusion
artifacts (including embedded text, so your base image stays clean for real
typography in Canva). See
[`examples/grand_opening_cafe.json`](examples/grand_opening_cafe.json).

## Usage

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY and DEEPSEEK_API_KEY

# Full structured output:
python main.py "Grand Opening Cafe"

# Just the prompt string, ready to paste into DALL-E 3 / Magic Media:
python main.py "Grand Opening Cafe" --raw
```

## Development

```bash
pip install -r requirements.txt pytest
pytest
```

All API calls are wrapped behind injectable clients, so the test suite runs
fully offline against mocked Anthropic/DeepSeek responses.
