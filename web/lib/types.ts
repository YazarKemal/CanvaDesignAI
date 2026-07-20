// Shape returned by the FastAPI /api/chat backend (the Canva automation card).
// Mirrors src/schema.py's PROMPT_CARD_SCHEMA field-for-field.

export type TextZone = "top" | "bottom" | "left" | "right" | "center";

// Mirrors src/omni_channel.py's TARGET_FORMATS keys.
export type TargetFormat = "instagram_post" | "instagram_story" | "banner";

export const TARGET_FORMAT_LABELS: Record<TargetFormat, string> = {
  instagram_post: "post",
  instagram_story: "story",
  banner: "banner",
};

// Mirrors src/canva_rules.py's CANVA_KNOWLEDGE_BASE["dimensions"] values,
// used only to hide the "adapt to X" button for a card's own format.
export const TARGET_FORMAT_ASPECT_RATIOS: Record<TargetFormat, string> = {
  instagram_post: "1080x1080 (1:1)",
  instagram_story: "1080x1920 (9:16)",
  banner: "1920x1080 (16:9)",
};

export interface LayerTypographyArchitecture {
  headline: string;
  subtext: string;
  color_palette: string[];
  fonts: {
    headline_font: string;
    body_font: string;
  };
  background_layers: string;
  magic_media_style?: string;
}

export interface PromptCard {
  concept: string;
  magic_media_prompt: string;
  negative_prompt: string;
  aspect_ratio: string;
  target_tool: string;
  text_zone: TextZone;
  layer_typography_architecture: LayerTypographyArchitecture;
  direct_action_tip: string[];
  canva_keywords?: string[];
}

export interface ChatResponse {
  card: PromptCard;
  approved: boolean;
  score: number;
  attempts: number;
  // Plain-text block (directive + full card) ready to paste into a
  // Claude/ChatGPT chat that has a Canva tool connected.
  paste_text: string;
  // Best available WCAG contrast ratio within color_palette (>= 4.5 = AA).
  contrast_ratio: number;
  text_zone: TextZone;
}

// One entry in the terminal log: either a rendered card or an error line.
export interface LogEntry {
  id: number;
  concept: string;
  card?: PromptCard;
  approved?: boolean;
  score?: number;
  pasteText?: string;
  contrastRatio?: number;
  error?: string;
  // Set on an entry that was produced by "adapt to other formats" rather
  // than a fresh chat request -- lets the card omit its own format button.
  sourceFormat?: TargetFormat;
}

export interface Brand {
  slug: string;
  name: string;
}

export interface BrandsResponse {
  brands: Brand[];
}

export interface AdaptResponse {
  variants: Record<string, PromptCard>;
}
