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

// Brand Launch Kit asset types — generated automatically when a brand is active.
export type BrandKitAsset = "logo_emblem" | "opening_poster" | "menu_list" | "packaging_merch";

export const BRAND_KIT_ASSET_LABELS: Record<BrandKitAsset, string> = {
  logo_emblem: "🪧 Logo",
  opening_poster: "📣 Poster",
  menu_list: "📜 Menu",
  packaging_merch: "☕ Packaging",
};

// Mirrors src/canva_rules.py's CANVA_KNOWLEDGE_BASE["dimensions"] values,
// used only to hide the "adapt to X" button for a card's own format.
export const TARGET_FORMAT_ASPECT_RATIOS: Record<TargetFormat, string> = {
  instagram_post: "1080x1080 (1:1)",
  instagram_story: "1080x1920 (9:16)",
  banner: "1920x1080 (16:9)",
};

/** Map a ratio string (any order — "1:1 (1080x1080)" or "1080x1080 (1:1)")
 *  to its TargetFormat. Returns null when the ratio doesn't match. */
export function formatForAspectRatio(aspectRatio: string): TargetFormat | null {
  // Normalise: extract the ratio portion (e.g. "1:1", "9:16", "16:9")
  const ratioMatch = aspectRatio.match(/(\d+:\d+)/);
  if (!ratioMatch) return null;
  const ratio = ratioMatch[1];
  const map: Record<string, TargetFormat> = {
    "1:1": "instagram_post",
    "9:16": "instagram_story",
    "16:9": "banner",
  };
  return map[ratio] ?? null;
}

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

/** New hybrid split-layer raster payload (replaces flat magic_media_prompt). */
export interface RasterBackground {
  magic_media_prompt: string;
  negative_prompt: string;
  magic_media_style?: string;
}

/** New hybrid split-layer typography payload (replaces layer_typography_architecture). */
export interface NativeTypography {
  headline: string;
  subtext: string;
  color_palette: string[];
  fonts: {
    headline_font: string;
    body_font: string;
  };
  alignment_zone: string;
  magic_media_style?: string;
}

export interface PromptCard {
  concept: string;
  aspect_ratio: string;
  target_tool: string;
  text_zone: TextZone;
  direct_action_tip: string[];
  canva_keywords?: string[];

  // ── Legacy flat fields (kept optional for backward compat) ──
  magic_media_prompt?: string;
  negative_prompt?: string;
  layer_typography_architecture?: LayerTypographyArchitecture;

  // ── New hybrid split-layer fields (raster + vector + native) ──
  raster_background?: RasterBackground;
  vector_elements?: Record<string, unknown>;
  native_typography?: NativeTypography;
}

export interface ChatResponse {
  card: PromptCard;
  approved: boolean;
  score: number;
  attempts: number;
  paste_text: string;
  contrast_ratio: number;
  text_zone: TextZone;
  selected_style_name?: string | null;
  variants?: Record<string, AdaptVariant>;
  kit_assets?: Record<string, AdaptVariant>;
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
  sourceFormat?: TargetFormat;
  selectedStyleName?: string | null;
  variants?: Record<string, AdaptVariant>;
  kitAssets?: Record<string, AdaptVariant>;
}

export interface Brand {
  slug: string;
  name: string;
}

export interface BrandsResponse {
  brands: Brand[];
}

export interface Style {
  slug: string;
  name: string;
  description: string;
}

export interface StylesResponse {
  styles: Style[];
}

export interface AdaptVariant {
  card: PromptCard;
  paste_text: string;
  contrast_ratio: number;
}

export interface AdaptResponse {
  variants: Record<string, AdaptVariant>;
}
