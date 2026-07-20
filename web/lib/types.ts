// Shape returned by the FastAPI /api/chat backend (the prompt card).

export interface ArtDirection {
  color_palette: string[];
  lighting: string;
  mood: string;
  magic_media_style?: string;
}

export interface PromptCard {
  concept: string;
  prompt_text: string;
  negative_prompt: string;
  aspect_ratio: string;
  target_tool: string;
  canva_tip: string;
  art_direction: ArtDirection;
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
