// Shape returned by the FastAPI /api/chat backend (the Canva automation card).
// Mirrors src/schema.py's PROMPT_CARD_SCHEMA field-for-field.

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
  layer_typography_architecture: LayerTypographyArchitecture;
  direct_action_tip: string[];
  canva_keywords?: string[];
}

export interface ChatResponse {
  card: PromptCard;
  approved: boolean;
  score: number;
  attempts: number;
}

// One entry in the terminal log: either a rendered card or an error line.
export interface LogEntry {
  id: number;
  concept: string;
  card?: PromptCard;
  approved?: boolean;
  score?: number;
  error?: string;
}
