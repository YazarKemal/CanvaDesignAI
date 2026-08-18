// Types for the Mockup Director workflow (analyze → refine → generate).
// Mirrors the shapes returned by mockup_api.py / src/mockup_workflow.py.

// --------------------------------------------------------------------------- //
// Listing roles (mockup types). Values are stable API identifiers.
// --------------------------------------------------------------------------- //

export type ListingRole =
  | "hero"
  | "lifestyle"
  | "close_up"
  | "scale"
  | "alternative_scene"
  | "clean_product";

export const LISTING_ROLES: readonly ListingRole[] = [
  "hero",
  "lifestyle",
  "close_up",
  "scale",
  "alternative_scene",
  "clean_product",
];

export const LISTING_ROLE_LABELS: Record<ListingRole, string> = {
  hero: "Hero",
  lifestyle: "Lifestyle",
  close_up: "Close-up",
  scale: "Scale",
  alternative_scene: "Alternative Scene",
  clean_product: "Clean Product",
};

// --------------------------------------------------------------------------- //
// An image attached by the user for mockup analysis.
// --------------------------------------------------------------------------- //

export interface AttachedImage {
  file: File;
  name: string;
  url: string;
  mimeType: string;
}

// --------------------------------------------------------------------------- //
// Backend shapes (snake_case keys preserved verbatim).
// --------------------------------------------------------------------------- //

export interface AssetAnalysis {
  product_type: string;
  asset_category: string;
  product_category?: string | null;
  presentation_mode?: string;
  orientation: string;
  aspect_ratio: string;
  visual_style: string;
  mood: string[];
  dominant_colors: string[];
  content_summary: string;
  composition_notes: string;
  audience: string;
  target_customer: string;
  physical_presentation_assumption: string;
}

export interface CreativeDirection {
  id: string;
  title: string;
  rationale: string;
  environment: string;
  mood: string;
  presentation_style: string;
  recommended?: boolean;
}

export interface BestRecommendation {
  id: string;
  title: string;
  message: string;
}

export interface ClarifyingQuestion {
  key: string;
  question: string;
  options: string[];
}

export interface MockupAnalyzeResponse {
  asset_analysis: AssetAnalysis;
  recommended_directions: CreativeDirection[];
  best_recommendation: BestRecommendation;
  clarification_needed: boolean;
  clarifying_questions: ClarifyingQuestion[];
  mockups?: unknown[];
}

export interface RefinedStrategy {
  direction: CreativeDirection;
  category: string;
  listing_role: ListingRole;
  environment: string;
  lighting: string;
  surface_or_frame: string;
  camera: string;
  composition: string;
  styling_notes: string;
  applied_answers: Record<string, string>;
  remaining_questions: ClarifyingQuestion[];
}

export interface FinalPromptResponse {
  direction: CreativeDirection;
  listing_role: ListingRole;
  recommended_usage: string;
  final_prompt: string;
  negative_prompt: string;
  preservation_notes: string[];
  preservation_clause: string;
}

export const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];

export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
